"""Shared send-rate guard — keeps LinkedIn/email sends within safe limits.

Why this exists: **Unipile does not enforce LinkedIn's sending limits.** It drives
the connected account via a hosted session and passes LinkedIn's native throttle
straight through — when the (weekly) invitation ceiling is hit, LinkedIn returns a
422 `cannot_resend_yet` and Unipile relays it back untouched. So pacing is entirely
our responsibility.

This module is the single source of truth for "how many of each channel have we
already sent in the trailing 24h / 7d", counted across BOTH send paths and
de-duplicated by draft_id:

  - scripts/send_approvals.py → appends to runs/sent.jsonl  (local, Phase-1 manual sends)
  - workers/sequence_send.py  → inserts into Postgres `sends` (Phase-2 cron)

Both callers ask `quota(channel)` how many more they may send right now, and treat
`is_invite_limit_error(exc)` as a hard stop (pause the run; don't keep hammering a
limit that won't clear until the window rolls over).

Caps are LinkedIn-side limits for ONE connected account. LinkedIn's invitation
limit is fundamentally WEEKLY; the daily caps just smooth the curve so a single day
can't spike. The numbers below are tuned for a **Sales Navigator / Premium**
account — LOWER them for a free/basic account (free invites can be as low as
~5/month).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config import BACKEND_DIR, Config

# Per-account daily ceilings (trailing 24h). Conservative on purpose — the account
# is the user's real LinkedIn, driven directly by Unipile's hosted session.
DAILY_CAPS: dict[str, int] = {
    "linkedin_connect": 30,  # guide: 30-50/day recommended (max ~80-100); ramped from 20, still conservative
    "linkedin_inmail": 5,  # Sales Nav gives ~50 InMail credits/month — pace, don't burn them
    "linkedin_dm": 30,
    "linkedin_followup_1": 30,
    "linkedin_followup_2": 30,
    # Email is sent across ~30 Maildoso boxes, so the global ceiling must clear the sum of
    # their per-box warmup caps (30 boxes x up to 25/day = 750) or it would bottleneck the
    # fleet. The PER-BOX warmup ramp (email_sender) is the real safety limiter; this is just
    # a fleet-wide backstop. Raise/lower with the mailbox count.
    "email": 750,
    "email_followup_1": 750,
    "email_followup_2": 750,
}

# Trailing-7-day ceilings. LinkedIn caps *invitations* weekly (~100-200 for a paid
# account; 100 is the conservative-safe read). Messages are bounded per-day by
# LinkedIn, not per-week, so only the invite channel carries a weekly cap.
WEEKLY_CAPS: dict[str, int] = {
    "linkedin_connect": 130,  # guide max is 200/week; 130 is a gradual ramp from 100
    "linkedin_inmail": 20,  # ~monthly credit budget spread across weeks
}

DEFAULT_DAILY_CAP = 50
SENT_LEDGER = BACKEND_DIR / "runs" / "sent.jsonl"
_ACTIVE_SEND_STATUSES = ("queued", "sent", "delivered")


@dataclass(frozen=True)
class Quota:
    """How much headroom a channel has right now."""

    channel: str
    allowed: int  # may send this many more immediately (>= 0)
    daily_cap: int
    daily_sent: int
    weekly_cap: int | None
    weekly_sent: int | None
    binding: str  # 'daily' | 'weekly' — which window is the limiter

    def describe(self) -> str:
        out = f"{self.daily_sent}/{self.daily_cap} in 24h"
        if self.weekly_cap is not None:
            out += f", {self.weekly_sent}/{self.weekly_cap} in 7d"
        return out


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _parse_ts(raw: object) -> datetime | None:
    if isinstance(raw, datetime):
        return _as_utc(raw)
    if isinstance(raw, str) and raw:
        try:
            return _as_utc(datetime.fromisoformat(raw))
        except ValueError:
            return None
    return None


def _ids_from_ledger(channel: str, since: datetime) -> set[str]:
    """draft_ids sent for `channel` since `since`, from the local JSONL ledger."""
    if not SENT_LEDGER.exists():
        return set()
    ids: set[str] = set()
    with SENT_LEDGER.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("channel") != channel:
                continue
            ts = _parse_ts(rec.get("sent_at"))
            if ts is None or ts < since:
                continue
            did = rec.get("draft_id")
            if did:
                ids.add(str(did))
    return ids


def _ids_from_db(channel: str, since: datetime) -> set[str]:
    """draft_ids sent for `channel` since `since`, from the Postgres `sends` table.

    Returns empty if no DATABASE_URL is configured (local/file mode) or on any DB
    error — the guard must never block a send because the DB hiccuped; it falls
    back to whatever the local ledger reported.
    """
    url = Config.database_url
    if not url:
        return set()
    try:
        import psycopg
    except ImportError:
        return set()
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select s.draft_id
                    from sends s
                    join drafts d on d.id = s.draft_id
                    where d.channel = %s
                      and s.sent_at >= %s
                      and s.status = any(%s)
                    """,
                    (channel, since, list(_ACTIVE_SEND_STATUSES)),
                )
                return {str(row[0]) for row in cur.fetchall()}
    except Exception:
        return set()


