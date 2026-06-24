"""Apollo.io client — source email leads by ICP, then reveal work emails.

Apollo's two-step model (by design):
  1. search_people()  -> POST /mixed_people/api_search   firmographics, NO emails, NO credits
  2. enrich_person()  -> POST /people/match              reveals the work email, COSTS a credit

So we search broadly (free), score against the campaign ICP, and enrich ONLY the leads we
will actually contact — minimizing Apollo credits and downstream verification cost.

Auth: header `Authorization: Bearer <APOLLO_API_KEY>` (master key).
Docs: https://docs.apollo.io/reference/people-api-search , /people-enrichment
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import require

_BASE = "https://api.apollo.io/api/v1"


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)


def _headers() -> dict[str, str]:
    # Apollo authenticates via the X-Api-Key header (not Authorization: Bearer).
    return {
        "X-Api-Key": require("APOLLO_API_KEY"),
        "Content-Type": "application/json",
        "accept": "application/json",
    }


def _clean_email(email: str | None) -> str | None:
    """Apollo masks locked emails as 'email_not_unlocked@domain.com'. Treat those as None."""
    if not email:
        return None
    low = email.lower()
    if "email_not_unlocked" in low or low.endswith("@domain.com") or "not_unlocked" in low:
        return None
    return email


def _norm_person(p: dict[str, Any]) -> dict[str, Any]:
    org = p.get("organization") or {}
    name = p.get("name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x) or None
    location = ", ".join(x for x in (p.get("city"), p.get("state"), p.get("country")) if x) or None
    work = _clean_email(p.get("email"))
    personals = [e for e in (p.get("personal_emails") or []) if e and "@" in e]
    # Small-agency owners often have only a personal email in Apollo; prefer work, fall
    # back to personal so the ICP is reachable. The caller decides whether to use personals.
    return {
        "apollo_id": p.get("id"),
        "name": name,
        "first_name": p.get("first_name"),
        "last_name": p.get("last_name"),
        "title": p.get("title"),
        "headline": p.get("headline") or p.get("title"),
        "seniority": p.get("seniority"),
        "linkedin_url": p.get("linkedin_url"),
        "company": org.get("name") or p.get("organization_name"),
        "company_domain": org.get("primary_domain") or org.get("website_url"),
        "location": location,
        "email": work or (personals[0] if personals else None),
        "work_email": work,
        "personal_emails": personals,
        "email_kind": "work" if work else ("personal" if personals else None),
        "apollo_email_status": p.get("email_status"),  # verified | guessed | unavailable | null
    }


@_RETRY
def search_people(
    *,
    titles: list[str] | None = None,
    seniorities: list[str] | None = None,
    locations: list[str] | None = None,
    num_employees_ranges: list[str] | None = None,
    keywords: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    """One page of an Apollo people search. Returns {"people": [...], page/total_pages/total}.

    seniorities use Apollo's enum: owner, founder, c_suite, vp, director, manager, senior,
    entry, intern. num_employees_ranges are "min,max" strings, e.g. "1,10".
    No emails here (Apollo design) — enrich the ones you want.
    """
    body: dict[str, Any] = {"page": page, "per_page": min(per_page, 100)}
    if titles:
        body["person_titles"] = titles
    if seniorities:
        body["person_seniorities"] = seniorities
    if locations:
        body["person_locations"] = locations
    if num_employees_ranges:
        body["organization_num_employees_ranges"] = num_employees_ranges
    if keywords:
        body["q_keywords"] = keywords
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_BASE}/mixed_people/api_search", headers=_headers(), json=body)
        r.raise_for_status()
        data = r.json()
    pg = data.get("pagination") or {}
    return {
        "people": [_norm_person(p) for p in (data.get("people") or [])],
        "page": pg.get("page"),
        "total_pages": pg.get("total_pages"),
        "total": pg.get("total_entries"),
    }


@_RETRY
def enrich_person(
    *,
    apollo_id: str | None = None,
    linkedin_url: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    domain: str | None = None,
    organization_name: str | None = None,
    reveal_personal_emails: bool = False,
) -> dict[str, Any]:
    """Reveal a person's work email (COSTS a credit). Identify by Apollo id (best),
    LinkedIn URL, or name + company domain. Returns a normalized person dict whose
    `email` is the work email (or None if Apollo couldn't unlock one)."""
    body: dict[str, Any] = {"reveal_personal_emails": reveal_personal_emails}
    if apollo_id:
        body["id"] = apollo_id
    if linkedin_url:
        body["linkedin_url"] = linkedin_url
    if first_name:
        body["first_name"] = first_name
    if last_name:
        body["last_name"] = last_name
    if domain:
        body["domain"] = domain
    if organization_name:
        body["organization_name"] = organization_name
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_BASE}/people/match", headers=_headers(), json=body)
        r.raise_for_status()
        data = r.json()
    return _norm_person(data.get("person") or {})
