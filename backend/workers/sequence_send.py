"""DB-aware sequence executor.

Reads sends + replies state from Postgres, asks workers/sequence which leads
have a step due, finds the approved-but-not-yet-sent draft for that step,
and pushes it via Heyreach.

Idempotency: we only push a draft that doesn't already have a `sends` row.
After a successful push we:
  - INSERT into sends (draft_id, provider, external_id, sent_at, status)
  - UPDATE drafts SET status='sent', decided_at=now() WHERE id=draft_id
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from clients import heyreach
from config import require
from workers.sequence import ActionableLead, determine_next_action


def _connect():
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e
    return psycopg.connect(require("DATABASE_URL"), autocommit=False)


def _campaign_id_for(channel: str) -> str | None:
    """Heyreach campaign id for a sequence step. Picks the channel-specific
    env var if present, falls back to HEYREACH_CAMPAIGN_DEFAULT."""
    env_key = f"HEYREACH_CAMPAIGN_{channel.upper()}"
    return os.environ.get(env_key) or os.environ.get("HEYREACH_CAMPAIGN_DEFAULT")


def _load_state() -> tuple[dict, dict, dict]:
    """Load the three slices the sequence engine needs.

    Returns (sends_by_lead, replies_by_lead, leads_by_id) where each value is
    keyed by lead_id (string).
    """
    sends_by_lead: dict[str, list[dict]] = {}
    replies_by_lead: dict[str, list[dict]] = {}
    leads_by_id: dict[str, dict] = {}

    conn = _connect()
    try:
        with conn.cursor() as cur:
            # All successful sends, joined with the draft channel
            cur.execute(
                """
                select s.draft_id, d.lead_id, d.channel, s.sent_at
                from sends s
                join drafts d on d.id = s.draft_id
                where s.status in ('queued', 'sent', 'delivered')
                """
            )
            for draft_id, lead_id, channel, sent_at in cur.fetchall():
                sends_by_lead.setdefault(str(lead_id), []).append(
                    {"draft_id": str(draft_id), "channel": channel, "sent_at": sent_at}
                )

            # All replies (we only care that *any* reply exists after the last send)
            cur.execute("select lead_id, received_at from replies where lead_id is not null")
            for lead_id, received_at in cur.fetchall():
                replies_by_lead.setdefault(str(lead_id), []).append(
                    {"received_at": received_at}
                )

            # Lead metadata for Heyreach push
            ids = list(sends_by_lead.keys())
            if ids:
                cur.execute(
                    "select id, linkedin_url, name, company from leads where id = any(%s::uuid[])",
                    (ids,),
                )
                for lid, url, name, company in cur.fetchall():
                    first, _, last = (name or "").partition(" ")
                    leads_by_id[str(lid)] = {
                        "linkedin_url": url,
                        "first_name": first or None,
                        "last_name": last or None,
                        "company": company,
                    }
    finally:
        conn.close()

    return sends_by_lead, replies_by_lead, leads_by_id


def _next_draft_for(
    cur,
    *,
    lead_id: str,
    channel: str,
) -> dict | None:
    """Find an approved draft for (lead_id, channel) that hasn't been sent.

    Returns {id, body, edited_body, hook} or None.
    """
    cur.execute(
        """
        select d.id, d.body, d.edited_body, d.hook
        from drafts d
        left join sends s on s.draft_id = d.id
        where d.lead_id = %s
          and d.channel = %s
          and d.status = 'approved'
          and s.id is null
        order by d.step_index asc
        limit 1
        """,
        (lead_id, channel),
    )
    row = cur.fetchone()
    if not row:
        return None
    draft_id, body, edited_body, hook = row
    return {
        "id": str(draft_id),
        "body": edited_body or body,
        "hook": hook,
    }


def _push_to_heyreach(
    actionable: ActionableLead,
    lead: dict,
    draft: dict,
    campaign_id: str,
) -> dict[str, Any]:
    """Push one approved draft to Heyreach. Returns the API response."""
    hook_ref = ""
    if isinstance(draft.get("hook"), dict):
        hook_ref = draft["hook"].get("reference") or ""

    leads_payload = [
        {
            "linkedin_url": lead.get("linkedin_url") or "",
            "first_name": lead.get("first_name") or "",
            "last_name": lead.get("last_name") or "",
            "company_name": lead.get("company") or "",
            "custom_fields": {
                "custom_body": draft["body"],
                "custom_hook": hook_ref,
            },
        }
    ]
    return heyreach.add_leads_to_campaign(campaign_id, leads_payload)


def _record_send(draft_id: str, response: dict[str, Any]) -> None:
    """Mark a draft as sent and add the corresponding sends row."""
    external_id = (
        response.get("id") or response.get("messageId") or response.get("requestId")
    )
    now = datetime.now(UTC)
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into sends (draft_id, provider, external_id, sent_at, status)
                    values (%s, 'heyreach', %s, %s, 'queued')
                    """,
                    (draft_id, str(external_id) if external_id else None, now),
                )
                cur.execute(
                    "update drafts set status = 'sent', decided_at = %s where id = %s",
                    (now, draft_id),
                )
    finally:
        conn.close()


