"""LinkedIn job-post discovery via Unipile (reuses the connected LinkedIn account).

Zero new integration cost — it rides the Unipile `POST /linkedin/search` endpoint the
outreach system already uses for people/posts, with category="jobs". Results are scoped to
what the connected account can see (same as browsing LinkedIn Jobs by hand) and this is NOT
a LinkedIn-sanctioned API, so treat it as best-effort: any error yields [] and never breaks
the sweep. Requires the Unipile creds already in .env (UNIPILE_*).

We only READ postings and draft a proposal/DM for your review — nothing auto-applies.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from clients.unipile import _base, _headers, _li_account  # reuse the configured client

DEFAULT_KEYWORDS = "AI engineer contract OR LLM OR AI agent OR machine learning contractor"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _search_jobs(keywords: str, *, account_id: str | None, cursor: str | None) -> dict[str, Any]:
    q: dict[str, Any] = {"account_id": account_id or _li_account()}
    if cursor:
        q["cursor"] = cursor
    body = {"api": "classic", "category": "jobs", "keywords": keywords}
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/linkedin/search", headers=_headers(), params=q, json=body)
        r.raise_for_status()
        return r.json()


def _normalize(j: dict[str, Any]) -> dict[str, Any] | None:
    jid = j.get("id") or j.get("job_id") or j.get("entity_urn") or j.get("tracking_urn")
    if not jid:
        return None
    company = j.get("company") or j.get("company_name")
    if isinstance(company, dict):
        company = company.get("name")
    loc = j.get("location")
    if isinstance(loc, dict):
        loc = loc.get("name") or loc.get("text")
    url = j.get("url") or j.get("share_url") or j.get("job_url")
    if not url and jid:
        url = f"https://www.linkedin.com/jobs/view/{str(jid).split(':')[-1]}"
    return {
        "source": "linkedin_jobs",
        "external_id": str(jid),
        "title": j.get("title") or j.get("name") or "(untitled role)",
        "org": company or None,
        "description": (j.get("description") or j.get("snippet") or "")[:8000],
        "url": url,
        "budget": j.get("salary") or None,
        "location": loc or None,
        "deadline": None,
        "posted_at": j.get("posted_at") or j.get("date") or j.get("listed_at") or None,
        "naics": None,
        "psc": None,
        "set_aside": None,
        "raw": j,
    }


def fetch_opportunities(*, keywords: str = DEFAULT_KEYWORDS, limit: int = 50) -> list[dict[str, Any]]:
    """Recent LinkedIn job posts matching AI/software keywords. Best-effort → []."""
    try:
        data = _search_jobs(keywords, account_id=None, cursor=None)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING linkedin_jobs search failed (endpoint may need adjustment): {e}")
        return []
    raw = data.get("items", []) if isinstance(data, dict) else (data or [])
    out: list[dict[str, Any]] = []
    for j in raw:
        if not isinstance(j, dict):
            continue
        norm = _normalize(j)
        if norm:
            out.append(norm)
        if len(out) >= limit:
            break
    return out
