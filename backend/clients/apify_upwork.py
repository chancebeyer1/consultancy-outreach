"""Upwork job discovery via the Apify actor `neatrat/upwork-job-scraper`.

STOPGAP source for Upwork jobs until the official GraphQL API clears (see clients/upwork.py).
Unlike upwork.py — which READS through Upwork's sanctioned API — this actor SCRAPES
upwork.com's public job search from Apify's own infrastructure.

RISK / SCOPE (read before enabling — this was a deliberate operator decision, not a default):
  • Scraping upwork.com violates Upwork's ToS. The scrape runs on Apify's proxies, not your
    logged-in session, so it's decoupled from your account — but the ToS violation is real and
    it can conflict with an in-review Upwork API application. Turn this OFF once the API is live.
  • DISCOVERY ONLY. Like every source it feeds the fit-score / draft review queue; it NEVER
    submits a proposal. The human-in-the-loop submission rule (see workers/opportunity_sourcing)
    is untouched by this file.

DOUBLE-GATED so it can never turn on by accident: fetch_opportunities() returns [] unless BOTH
APIFY_TOKEN is set AND APIFY_UPWORK_ENABLED is truthy. Adding it to the sweep's SOURCES is
therefore safe — an unconfigured (or token-only) install simply skips it.

Apify endpoint — run the actor synchronously and get the dataset back in one call:
  POST https://api.apify.com/v2/acts/neatrat~upwork-job-scraper/run-sync-get-dataset-items?token=…
The actor's OUTPUT field names are NOT fully documented, so the normalizer below tries several
candidate keys per field and keeps the full item in `raw`. VERIFY the mapping against the first
live run's raw payload (`select raw from opportunities where source='upwork_apify' limit 1`) and
tighten the key lists if the actor uses names we didn't anticipate.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

_ACTOR = "neatrat~upwork-job-scraper"  # API form of neatrat/upwork-job-scraper (/ → ~)
_ENDPOINT = f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items"

# Same AI/agent focus as the official client. Upwork's search box honors OR / quotes.
DEFAULT_QUERY = 'AI agent OR LLM OR chatbot OR automation OR RAG OR "machine learning"'

# Bound the actor's own runtime so a slow/stuck scrape can't stall the daily sweep. The httpx
# read timeout sits just above it; only one retry (a long sync call retried many times would
# blow the sweep's wall-clock budget).
_RUN_TIMEOUT_S = 120


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=3, max=15))
def _run(payload: dict[str, Any]) -> list[dict[str, Any]]:
    params = {"token": Config.apify_token, "timeout": _RUN_TIMEOUT_S, "format": "json"}
    with httpx.Client(timeout=_RUN_TIMEOUT_S + 25) as c:
        r = c.post(_ENDPOINT, params=params, json=payload)
        r.raise_for_status()
        data = r.json()
    # run-sync-get-dataset-items returns the dataset items array directly.
    return data if isinstance(data, list) else []


def _first(d: dict[str, Any], *keys: str) -> Any:
    """First present, non-empty value among `keys` (defensive against unknown output shape)."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _scalar(v: Any) -> Any:
    """Pull a usable scalar out of a number/string, or a {amount|value|rawValue|min|max} dict."""
    if isinstance(v, dict):
        for k in ("amount", "value", "rawValue", "min", "max"):
            if v.get(k) not in (None, ""):
                return v[k]
        return None
    return v


def _budget_str(item: dict[str, Any]) -> str | None:
    """Freeform budget label — hourly range, hourly rate, then fixed price; None if unknown."""
    lo = _scalar(_first(item, "hourlyRateMin", "hourlyBudgetMin", "minHourlyRate"))
    hi = _scalar(_first(item, "hourlyRateMax", "hourlyBudgetMax", "maxHourlyRate"))
    if lo or hi:
        return f"${lo or '?'}–${hi or '?'}/hr"
    hourly = _scalar(_first(item, "hourlyRate", "hourlyBudget", "hourly"))
    if hourly:
        return f"${hourly}/hr"
    fixed = _scalar(_first(item, "fixedBudget", "fixedPrice", "budget", "amount", "price"))
    if fixed:
        return f"${fixed} (fixed)"
    return None


def _skills(item: dict[str, Any]) -> list[str]:
    raw = _first(item, "skills", "tags", "requiredSkills")
    out: list[str] = []
    for s in raw if isinstance(raw, list) else []:
        if isinstance(s, str):
            out.append(s)
        elif isinstance(s, dict):
            name = s.get("name") or s.get("skill") or s.get("label")
            if name:
                out.append(str(name))
    return out


def _country(item: dict[str, Any], client: dict[str, Any]) -> str | None:
    for src in (item, client):
        c = _first(src, "clientCountry", "country", "location")
        if isinstance(c, str):
            return c
        if isinstance(c, dict):
            v = c.get("country") or c.get("name")
            if v:
                return str(v)
    return None


def _normalize(item: dict[str, Any]) -> dict[str, Any]:
    url = _first(item, "url", "jobUrl", "link")
    cipher = _first(item, "ciphertext", "id", "uid", "jobId", "key")
    if not url and cipher:
        url = f"https://www.upwork.com/jobs/{cipher}"
    # external_id is the dedup key — prefer the native id, else the (stable) url.
    ext = str(cipher) if cipher else (str(url) if url else "")
    client = item.get("client") if isinstance(item.get("client"), dict) else {}
    country = _country(item, client)
    skills = _skills(item)
    desc = str(_first(item, "description", "descriptionText", "snippet", "text") or "")
    return {
        "source": "upwork_apify",
        "external_id": ext,
        "title": _first(item, "title", "jobTitle", "name") or "(untitled Upwork job)",
        "org": "Upwork client" + (f" ({country})" if country else ""),
        "description": desc[:8000] + ("\n\nSkills: " + ", ".join(skills) if skills else ""),
        "url": url,
        "budget": _budget_str(item),
        "location": country or "Remote",
        "deadline": None,
        # May be relative ('2 hours ago') — the worker's _ts() ISO-validates and drops non-ISO.
        "posted_at": _first(
            item, "postedOn", "publishedDate", "createdDate", "datePosted", "publishedAt", "createdAt"
        ),
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
    per_page = max(10, min(limit, 50))  # actor floor is 10 results/page
    payload = {
        "query": query or Config.apify_upwork_query or DEFAULT_QUERY,
        "sort": "newest",
        "perPage": per_page,
        "pagesToScrape": 1,
        # Verified clients only — fewer scams/non-payers and less wasted LLM scoring. The
        # fit-scorer still gates everything downstream.
        "paymentVerified": True,
        # Keep the scrape light + relevant: a 14-day window plus the dedup ledger still catches
        # everything recent even if a daily sweep is missed.
        "maxJobAge": {"value": 14, "unit": "days"},
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
