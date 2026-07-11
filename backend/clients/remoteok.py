"""RemoteOK public jobs feed — https://remoteok.com/api

Free, no auth, no key. Returns a JSON array whose FIRST element is a legal/metadata
notice (skip it). RemoteOK's ToS requires attribution + a link back to the listing when you
surface it — we always store and display the listing `url`, so honor that in any UI.

These are mostly full-time remote roles, not consulting gigs, but the AI/agent-tagged ones
are a cheap zero-approval signal source; the fit-scorer decides which are worth a bid.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

_URL = "https://remoteok.com/api"

# Client-side keyword gate — RemoteOK returns everything; we only want software/AI work.
_KEYWORDS = (
    "ai", "artificial intelligence", "machine learning", "ml", "llm", "agent", "agents",
    "genai", "generative", "nlp", "chatbot", "automation", "rag", "python", "developer",
    "engineer", "software", "backend", "full stack", "fullstack", "data",
)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _fetch_raw() -> list[dict[str, Any]]:
    with httpx.Client(timeout=30.0, follow_redirects=True) as c:
        r = c.get(
            _URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; consultancy-bids/1.0; +https://remoteok.com)",
                "Accept": "application/json",
            },
        )
        r.raise_for_status()
        data = r.json()
    return data if isinstance(data, list) else []


def _matches(job: dict[str, Any]) -> bool:
    hay = " ".join(
        str(x).lower() for x in (
            job.get("position"), job.get("description"), " ".join(job.get("tags") or []),
        ) if x
    )
    return any(k in hay for k in _KEYWORDS)


def _normalize(job: dict[str, Any]) -> dict[str, Any]:
    tags = job.get("tags") or []
    sal_min, sal_max = job.get("salary_min"), job.get("salary_max")
    budget = None
    if sal_min or sal_max:
        budget = f"${sal_min or '?'}–${sal_max or '?'}/yr"
    return {
        "source": "remoteok",
        "external_id": str(job.get("id") or job.get("slug") or ""),
        "title": job.get("position") or "(untitled role)",
        "org": job.get("company") or None,
        "description": (job.get("description") or "")[:8000]
        + ("\n\nTags: " + ", ".join(tags) if tags else ""),
        "url": job.get("url") or job.get("apply_url") or None,
        "budget": budget,
        "location": job.get("location") or "Remote",
        "deadline": None,
        "posted_at": job.get("date") or None,
        "naics": None,
        "psc": None,
        "set_aside": None,
        "raw": job,
    }


def fetch_opportunities(*, limit: int = 100) -> list[dict[str, Any]]:
    """Recent AI/software remote listings. Returns [] on any failure (best-effort)."""
    try:
        raw = _fetch_raw()
    except Exception as e:  # noqa: BLE001
        print(f"WARNING remoteok fetch failed: {e}")
        return []
    out: list[dict[str, Any]] = []
    for job in raw:
        if not isinstance(job, dict) or job.get("legal"):
            continue  # element 0 is the legal notice
        if not job.get("id") and not job.get("slug"):
            continue
        if not _matches(job):
            continue
        out.append(_normalize(job))
        if len(out) >= limit:
            break
    return out
