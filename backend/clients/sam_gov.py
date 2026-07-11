"""SAM.gov Get Opportunities API — US federal contract opportunities.

The one gov source a solo/small LLC can realistically win, via small-business set-asides.
Free public API (api.sam.gov), key from your SAM.gov account. IMPORTANT quota: the free
per-account tier is ~10 requests/DAY; an entity-registered account gets 1,000/day. So we
issue ONE search request per NAICS code per sweep and run the sweep at most once a day
(see workers.opportunity_sourcing) — a handful of requests, well under the free ceiling.
Do NOT fetch the per-notice description endpoint (one extra request each would blow the
quota); the search payload carries enough to fit-score, and the human opens uiLink for detail.

Docs: https://open.gsa.gov/api/get-opportunities-public-api/

Relevant filters we set:
  ncode  — NAICS: 541511 custom programming, 541512 systems design, 541519 other IT,
           518210 data processing/hosting (where cloud/AI work lands).
  ptype  — notice type: o=Solicitation, k=Combined Synopsis, p=Presolicitation (live work).
  postedFrom/postedTo — MM/DD/YYYY (required pair).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

_BASE = "https://api.sam.gov/prod/opportunities/v2/search"

# NAICS codes that map to software / AI / IT services work.
DEFAULT_NAICS = ("541511", "541512", "541519", "518210")
# Live-opportunity notice types (skip 'a' awards / 'r' sources-sought unless you want them).
DEFAULT_PTYPES = "o,k,p"


def _mmddyyyy(d: datetime) -> str:
    return d.strftime("%m/%d/%Y")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def _search_one(naics: str, *, posted_from: str, posted_to: str, limit: int) -> list[dict[str, Any]]:
    """One page of results for a single NAICS code. Raises on non-2xx (retried)."""
    params = {
        "api_key": Config.sam_gov_api_key,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "ptype": DEFAULT_PTYPES,
        "ncode": naics,
        "limit": str(limit),
        "offset": "0",
    }
    with httpx.Client(timeout=45.0) as c:
        r = c.get(_BASE, params=params)
        r.raise_for_status()
        data = r.json()
    return data.get("opportunitiesData") or []


def _normalize(o: dict[str, Any]) -> dict[str, Any]:
    """Map a SAM opportunity onto the common opportunity shape the worker ingests."""
    notice_id = o.get("noticeId") or o.get("solicitationNumber") or ""
    agency = o.get("fullParentPathName") or o.get("organizationName") or ""
    pop = o.get("placeOfPerformance") or {}
    city = (pop.get("city") or {}).get("name") if isinstance(pop.get("city"), dict) else pop.get("city")
    state = (pop.get("state") or {}).get("name") if isinstance(pop.get("state"), dict) else pop.get("state")
    location = ", ".join([p for p in (city, state) if p]) or None
    # SAM v2 puts a short synopsis in `description` when present; sometimes it's a URL to the
    # full text (which we deliberately do not fetch — quota). Keep only inline text.
    desc = o.get("description") or ""
    if isinstance(desc, str) and desc.startswith("http"):
        desc = ""
    # Build a compact text blob for the fit-scorer from the structured fields.
    blob = "\n".join(
        p for p in (
            f"Title: {o.get('title', '')}",
            f"Agency: {agency}",
            f"NAICS: {o.get('naicsCode', '')}",
            f"Classification (PSC): {o.get('classificationCode', '')}",
            f"Set-aside: {o.get('typeOfSetAsideDescription') or o.get('typeOfSetAside') or 'none'}",
            f"Type: {o.get('type', '')}",
            f"Place of performance: {location or ''}",
            (desc if desc else ""),
        ) if p and not p.endswith(": ")
    )
    return {
        "source": "sam_gov",
        "external_id": str(notice_id),
        "title": o.get("title") or "(untitled solicitation)",
        "org": agency or None,
        "description": blob,
        "url": o.get("uiLink") or None,
        "budget": None,  # SAM rarely publishes an award ceiling in the search payload
        "location": location,
        "deadline": o.get("responseDeadLine") or None,
        "posted_at": o.get("postedDate") or None,
        "naics": o.get("naicsCode") or None,
        "psc": o.get("classificationCode") or None,
        "set_aside": o.get("typeOfSetAsideDescription") or o.get("typeOfSetAside") or None,
        "raw": o,
    }


def fetch_opportunities(
    *,
    naics: tuple[str, ...] = DEFAULT_NAICS,
    days_back: int = 7,
    limit_per_naics: int = 200,
) -> list[dict[str, Any]]:
    """Pull recent federal software/IT opportunities across the given NAICS codes.

    Returns normalized dicts. Best-effort per NAICS: one code erroring (e.g. quota) does not
    abort the others. Returns [] if no API key is configured.
    """
    if not Config.sam_gov_api_key:
        return []
    now = datetime.now(UTC)
    posted_from = _mmddyyyy(now - timedelta(days=days_back))
    posted_to = _mmddyyyy(now)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for code in naics:
        try:
            rows = _search_one(code, posted_from=posted_from, posted_to=posted_to, limit=limit_per_naics)
        except Exception as e:  # noqa: BLE001 — one NAICS failing must not kill the sweep
            print(f"WARNING sam_gov NAICS {code} failed: {e}")
            continue
        for o in rows:
            norm = _normalize(o)
            if norm["external_id"] and norm["external_id"] not in seen:
                seen.add(norm["external_id"])
                out.append(norm)
    return out
