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


# TODO Phase 2: implement set_custom_message, pause_campaign, webhook verification.
