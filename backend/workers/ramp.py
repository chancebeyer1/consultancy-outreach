"""Auto-ramp per-account LinkedIn invite caps — warm a fresh account up without a human
babysitting the number.

A profile opts in by having li_ramp_target set (e.g. 20). Its li_daily_cap then walks
the STEPS ladder (5 → 10 → 15 → 20) automatically, one step at a time, gated on the
account actually being healthy at the current step:

promote (next step) only when ALL hold:
  - >= MIN_DAYS_AT_STEP days since the last cap change (li_cap_updated_at)
  - >= MIN_SENDS_AT_STEP connects actually sent since the last change (calendar time
    with no activity proves nothing)
  - accept rate over the trailing 30d >= MIN_ACCEPT_RATE once the sample is big enough
    (a low accept rate is itself a spam signal to LinkedIn — growing volume on top of
    it compounds the risk)
  - pending (unaccepted) invites below PENDING_HOLD — LinkedIn throttles on the pending
    PILE, not just send rate
  - no active linkedin provider cooldown (a recent 422 means we're already on thin ice)

step DOWN one step when the pending pile crosses PENDING_STEP_DOWN.

Any change stamps li_cap_updated_at, which doubles as the rate limiter: at most one
change per account per ~20h no matter how often the hourly dispatcher calls this.
li_weekly_cap tracks daily*5 (LinkedIn's real limit is weekly; daily smooths it).
Owner + admin get an email on every change. Manual override: set li_daily_cap by hand
and the ladder resumes from there next cycle; clear li_ramp_target to stop ramping.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

STEPS = [5, 10, 15, 20]
MIN_DAYS_AT_STEP = 10
MIN_SENDS_AT_STEP = 20
MIN_ACCEPT_RATE = 0.10
ACCEPT_SAMPLE_MIN = 20  # below this many 30d sends, the accept-rate gate abstains
PENDING_HOLD = 100      # pending invites at/above this: no promotion
PENDING_STEP_DOWN = 200  # pending invites at/above this: drop a step
MIN_HOURS_BETWEEN_CHANGES = 20.0


def _next_step(current: int, target: int) -> int | None:
    for s in STEPS:
        if s > current:
            return min(s, target)
    return None


def _prev_step(current: int) -> int:
    below = [s for s in STEPS if s < current]
    return below[-1] if below else STEPS[0]


def _notify_change(email: str | None, name: str | None, old: int, new: int, reason: str) -> None:
    from config import Config
    from workers.email_sender import notify

    subject = f"LinkedIn invite cap {'raised' if new > old else 'LOWERED'}: {old} → {new}/day"
    body = (
        f"Hi {name or 'there'},\n\n"
        f"The outreach system adjusted your LinkedIn connection-request cap: "
        f"{old}/day → {new}/day ({new * 5}/week).\n\nWhy: {reason}\n\n"
        f"This is automatic account warm-up; no action needed."
    )
    recipients = {e.strip().lower(): e for e in (email, Config.notify_email) if e}
    for addr in recipients.values():
        try:
            notify(subject=subject, body=body, to_email=addr)
        except Exception:  # noqa: BLE001 — a notify hiccup must not block the ramp
            pass


def auto_ramp(*, dry_run: bool = False) -> dict[str, Any]:
    """Evaluate every ramping profile once; apply at most one cap change each."""
    import psycopg

    from clients import unipile
    from config import require

    now = datetime.now(UTC)
    results: list[dict[str, Any]] = []

    conn = psycopg.connect(require("DATABASE_URL"))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id, email, name, unipile_account_id, li_daily_cap, "
                "li_ramp_target, li_cap_updated_at from profiles "
                "where li_ramp_target is not null and unipile_account_id is not null"
            )
            profiles = cur.fetchall()

            # One shared linkedin cooldown check (cooldowns are channel-global today).
            cur.execute(
                "select 1 from provider_cooldowns "
                "where key like 'linkedin%' and blocked_until > now() limit 1"
            )
            linkedin_cooling = cur.fetchone() is not None

            for uid, email, name, acct, cap, target, changed_at in profiles:
                current = cap or STEPS[0]
                entry: dict[str, Any] = {"profile": str(uid), "cap": current, "target": target}
                results.append(entry)

                since_change_h = (
                    (now - changed_at).total_seconds() / 3600 if changed_at else None
                )
                if since_change_h is not None and since_change_h < MIN_HOURS_BETWEEN_CHANGES:
                    entry["hold"] = "changed recently"
                    continue

                # Pending pile — the strongest step-down signal we have.
                try:
                    pending = len(unipile.list_sent_invitations(account_id=acct))
                except Exception:  # noqa: BLE001 — unreadable pending: act on nothing
                    pending = None
                entry["pending"] = pending

                if pending is not None and pending >= PENDING_STEP_DOWN and current > STEPS[0]:
                    new = _prev_step(current)
                    entry["change"] = f"{current} -> {new} (pending {pending})"
                    if not dry_run:
                        cur.execute(
                            "update profiles set li_daily_cap = %s, li_weekly_cap = %s, "
                            "li_cap_updated_at = now() where id = %s",
                            (new, new * 5, uid),
                        )
                        conn.commit()
                        _notify_change(
                            email, name, current, new,
                            f"{pending} invites are sitting unaccepted — easing off so "
                            f"LinkedIn doesn't throttle the account.",
                        )
                    continue

                if current >= (target or 0):
                    entry["hold"] = "at target"
                    continue
                if linkedin_cooling:
                    entry["hold"] = "linkedin cooldown active"
                    continue
                if pending is not None and pending >= PENDING_HOLD:
                    entry["hold"] = f"pending {pending} >= {PENDING_HOLD}"
                    continue

                # Activity + tenure at the current step.
                since = changed_at or now - timedelta(days=36500)
                if changed_at and (now - changed_at) < timedelta(days=MIN_DAYS_AT_STEP):
                    entry["hold"] = f"only {(now - changed_at).days}d at step"
                    continue
                cur.execute(
                    """
                    select count(*) from sends s
                    join drafts d on d.id = s.draft_id
                    join leads l on l.id = d.lead_id
                    where l.user_id = %s and d.channel = 'linkedin_connect'
                      and s.status = 'sent' and s.sent_at >= %s
                    """,
                    (uid, since),
                )
                sends_since = cur.fetchone()[0]
                if sends_since < MIN_SENDS_AT_STEP:
                    entry["hold"] = f"only {sends_since} connects sent at step"
                    continue

                # Accept rate, trailing 30d (abstain on a small sample).
                cur.execute(
                    """
                    select
                      (select count(*) from sends s
                         join drafts d on d.id = s.draft_id
                         join leads l on l.id = d.lead_id
                         where l.user_id = %s and d.channel = 'linkedin_connect'
                           and s.status = 'sent' and s.sent_at >= now() - interval '30 days'),
                      (select count(*) from leads
                         where user_id = %s and accepted_at >= now() - interval '30 days')
                    """,
                    (uid, uid),
                )
                sent_30d, accepted_30d = cur.fetchone()
                if sent_30d >= ACCEPT_SAMPLE_MIN and accepted_30d / sent_30d < MIN_ACCEPT_RATE:
                    entry["hold"] = f"accept rate {accepted_30d}/{sent_30d} below floor"
                    continue

                new = _next_step(current, target)
                if new is None:
                    entry["hold"] = "at ladder top"
                    continue
                entry["change"] = f"{current} -> {new}"
                if not dry_run:
                    cur.execute(
                        "update profiles set li_daily_cap = %s, li_weekly_cap = %s, "
                        "li_cap_updated_at = now() where id = %s",
                        (new, new * 5, uid),
                    )
                    conn.commit()
                    _notify_change(
                        email, name, current, new,
                        f"{sends_since} invites sent over {MIN_DAYS_AT_STEP}+ days at "
                        f"{current}/day with a healthy account — stepping up.",
                    )
    finally:
        conn.close()

    return {"profiles": len(results), "results": results, "dry_run": dry_run}
