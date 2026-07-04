"""Meta (Facebook/Instagram) lead-ads client — INBOUND side only.

We do NOT create or manage campaigns here: Advantage+ in Meta Ads Manager runs the ads,
the creative, and the A/B testing (the deep-research verdict — own the ingestion, not the
ad management). This module's whole job is to pull the full field set of a lead the moment
its form is submitted, given the leadgen_id delivered by the webhook.

Graph API: GET /{leadgen_id}?access_token=<page token>. Requires a long-lived Page access
token with the `leads_retrieval` permission on the Page the form belongs to.
"""

from __future__ import annotations

from typing import Any

import httpx

from config import Config

_GRAPH = "https://graph.facebook.com/v21.0"


def fetch_lead(leadgen_id: str, *, access_token: str | None = None) -> dict[str, Any]:
    """Fetch one lead's answers from the Graph API.

    Returns a normalized dict: {id, created_time, form_id, ad_id, campaign_id (Meta's),
    fields: {name: value}, raw}. Raises on HTTP error or missing token so the caller can
    record the failure instead of silently dropping a paid lead.
    """
    token = access_token or Config.meta_page_access_token
    if not token:
        raise RuntimeError("META_PAGE_ACCESS_TOKEN not set — cannot fetch lead")

    params = {
        "access_token": token,
        "fields": "id,created_time,ad_id,form_id,campaign_id,field_data",
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{_GRAPH}/{leadgen_id}", params=params)
        r.raise_for_status()
        data = r.json()

    # field_data is [{name, values:[...]}, ...] — flatten to {name: first value}.
    fields: dict[str, str] = {}
    for f in data.get("field_data", []) or []:
        name = f.get("name")
        vals = f.get("values") or []
        if name:
            fields[name] = vals[0] if vals else ""

    return {
        "id": data.get("id") or leadgen_id,
        "created_time": data.get("created_time"),
        "form_id": data.get("form_id"),
        "ad_id": data.get("ad_id"),
        "meta_campaign_id": data.get("campaign_id"),
        "fields": fields,
        "raw": data,
    }


# Meta lead forms use stable field NAMES for the standard questions; custom questions get
# operator-defined names. These are the common built-ins we map to lead columns.
_NAME_KEYS = ("full_name", "name", "first_name")
_EMAIL_KEYS = ("email", "work_email")
_PHONE_KEYS = ("phone_number", "phone", "mobile")
_COMPANY_KEYS = ("company_name", "company", "business_name")


def _first(fields: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if fields.get(k):
            return fields[k]
    return None


def map_fields(fields: dict[str, str]) -> dict[str, str | None]:
    """Pull the standard identity fields out of a form's answers (best-effort)."""
    first = fields.get("first_name")
    last = fields.get("last_name")
    name = _first(fields, _NAME_KEYS) or (
        f"{first} {last}".strip() if (first or last) else None
    )
    return {
        "name": name,
        "email": _first(fields, _EMAIL_KEYS),
        "phone": _first(fields, _PHONE_KEYS),
        "company": _first(fields, _COMPANY_KEYS),
    }
