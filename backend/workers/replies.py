"""Reply-fetching worker: poll Heyreach inbox, classify new inbound messages.

Used by both:
  - scripts/pull_replies.py  → writes results to runs/replies.jsonl
  - modal_app.py (cron)      → writes results to Supabase / Postgres

Stays pure (no I/O persistence): returns the new reply records as dicts.
Callers pass in the set of already-seen message ids for idempotency.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Iterable

from clients import heyreach
from workers import reply_triage


def _message_id(msg: dict[str, Any]) -> str:
    """Stable id per message. Falls back to a content+timestamp hash if
    Heyreach doesn't return one."""
    mid = msg.get("id") or msg.get("messageId")
    if mid:
        return str(mid)
    blob = f"{msg.get('sentAt')}|{msg.get('body', '')[:200]}".encode()
    return hashlib.sha1(blob).hexdigest()[:16]


def _find_last_outbound(messages: list[dict[str, Any]], before_idx: int) -> str | None:
    """Walk backward from a reply to find the most recent outbound we sent."""
    for i in range(before_idx - 1, -1, -1):
        m = messages[i]
        if (m.get("direction") or "").lower() == "outbound":
            return m.get("body")
    return None


def _classify_one(
    convo: dict[str, Any],
    msg: dict[str, Any],
    *,
    original_message: str | None,
) -> dict[str, Any] | None:
    """Run the LLM classifier on one inbound message. Returns the assembled
    record, or None if classification fails."""
    try:
        classification = reply_triage.classify_reply(
            reply_body=msg.get("body") or "",
            original_message=original_message,
            lead_name=convo.get("firstName") or convo.get("leadName"),
            lead_role=convo.get("role"),
            lead_company=convo.get("companyName") or convo.get("company"),
        )
    except Exception:  # noqa: BLE001 — caller decides whether to log
        return None

    return {
        "message_id": _message_id(msg),
        "conversation_id": str(convo.get("id") or convo.get("conversationId") or ""),
        "linkedin_url": convo.get("leadLinkedinUrl") or convo.get("linkedinUrl"),
        "lead_name": convo.get("firstName") or convo.get("leadName"),
        "lead_company": convo.get("companyName") or convo.get("company"),
        "campaign_id": convo.get("campaignId"),
        "channel": "linkedin_dm",  # Heyreach inbox = LinkedIn DM
        "body": msg.get("body") or "",
        "original_message": original_message,
        "received_at": msg.get("sentAt") or datetime.now(UTC).isoformat(),
        "classified_at": datetime.now(UTC).isoformat(),
        "intent": classification.get("intent"),
        "sentiment": classification.get("sentiment"),
        "summary": classification.get("summary"),
        "suggested_reply": classification.get("suggested_reply"),
        "next_action": classification.get("next_action"),
    }


def fetch_and_classify_new_replies(
    *,
    seen_message_ids: Iterable[str] = (),
    limit: int = 100,
    only_with_unread: bool = True,
    campaign_id: str | None = None,
) -> list[dict[str, Any]]:
    """Poll the Heyreach inbox; classify any inbound messages we haven't seen.

    Parameters
    ----------
    seen_message_ids:
        Set/iterable of message ids the caller has already processed. These
        are skipped — caller persists their own ledger.
    limit, only_with_unread, campaign_id:
        Forwarded to heyreach.list_inbox_conversations.

    Returns
    -------
    list of reply records (dict). Empty if nothing new.
    """
    seen = set(seen_message_ids)
    payload = heyreach.list_inbox_conversations(
        limit=limit,
        only_with_unread=only_with_unread,
        campaign_ids=[campaign_id] if campaign_id else None,
    )
    conversations = payload.get("items") or payload.get("conversations") or []

    new_records: list[dict[str, Any]] = []
    for convo in conversations:
        convo_id = str(convo.get("id") or convo.get("conversationId") or "")
        if not convo_id:
            continue
        messages = heyreach.list_conversation_messages(convo_id)
        for idx, msg in enumerate(messages):
            if (msg.get("direction") or "").lower() != "inbound":
                continue
            mid = _message_id(msg)
            if mid in seen:
                continue
            record = _classify_one(
                convo, msg, original_message=_find_last_outbound(messages, idx)
            )
            if record is not None:
                new_records.append(record)
                seen.add(mid)
    return new_records
