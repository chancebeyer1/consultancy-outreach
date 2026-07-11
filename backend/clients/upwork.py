"""Upwork job discovery via the official GraphQL Marketplace API.

Highest-relevance source (your literal buyer wants AI-agent builds) but GATED: Upwork
requires an approved API application (Developer Space → ~2-week review) and OAuth2. This
client is built and ready; it goes live the moment UPWORK_ACCESS_TOKEN is set. Until then
fetch_opportunities() returns [] so the sweep runs fine without it.

HARD RULES (Upwork ToS — a violation is an instant ban):
  • API ONLY. Never scrape upwork.com pages or automate the logged-in web session.
  • Never auto-SUBMIT proposals. This module only READS postings; you submit by hand.
  • Stay under ~300 requests/min per IP.

Endpoint: https://api.upwork.com/graphql   (Bearer <access_token>)
Query:    marketplaceJobPostingsSearch(marketPlaceJobFilter: {...})
Token:    obtain via OAuth2 (client_credentials or authorization_code); refresh out of band
          and set UPWORK_ACCESS_TOKEN. Scope: "Common Entities – Read-Only Access".
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

_ENDPOINT = "https://api.upwork.com/graphql"

# AI/agent-focused search expression. Upwork's searchExpression is a boolean keyword query.
DEFAULT_QUERY = "AI agent OR LLM OR chatbot OR automation OR RAG OR \"machine learning\""

_GQL = """
query jobSearch($filter: MarketplaceJobPostingsSearchFilter, $sort: [MarketplaceJobPostingSearchSortAttribute]) {
  marketplaceJobPostingsSearch(marketPlaceJobFilter: $filter, searchType: USER_JOBS_SEARCH, sortAttributes: $sort) {
    totalCount
    edges {
      node {
        id
        ciphertext
        title
        description
        createdDateTime
        duration
        engagement
        amount { rawValue currency }
        hourlyBudgetMin { rawValue currency }
        hourlyBudgetMax { rawValue currency }
        skills { name }
        client { location { country } totalSpent { rawValue } }
      }
    }
  }
}
""".strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
def _query(query: str, first: int) -> dict[str, Any]:
    variables = {
        "filter": {"searchExpression_eq": query, "pagination_eq": {"first": first, "after": "0"}},
        "sort": [{"field": "RECENCY", "order": "DESC"}],
    }
    headers = {
        "Authorization": f"Bearer {Config.upwork_access_token}",
        "Content-Type": "application/json",
    }
    if Config.upwork_org_id:
        # Upwork routes some org-scoped tokens via this header.
        headers["X-Upwork-API-TenantId"] = Config.upwork_org_id
    with httpx.Client(timeout=45.0) as c:
        r = c.post(_ENDPOINT, headers=headers, json={"query": _GQL, "variables": variables})
        r.raise_for_status()
        return r.json()


def _amount_str(node: dict[str, Any]) -> str | None:
    amt = node.get("amount") or {}
    if amt.get("rawValue"):
        return f"{amt.get('rawValue')} {amt.get('currency') or 'USD'} (fixed)"
    lo = (node.get("hourlyBudgetMin") or {}).get("rawValue")
    hi = (node.get("hourlyBudgetMax") or {}).get("rawValue")
    if lo or hi:
        return f"${lo or '?'}–${hi or '?'}/hr"
    return None


def _normalize(node: dict[str, Any]) -> dict[str, Any]:
    cipher = node.get("ciphertext") or node.get("id") or ""
    skills = [s.get("name") for s in (node.get("skills") or []) if s.get("name")]
    client = node.get("client") or {}
    country = ((client.get("location") or {}).get("country")) if isinstance(client.get("location"), dict) else None
    return {
        "source": "upwork",
        "external_id": str(node.get("id") or cipher),
        "title": node.get("title") or "(untitled Upwork job)",
        "org": "Upwork client" + (f" ({country})" if country else ""),
        "description": (node.get("description") or "")[:8000]
        + ("\n\nSkills: " + ", ".join(skills) if skills else ""),
        "url": f"https://www.upwork.com/jobs/{cipher}" if cipher else None,
        "budget": _amount_str(node),
        "location": country or "Remote",
        "deadline": None,
        "posted_at": node.get("createdDateTime") or None,
        "naics": None,
        "psc": None,
        "set_aside": None,
        "raw": node,
    }


def fetch_opportunities(*, query: str = DEFAULT_QUERY, limit: int = 50) -> list[dict[str, Any]]:
    """Recent AI/software Upwork postings. Returns [] if no token or on any error."""
    if not Config.upwork_access_token:
        return []
    try:
        data = _query(query, first=limit)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING upwork fetch failed: {e}")
        return []
    if data.get("errors"):
        print(f"WARNING upwork GraphQL errors: {data['errors']}")
        return []
    edges = (((data.get("data") or {}).get("marketplaceJobPostingsSearch") or {}).get("edges")) or []
    out: list[dict[str, Any]] = []
    for e in edges:
        node = e.get("node") if isinstance(e, dict) else None
        if node and (node.get("id") or node.get("ciphertext")):
            out.append(_normalize(node))
    return out