def _count_sent(channel: str, since: datetime) -> int:
    # Union de-dupes a draft that was recorded in both stores.
    return len(_ids_from_ledger(channel, since) | _ids_from_db(channel, since))


def quota(channel: str, *, now: datetime | None = None) -> Quota:
    """Headroom for `channel` given the trailing 24h + 7d send history.

    `allowed` is the smaller of the daily and weekly remaining counts, floored at
    0, so a caller can safely send up to that many right now.
    """
    now = now or _utcnow()
    daily_cap = DAILY_CAPS.get(channel, DEFAULT_DAILY_CAP)
    daily_sent = _count_sent(channel, now - timedelta(hours=24))
    daily_left = daily_cap - daily_sent

    weekly_cap = WEEKLY_CAPS.get(channel)
    if weekly_cap is None:
        allowed, binding, weekly_sent = daily_left, "daily", None
    else:
        weekly_sent = _count_sent(channel, now - timedelta(days=7))
        weekly_left = weekly_cap - weekly_sent
        if daily_left <= weekly_left:
            allowed, binding = daily_left, "daily"
        else:
            allowed, binding = weekly_left, "weekly"

    return Quota(
        channel=channel,
        allowed=max(0, allowed),
        daily_cap=daily_cap,
        daily_sent=daily_sent,
        weekly_cap=weekly_cap,
        weekly_sent=weekly_sent,
        binding=binding,
    )


def campaign_share(channel: str, n_campaigns: int) -> int:
    """Even-dispersal slice: the most of `channel` any ONE campaign may send per day.

    So a multi-campaign experiment compares campaigns at ~equal volume instead of
    letting the campaign with the oldest/biggest draft queue eat the shared daily
    cap. Ceil division means slices can sum to slightly over the cap — the global
    `quota()` still binds the true daily total; this only caps any single campaign.
    """
    cap = DAILY_CAPS.get(channel, DEFAULT_DAILY_CAP)
    if n_campaigns <= 1:
        return cap
    return max(1, (cap + n_campaigns - 1) // n_campaigns)


def campaign_daily_sent(channel: str, *, now: datetime | None = None) -> dict[str, int]:
    """{campaign_id: count} of `channel` sends in the trailing 24h, from Postgres.

    Backs the per-campaign fair-share cap. DB-only (the local JSONL ledger carries no
    campaign link); returns {} with no DATABASE_URL or on any error so it never blocks
    a send on a DB hiccup.
    """
    url = Config.database_url
    if not url:
        return {}
    try:
        import psycopg
    except ImportError:
        return {}
    since = (now or _utcnow()) - timedelta(hours=24)
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select l.campaign_id, count(distinct s.draft_id)
                    from sends s
                    join drafts d on d.id = s.draft_id
                    join leads l on l.id = d.lead_id
                    where d.channel = %s
                      and s.sent_at >= %s
                      and s.status = any(%s)
                      and l.campaign_id is not null
                    group by l.campaign_id
                    """,
                    (channel, since, list(_ACTIVE_SEND_STATUSES)),
                )
                return {str(cid): int(cnt) for cid, cnt in cur.fetchall()}
    except Exception:
        return {}


def is_invite_limit_error(exc: BaseException) -> bool:
    """True if `exc` is LinkedIn's "you've hit the invite ceiling" signal.

    LinkedIn returns HTTP 422 with a `cannot_resend_yet` code when the (weekly)
    invitation limit is reached. Treat it as a hard stop — retrying won't help
    until the window rolls over. (A bare 422 from a validation error is *not*
    matched, so we only pause on the real limit signal.)
    """
    resp = getattr(exc, "response", None)
    if resp is None or getattr(resp, "status_code", None) != 422:
        return False
    try:
        body = (resp.text or "").lower()
    except Exception:
        return False
    return "cannot_resend_yet" in body or "limit" in body
