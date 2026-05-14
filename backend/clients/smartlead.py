"""Smartlead client — email sender. Stub for Phase 2.

API docs: https://api.smartlead.ai/reference
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import Config

BASE = "https://server.smartlead.ai/api/v1"


def _key_param() -> dict[str, str]:
    if not Config.smartlead_api_key:
        raise RuntimeError("SMARTLEAD_API_KEY not set (Phase 2)")
    return {"api_key": Config.smartlead_api_key}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def add_leads_to_campaign(campaign_id: str, leads: list[dict[str, Any]]) -> dict[str, Any]:
    """Push leads into a Smartlead campaign.

    `leads` items: {first_name, last_name, email, company_name, custom_fields}
    """
    payload = {"lead_list": leads}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{BASE}/campaigns/{campaign_id}/leads",
            params=_key_param(),
            json=payload,
        )
        r.raise_for_status()
        return r.json()


def list_campaigns() -> list[dict[str, Any]]:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{BASE}/campaigns", params=_key_param())
        r.raise_for_status()
        return r.json()


# TODO Phase 2: implement update_message_sequence, set_unsubscribe, webhook verification.
