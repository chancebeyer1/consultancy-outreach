"""Deal revival — draft a nudge when an open deal's conversation goes quiet.

Scans open deals (interested / call_booked / proposal_sent) whose last touch — deal update,
inbound reply, or outbound send — is older than the stage's quiet window, and drafts ONE short
re-engagement message in the campaign owner's voice (prompts/draft_revival.md). The draft lands
in scheduled_replies with status='draft', kind='revival': NOTHING sends until the operator
approves it on /replies (draft -> pending), after which the existing scheduled sender fires it.

Guardrails: lifetime cap of REVIVAL_MAX_SENT sent nudges per lead, REVIVAL_SPACING_DAYS between
revival drafts, skip while anything is already queued/scheduled for the lead, and the model may
itself decide to skip (e.g. "they said after the 20th" and it isn't the 20th). The prompt bans
the "just checking in" family outright — a nudge must carry a new specific thought.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import claude
from config import Config, require
from operator_profile import operator_bio
from prompts_loader import load_prompt, system_prefix
from workers.draft import _humanize

# Days of silence before a deal in this stage earns a nudge. call_booked gets longer rope —
# a booked call means the ball is nominally in motion; nudging early reads as anxious.
QUIET_DAYS = {"interested": 5, "call_booked": 10, "proposal_sent": 5}
REVIVAL_MAX_SENT = 2  # lifetime cap of SENT revival nudges per lead — then let it die with dignity
REVIVAL_SPACING_DAYS = 14  # min days between revival drafts for the same lead (any status)
MAX_BODY_CHARS = 700  # hard sanity ceiling; prompt asks for ≤60 words


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _candidates(cur, scan_limit: int) -> list[dict[str, Any]]:
    """Open deals whose thread went quiet past their stage window, minus anything already
    queued, recently nudged, or at the lifetime nudge cap. Oldest silence first."""
    cur.execute(
        """
        select d.id, d.lead_id, d.stage, d.notes, d.next_action,
               l.name, l.role, l.headline, l.company, l.email, l.provider_id,
               l.accepted_at, l.user_id, l.campaign_id,
               greatest(
                   d.updated_at,
                   coalesce((select max(r.received_at) from replies r
                             where r.lead_id = d.lead_id), d.created_at),
                   coalesce((select max(sr.sent_at) from scheduled_replies sr
                             where sr.lead_id = d.lead_id and sr.sent_at is not null), d.created_at),
                   coalesce((select max(sn.sent_at) from sends sn
                             join drafts dr on dr.id = sn.draft_id
                             where dr.lead_id = d.lead_id), d.created_at)
               ) as last_touch
        from deals d
        join leads l on l.id = d.lead_id
        where d.stage in ('interested', 'call_booked', 'proposal_sent')
          and not exists (select 1 from scheduled_replies q
                          where q.lead_id = d.lead_id and q.status in ('draft', 'pending'))
          and not exists (select 1 from scheduled_replies q
                          where q.lead_id = d.lead_id and q.kind = 'revival'
                            and q.created_at > now() - make_interval(days => %s))
          and (select count(*) from scheduled_replies q
               where q.lead_id = d.lead_id and q.kind = 'revival' and q.status = 'sent') < %s
        order by last_touch asc
        limit %s
        """,
        (REVIVAL_SPACING_DAYS, REVIVAL_MAX_SENT, scan_limit),
    )
    cols = [
        "deal_id", "lead_id", "stage", "notes", "next_action", "name", "role", "headline",
        "company", "email", "provider_id", "accepted_at", "user_id", "campaign_id", "last_touch",
    ]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _thread_context(cur, lead_id) -> dict[str, Any]:
    """Latest inbound reply + latest outbound message for the lead (either a sequence send or a
    previously sent scheduled reply — whichever is newer)."""
    cur.execute(
        "select id, body, chat_id, received_at from replies "
        "where lead_id = %s order by received_at desc nulls last limit 1",
        (lead_id,),
    )
    r = cur.fetchone()
    reply = {"id": r[0], "body": r[1], "chat_id": r[2], "received_at": r[3]} if r else {}

    cur.execute(
        "select coalesce(dr.edited_body, dr.body), sn.sent_at from sends sn "
        "join drafts dr on dr.id = sn.draft_id "
        "where dr.lead_id = %s order by sn.sent_at desc limit 1",
        (lead_id,),
    )
    seq = cur.fetchone()
    cur.execute(
        "select body, sent_at from scheduled_replies "
        "where lead_id = %s and status = 'sent' order by sent_at desc limit 1",
        (lead_id,),
    )
    sched = cur.fetchone()
    ours = None
    if seq and sched:
        ours = seq if (seq[1] and sched[1] and seq[1] >= sched[1]) else sched
    else:
        ours = seq or sched
    return {"reply": reply, "our_last": ours[0] if ours else None}


def _pick_target(cand: dict[str, Any], chat_id: str | None) -> tuple[str, str | None, str | None] | None:
    """(channel, chat_id, provider_id) for the nudge, or None when the lead is unreachable.
    Prefer the existing LinkedIn chat; fall back to a DM by provider id (only once they've
    accepted the connection); last resort email."""
    if chat_id:
        return ("linkedin_dm", chat_id, cand.get("provider_id"))
    if cand.get("provider_id") and cand.get("accepted_at"):
        return ("linkedin_dm", None, cand["provider_id"])
    if cand.get("email"):
        return ("email", None, None)
    return None


def _body_ok(body: str) -> bool:
    """Same spirit as the connect-note sanity gate: reject meta/refusal leakage before it can
    ever reach an approve button."""
    if not body or not (10 <= len(body) <= MAX_BODY_CHARS):
        return False
    lowered = body.lower()
    banned = ("as an ai", "variant", "skip", "[insert", "just checking in", "just following up",
              "circling back", "bumping this")
    return not any(b in lowered for b in banned)


def draft_revivals(*, limit: int = 5, time_budget_s: float = 240.0, dry_run: bool = False) -> dict:
    """Draft up to `limit` revival nudges. Time-budgeted; leftover candidates defer to the next
    run. Returns counts; never raises for a single bad candidate."""
    deadline = time.monotonic() + time_budget_s
    drafted = 0
    skipped_quiet_window = 0
    skipped_model = 0
    skipped_target = 0
    failed = 0
    deferred = 0

    with _connect() as conn, conn.cursor() as cur:
        candidates = _candidates(cur, scan_limit=40)

    from datetime import UTC, datetime

    now = datetime.now(UTC)
    due: list[dict[str, Any]] = []
    for cand in candidates:
        window = QUIET_DAYS.get(cand["stage"], 7)
        last_touch = cand["last_touch"]
        quiet_days = (now - last_touch).days if last_touch else 999
        if quiet_days < window:
            skipped_quiet_window += 1
            continue
        cand["days_quiet"] = quiet_days
        due.append(cand)

    for i, cand in enumerate(due):
        if drafted >= limit:
            deferred = len(due) - i
            break
        if time.monotonic() > deadline:
            deferred = len(due) - i
            break
        try:
            with _connect() as conn, conn.cursor() as cur:
                ctx = _thread_context(cur, cand["lead_id"])
            target = _pick_target(cand, (ctx.get("reply") or {}).get("chat_id"))
            if target is None:
                skipped_target += 1
                continue
            channel, chat_id, provider_id = target

            campaign = None
            if cand.get("campaign_id"):
                try:
                    from campaigns_loader import load_campaign

                    campaign = load_campaign(str(cand["campaign_id"]))
                except Exception:  # noqa: BLE001
                    campaign = None

            reply = ctx.get("reply") or {}
            received = reply.get("received_at")
            payload = json.dumps(
                {
                    "lead_name": cand.get("name"),
                    "lead_role": cand.get("role") or cand.get("headline"),
                    "lead_company": cand.get("company"),
                    "deal_stage": cand["stage"],
                    "deal_notes": (cand.get("notes") or "")[:500],
                    "next_action": (cand.get("next_action") or "")[:200],
                    "days_quiet": cand["days_quiet"],
                    "their_last_message": (reply.get("body") or "")[:800],
                    "their_last_message_date": received.date().isoformat() if received else None,
                    "our_last_message": (ctx.get("our_last") or "")[:800],
                    "today": now.date().isoformat(),
                    "operator_background": operator_bio(
                        str(cand["user_id"]) if cand.get("user_id") else None
                    ),
                    "landing_url": campaign.landing_url if campaign else Config.landing_url,
                    "calcom_url": campaign.calcom_url if campaign else Config.calcom_url,
                },
                default=str,
                indent=2,
            )
            out = claude.call_json(
                instruction=load_prompt("draft_revival"),
                user_payload=payload,
                system_prefix=system_prefix(campaign) if campaign else None,
                model=Config.claude_model_reason,
                max_tokens=600,
            )
            if out.get("skip") or not out.get("body"):
                skipped_model += 1
                continue
            body = _humanize(str(out["body"]))
            if not _body_ok(body):
                skipped_model += 1
                continue
            if dry_run:
                drafted += 1
                continue
            with _connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    insert into scheduled_replies
                        (lead_id, reply_id, channel, chat_id, provider_id, body,
                         due_at, status, kind)
                    values (%s, %s, %s, %s, %s, %s, now() + interval '1 day', 'draft', 'revival')
                    """,
                    (cand["lead_id"], reply.get("id"), channel, chat_id, provider_id, body),
                )
            drafted += 1
            try:
                from activity import log as _alog

                _alog(
                    "revival_drafted", source="worker",
                    channel="linkedin" if channel.startswith("linkedin") else "email",
                    lead_id=str(cand["lead_id"]),
                    summary=f"Revival nudge drafted after {cand['days_quiet']} quiet days "
                    f"({cand['stage']})",
                    meta={"deal_id": str(cand["deal_id"])},
                )
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001 — one bad candidate must not kill the scan
            failed += 1

    return {
        "candidates": len(candidates),
        "past_quiet_window": len(due),
        "drafted": drafted,
        "skipped_quiet_window": skipped_quiet_window,
        "skipped_model": skipped_model,
        "skipped_no_target": skipped_target,
        "failed": failed,
        "deferred": deferred,
        "dry_run": dry_run,
    }


if __name__ == "__main__":
    print(json.dumps(draft_revivals(dry_run=True), default=str))
