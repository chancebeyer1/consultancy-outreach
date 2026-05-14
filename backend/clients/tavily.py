"""Tavily search client — for company/news signals.

API: https://docs.tavily.com
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

URL = "https://api.tavily.com/search"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def search(
    query: str,
    *,
    max_results: int = 5,
    search_depth: str = "advanced",
    include_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not Config.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY not set")
    body = {
        "api_key": Config.tavily_api_key,
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    if include_domains:
        body["include_domains"] = include_domains
    with httpx.Client(timeout=60.0) as client:
        r = client.post(URL, json=body)
        r.raise_for_status()
        return r.json().get("results", [])


def company_signals(company_name: str) -> dict[str, list[dict[str, Any]]]:
    """Run a small panel of searches that surface useful sales signals."""
    if not Config.tavily_api_key:
        return {"funding": [], "hiring": [], "ai_work": [], "press": []}
    return {
        "funding": search(f'"{company_name}" funding OR raised OR seed OR series', max_results=3),
        "hiring": search(f'"{company_name}" hiring AI engineer OR agent engineer', max_results=3),
        "ai_work": search(
            f'"{company_name}" AI agent OR LLM application OR case study',
            max_results=3,
        ),
        "press": search(f'"{company_name}" announces OR launches', max_results=3),
    }