def progress_sequences(
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """One pass through the sequence engine. Returns a summary dict.

    Suitable for a cron tick; idempotent across runs.
    """
    sends_by_lead, replies_by_lead, leads_by_id = _load_state()
    actionable_list = determine_next_action(
        sends_by_lead=sends_by_lead,
        replies_by_lead=replies_by_lead,
    )
    actionable_list = [a for a in actionable_list if a.is_overdue]
    if limit is not None:
        actionable_list = actionable_list[:limit]

    pushed: list[dict[str, Any]] = []
    blocked_no_draft: list[str] = []
    blocked_no_campaign: list[str] = []
    failed: list[dict[str, Any]] = []

    if not actionable_list:
        return {
            "actionable": 0,
            "pushed": 0,
            "blocked_no_draft": 0,
            "blocked_no_campaign": 0,
            "failed": 0,
            "dry_run": dry_run,
        }

    # One DB session for the read-side; writes still spawn their own
    # connections so each send commits independently.
    conn = _connect()
    try:
        for a in actionable_list:
            lead = leads_by_id.get(a.lead_id)
            if not lead or not lead.get("linkedin_url"):
                blocked_no_draft.append(a.lead_id)
                continue
            with conn.cursor() as cur:
                draft = _next_draft_for(cur, lead_id=a.lead_id, channel=a.next_channel)
            if not draft:
                blocked_no_draft.append(a.lead_id)
                continue

            campaign_id = _campaign_id_for(a.next_channel)
            if not campaign_id:
                blocked_no_campaign.append(a.lead_id)
                continue

            if dry_run:
                pushed.append(
                    {
                        "lead_id": a.lead_id,
                        "channel": a.next_channel,
                        "draft_id": draft["id"],
                        "would_push_to_campaign": campaign_id,
                    }
                )
                continue

            try:
                response = _push_to_heyreach(a, lead, draft, campaign_id)
                _record_send(draft["id"], response)
                pushed.append(
                    {"lead_id": a.lead_id, "channel": a.next_channel, "draft_id": draft["id"]}
                )
            except Exception as e:  # noqa: BLE001
                failed.append({"lead_id": a.lead_id, "error": str(e)})
    finally:
        conn.close()

    return {
        "actionable": len(actionable_list),
        "pushed": len(pushed),
        "blocked_no_draft": len(blocked_no_draft),
        "blocked_no_campaign": len(blocked_no_campaign),
        "failed": len(failed),
        "details": {
            "pushed": pushed,
            "blocked_no_draft": blocked_no_draft,
            "blocked_no_campaign": blocked_no_campaign,
            "failed": failed,
        },
        "dry_run": dry_run,
    }
