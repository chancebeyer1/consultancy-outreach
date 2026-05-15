"""Heyreach client — LinkedIn sender. Stub for Phase 2.

API docs: https://help.heyreach.io/en/articles/9220325-public-api-documentation
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

BASE = "https://api.heyreach.io/api/public"


def _headers() -> dict[str, str]:
    if not Config.heyreach_api_key:
        raise RuntimeError("HEYREACH_API_KEY not set (Phase 2)")
    return {"X-API-KEY": Config.heyreach_api_key, "accept": "application/json"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def add_leads_to_campaign(campaign_id: str, leads: list[dict[str, Any]]) -> dict[str, Any]:
    """Push approved leads into a Heyreach campaign queue.

    `leads` items: {linkedin_url, first_name, last_name, company_name, custom_fields}
    """
    payload = {"campaignId": campaign_id, "leads": leads}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{BASE}/lead/AddLeadsToCampaign", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


def list_campaigns() -> list[dict[str, Any]]:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(f"{BASE}/campaign/GetAll", headers=_headers(), json={})
        r.raise_for_status()
        return r.json().get("items", [])


# ---------------------------------------------------------------------------
# Inbox / replies
# ---------------------------------------------------------------------------
#
# Heyreach's inbox endpoints expose per-conversation message threads. We poll
# them to surface inbound replies for our reply-triage pipeline.
#
# Endpoint shapes below match the public API as of 2025-Q2. If a request 404s
# after a Heyreach release, check the dashboard's Settings → API page for the
# latest paths and update accordingly.


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def list_inbox_conversations(
    *,
    limit: int = 100,
    offset: int = 0,
    only_with_unread: bool = True,
    campaign_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch conversations from the Heyreach inbox.

    Returns the raw payload: typically {items: [...], total: N}. Each item has
    `id`, `leadLinkedinUrl`, `firstName`, `lastName`, `companyName`,
    `lastMessageAt`, `unreadCount`, `campaignId`.
    """
    payload: dict[str, Any] = {"limit": limit, "offset": offset}
    if only_with_unread:
        payload["onlyWithUnread"] = True
    if campaign_ids:
        payload["campaignIds"] = campaign_ids
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{BASE}/inbox/GetConversations",
            headers=_headers(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def list_conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    """Fetch all messages for one Heyreach conversation.

    Each message has at minimum: `id`, `direction` ("inbound"|"outbound"),
    `body`, `sentAt`. We use direction to separate the prospect's reply
    from our outbound that prompted it.
    """
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{BASE}/inbox/GetConversationMessages",
            headers=_headers(),
            json={"conversationId": conversation_id},
        )
        r.raise_for_status()
        data = r.json()
        # Heyreach returns either a list or {items: [...]} depending on
        # endpoint version. Normalize.
        return data.get("items", data) if isinstance(data, dict) else data


def mark_conversation_read(conversation_id: str) -> None:
    """Mark a Heyreach conversation as read. Best-effort — swallow errors."""
    try:
        with httpx.Client(timeout=15.0) as client:
            client.post(
                f"{BASE}/inbox/MarkAsRead",
                headers=_headers(),
                json={"conversationId": conversation_id},
            )
    except Exception:  # noqa: BLE001
        pass


# TODO Phase 2: webhook signature verification (we currently rely on polling).
