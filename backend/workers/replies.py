"""Reply-fetching worker: poll Unipile (LinkedIn chats + email), classify inbound.

Used by both:
  - scripts/pull_replies.py  → writes results to runs/replies.jsonl
  - modal_app.py (cron + webhook) → writes results to Supabase / Postgres

Stays pure (no I/O persistence): returns the new reply records as dicts.
Callers pass in the set of already-seen message ids for idempotency.

Unipile message shapes:
  * LinkedIn chat message: {id, text, timestamp, is_sender (0|1), sender_id, …}
    is_sender == 0 ⇒ inbound (the prospect). 1 ⇒ outbound (us).
  * Email: {id, from_attendee:{identifier,display_name}, subject, body,
    body_plain, date, read_date (null ⇒ unread), …}
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Iterable

from clients import unipile
from workers import reply_triage


def _stable_id(primary: Any, *fallback_parts: Any) -> str:
    """Provider message id when present, else a content hash for idempotency."""
    if primary:
        return str(primary)
    blob = "|".join(str(p) for p in fallback_parts).encode()
    return hashlib.sha1(blob).hexdigest()[:16]


def _is_inbound(msg: dict[str, Any]) -> bool:
    """A LinkedIn chat message is inbound (from the prospect) when is_sender == 0."""
    flag = msg.get("is_sender")
    if flag is None:
        return False
    try:
        return int(flag) == 0
    except (TypeError, ValueError):
        return not bool(flag)


def _find_last_outbound(messages: list[dict[str, Any]], before_idx: int) -> str | None:
    """Walk backward from a reply to find the most recent message we sent."""
    for i in range(before_idx - 1, -1, -1):
        m = messages[i]
        if not _is_inbound(m) and (m.get("text") or m.get("body")):
            return m.get("text") or m.get("body")
    return None


def _linkedin_url_from_chat(chat: dict[str, Any]) -> str | None:
    """Best-effort recovery of the prospect's profile URL from a chat object.

    Unipile keys vary; if we can find a public identifier we rebuild the URL,
    otherwise return None (the reply persists as an orphan — lead_id is
    nullable downstream).
    """
    ident = (
        chat.get("attendee_public_identifier")
        or chat.get("public_identifier")
        or chat.get("attendee_provider_id")
    )
    if ident and not str(ident).startswith("http"):
        # provider_id values are opaque ACoAA… urns, not usable as /in/ slugs.
        if str(ident).startswith("ACoA") or "," in str(ident):
            return None
        return f"https://www.linkedin.com/in/{ident}"
    return ident or None


def classify_message(
    *,
    channel: str,
    external_id: str,
    text: str,
    linkedin_url: str | None = None,
    lead_name: str | None = None,
    lead_company: str | None = None,
    lead_role: str | None = None,
    original_message: str | None = None,
    received_at: str | None = None,
) -> dict[str, Any] | None:
    """Run the LLM classifier on one inbound message → assembled reply record.

    Returns None if classification fails (caller decides whether to log/skip).
    Shared by the poller and the webhook receiver so both produce identical rows.
    """
    try:
        classification = reply_triage.classify_reply(
            reply_body=text or "",
            original_message=original_message,
            lead_name=lead_name,
            lead_role=lead_role,
            lead_company=lead_company,
        )
    except Exception:  # noqa: BLE001 — caller decides whether to log
        return None

    return {
        "message_id": external_id,
        "linkedin_url": linkedin_url,
        "lead_name": lead_name,
        "lead_company": lead_company,
        "channel": channel,
        "body": text or "",
        "original_message": original_message,
        "received_at": received_at or datetime.now(UTC).isoformat(),
        "classified_at": datetime.now(UTC).isoformat(),
        "intent": classification.get("intent"),
        "sentiment": classification.get("sentiment"),
        "summary": classification.get("summary"),
        "suggested_reply": classification.get("suggested_reply"),
        "next_action": classification.get("next_action"),
    }


def _linkedin_replies(seen: set[str], limit: int, unread_only: bool) -> list[dict[str, Any]]:
    """Scan LinkedIn chats; classify inbound messages we haven't seen."""
    records: list[dict[str, Any]] = []
    chats = unipile.list_chats(unread_only=unread_only, limit=limit)
    for chat in chats:
        chat_id = str(chat.get("id") or chat.get("chat_id") or "")
        if not chat_id:
            continue
        lead_name = chat.get("name")
        linkedin_url = _linkedin_url_from_chat(chat)
        messages = unipile.list_chat_messages(chat_id)
        messages.sort(key=lambda m: str(m.get("timestamp") or ""))
        for idx, msg in enumerate(messages):
            if not _is_inbound(msg):
                continue
            mid = _stable_id(msg.get("id"), msg.get("timestamp"), (msg.get("text") or "")[:200])
            if mid in seen:
                continue
            record = classify_message(
                channel="linkedin_dm",
                external_id=mid,
                text=msg.get("text") or "",
                linkedin_url=linkedin_url,
                lead_name=lead_name,
                original_message=_find_last_outbound(messages, idx),
                received_at=msg.get("timestamp"),
            )
            if record is not None:
                records.append(record)
                seen.add(mid)
    return records


def _email_replies(seen: set[str], limit: int, unread_only: bool) -> list[dict[str, Any]]:
    """Scan the email inbox; classify inbound emails we haven't seen."""
    records: list[dict[str, Any]] = []
    emails = unipile.list_emails(role="inbox", limit=limit)
    for email in emails:
        if unread_only and email.get("read_date"):
            continue
        from_attendee = email.get("from_attendee") or {}
        body = email.get("body_plain") or email.get("body") or ""
        mid = _stable_id(email.get("id"), email.get("date"), (body or "")[:200])
        if mid in seen:
            continue
        record = classify_message(
            channel="email",
            external_id=mid,
            text=body,
            lead_name=from_attendee.get("display_name"),
            received_at=email.get("date"),
        )
        if record is not None:
            records.append(record)
            seen.add(mid)
    return records


def fetch_and_classify_new_replies(
    *,
    seen_message_ids: Iterable[str] = (),
    limit: int = 100,
    only_with_unread: bool = True,
    campaign_id: str | None = None,  # noqa: ARG001 — kept for caller back-compat (Unipile has no campaigns)
) -> list[dict[str, Any]]:
    """Poll Unipile (LinkedIn + email); classify inbound messages we haven't seen.

    Parameters
    ----------
    seen_message_ids:
        Iterable of message ids the caller has already processed — skipped.
    limit, only_with_unread:
        Forwarded to the Unipile list calls.
    campaign_id:
        Unused (Unipile has no campaign concept); accepted so existing callers
        don't break.

    Returns
    -------
    list of reply records (dict). Empty if nothing new.
    """
    seen = set(seen_message_ids)
    records: list[dict[str, Any]] = []
    records.extend(_linkedin_replies(seen, limit, only_with_unread))
    records.extend(_email_replies(seen, limit, only_with_unread))
    return records
