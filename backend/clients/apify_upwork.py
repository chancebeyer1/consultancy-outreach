"""Upwork job discovery via the Apify actor `blackfalcondata/upwork-scraper`.

STOPGAP source for Upwork jobs until the official GraphQL API clears (see clients/upwork.py).
Unlike upwork.py — which READS through Upwork's sanctioned API — this actor SCRAPES upwork.com's
public job search from Apify's own infrastructure.

(History: we first wired `neatrat/upwork-job-scraper`, but during Apify's rental→pay-per-result
migration its free-tier gate 404'd and returned 0 jobs. Switched to blackfalcondata, which runs
clean and — crucially for a bidder — returns CLIENT INTELLIGENCE: payment-verified, client total
spend, rating, review count, and applicant count. We fold that into the description so the
fit-scorer bids on verified, well-funded clients with less competition.)

RISK / SCOPE (read before enabling — this was a deliberate operator decision, not a default):
  • Scraping upwork.com violates Upwork's ToS. The scrape runs on Apify's proxies, not your
    logged-in session, so it's decoupled from your account — but the ToS violation is real and
    it can conflict with an in-review Upwork API application. Turn this OFF once the API is live.
  • We never send `enrichDetails`/`sessionToken` (which would require YOUR Upwork cookies) — that
    would re-couple the scrape to your account. Base fields only.
  • DISCOVERY ONLY. Like every source it feeds the fit-score / draft review queue; it NEVER
    submits a proposal. The human-in-the-loop submission rule is untouched by this file.

DOUBLE-GATED so it can never turn on by accident: fetch_opportunities() returns [] unless BOTH
APIFY_TOKEN is set AND APIFY_UPWORK_ENABLED is truthy. Adding it to the sweep's SOURCES is
therefore safe — an unconfigured (or token-only) install simply skips it.

Apify endpoint — run the actor synchronously and get the dataset back in one call:
  POST https://api.apify.com/v2/acts/blackfalcondata~upwork-scraper/run-sync-get-dataset-items?token=…
Output field names below are mapped from a verified live run; the full item is kept in `raw`.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

_ACTOR = "blackfalcondata~upwork-scraper"  # API form of blackfalcondata/upwork-scraper (/ → ~)
_ENDPOINT = f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items"

# Upwork's search box honors OR / quotes; the actor forwards `query` to it.
DEFAULT_QUERY = 'AI agent OR LLM OR chatbot OR automation OR RAG OR "machine learning"'

_MAX_AGE_MINUTES = 14 * 24 * 60  # only postings from the last 14 days
# Bound the actor's own runtime so a slow scrape can't stall the daily sweep; httpx read timeout
# sits just above it, with a single retry (a long sync call retried many times would blow the
# sweep's wall-clock budget).
_RUN_TIMEOUT_S = 150


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=3, max=15))
def _run(payload: dict[str, Any]) -> list[dict[str, Any]]:
    params = {"token": Config.apify_token, "timeout": _RUN_TIMEOUT_S, "format": "json"}
    with httpx.Client(timeout=_RUN_TIMEOUT_S + 25) as c:
        r = c.post(_ENDPOINT, params=params, json=payload)
        r.raise_for_status()  # run-sync returns 200/201 on success
        data = r.json()
    return data if isinstance(data, list) else []


def _budget_str(item: dict[str, Any]) -> str | None:
    """Freeform budget label — fixed price, hourly range, then salary range; None if unknown."""
    amt = item.get("budgetAmount")
    if amt:
        return f"{amt} {item.get('budgetCurrency') or 'USD'} (fixed)"
    lo, hi = item.get("hourlyBudgetMin"), item.get("hourlyBudgetMax")
    if lo or hi:
        return f"${lo or '?'}–${hi or '?'}/hr"
    slo, shi = item.get("salaryMin"), item.get("salaryMax")
    if slo or shi:
        unit = "/hr" if (item.get("salaryType") or "").upper() == "HOURLY" else ""
        return f"${slo or '?'}–${shi or '?'}{unit}"
    return None


def _skills(item: dict[str, Any]) -> list[str]:
    flat = [s for s in (item.get("skills") or []) if isinstance(s, str)]
    if flat:
        return flat
    return [s.get("name") for s in (item.get("skillsDetailed") or [])
            if isinstance(s, dict) and s.get("name")]


def _client_note(item: dict[str, Any]) -> str:
    """Compact client-intelligence line — the reason we picked this actor. Folded into the
    description so the fit-scorer factors in client quality/competition, not just the job text."""
    bits: list[str] = []
    verified = item.get("clientPaymentVerified")
    if verified is True:
        bits.append("payment-verified")
    elif verified is False:
        bits.append("payment UNVERIFIED")
    spent = item.get("clientTotalSpent")
    if spent:
        bits.append(f"${round(spent):,} spent")
    rating = item.get("clientRating")
    if rating:
        rc = item.get("clientReviewCount")
        bits.append(f"rating {rating}" + (f"/{rc} reviews" if rc else ""))
    apps = item.get("totalApplicants")
    if apps is not None:
        bits.append(f"{apps} proposals so far")
    return " · ".join(bits)


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    url = item.get("url") or item.get("portalUrl")
    jid = item.get("jobId")
    ext = str(jid) if jid else (str(url) if url else str(item.get("contentHash") or ""))
    country = item.get("clientCountry")
    skills = _skills(item)
    desc = str(item.get("description") or item.get("descriptionMarkdown") or "")[:8000]

    extras: list[str] = []
    if skills:
        extras.append("Skills: " + ", ".join(skills))
    note = _client_note(item)
    if note:
        extras.append("Client: " + (f"{country} · " if country else "") + note)
    meta = " · ".join(b for b in (item.get("experienceLevel"), item.get("engagementDuration")) if b)
    if meta:
        extras.append(meta)
    if extras:
        desc = desc + "\n\n" + "\n".join(extras)

    return {
        "source": "upwork_apify",
        "external_id": ext,
        "title": item.get("title") or "(untitled Upwork job)",
        "org": "Upwork client" + (f" ({country})" if country else ""),
        "description": desc,
        "url": url,
        "budget": _budget_str(item),
        "location": country or "Remote",
        "deadline": None,
        "posted_at": item.get("publishTime") or item.get("createTime"),  # ISO; worker _ts() validates
        "naics": None,
        "psc": None,
        "set_aside": None,
        "raw": item,
    }


def fetch_opportunities(*, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Recent AI/software Upwork postings via the Apify scraper. Returns [] unless BOTH
    APIFY_TOKEN and APIFY_UPWORK_ENABLED are set, and [] on any error (best-effort)."""
    if not (Config.apify_token and Config.apify_upwork_enabled):
        return []
    payload = {
        "query": query or Config.apify_upwork_query or DEFAULT_QUERY,
        "sort": "recency",
        "maxResults": max(1, min(limit, 100)),
        # Verified-payment clients only — fewer scams/non-payers and less wasted LLM scoring.
        # The fit-scorer still gates everything downstream.
        "verifiedPaymentOnly": True,
        "maxAgeMinutes": _MAX_AGE_MINUTES,
        "skipReposts": True,
    }
    try:
        items = _run(payload)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING apify_upwork fetch failed: {e}")
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        n = _normalize(item)
        if n["external_id"]:
            out.append(n)
        if len(out) >= limit:
            break
    return out
