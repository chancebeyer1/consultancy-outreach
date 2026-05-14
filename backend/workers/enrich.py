"""Enrichment worker: orchestrates ProxyCurl + Tavily + GitHub for one lead."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from clients import github, proxycurl, tavily


def _github_username_from_profile(profile: dict[str, Any]) -> str | None:
    """ProxyCurl returns github profile id under 'extra.github_profile_id'.

    Falls back to scanning the 'github_profile_id' top-level field on older payloads.
    """
    if not profile:
        return None
    extra = profile.get("extra") or {}
    gh = extra.get("github_profile_id") or profile.get("github_profile_id")
    if not gh:
        return None
    # Sometimes ProxyCurl returns the full URL, sometimes just the username
    if gh.startswith("http"):
        path = urlparse(gh).path.strip("/")
        return path.split("/")[0] or None
    return gh


def _company_name(profile: dict[str, Any]) -> str | None:
    if not profile:
        return None
    experiences = profile.get("experiences") or []
    if not experiences:
        return None
    return experiences[0].get("company")


def enrich(linkedin_url: str) -> dict[str, Any]:
    """Run the full enrichment pipeline for one LinkedIn URL.

    Returns a dict with: profile, recent_posts, company_signals, github.
    Any field that fails or is unavailable is set to None / empty.
    """
    out: dict[str, Any] = {
        "linkedin_url": linkedin_url,
        "profile": None,
        "recent_posts": [],
        "company_signals": {},
        "github": {},
    }

    # 1. ProxyCurl profile (required — fail loudly)
    out["profile"] = proxycurl.fetch_profile(linkedin_url)

    # 2. Recent posts (nice-to-have)
    try:
        out["recent_posts"] = proxycurl.fetch_recent_posts(linkedin_url, count=10)
    except Exception as e:  # noqa: BLE001
        out["recent_posts_error"] = str(e)

    # 3. Company signals via Tavily (nice-to-have)
    company = _company_name(out["profile"])
    if company:
        try:
            out["company_signals"] = tavily.company_signals(company)
        except Exception as e:  # noqa: BLE001
            out["company_signals_error"] = str(e)
    out["company"] = company

    # 4. GitHub (best-effort)
    gh_user = _github_username_from_profile(out["profile"])
    if gh_user:
        try:
            out["github"] = github.summarize(gh_user)
        except Exception as e:  # noqa: BLE001
            out["github_error"] = str(e)

    return out
