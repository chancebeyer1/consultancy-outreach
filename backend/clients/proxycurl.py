"""ProxyCurl client — LinkedIn profile + recent-posts enrichment.

API docs: https://nubela.co/proxycurl/docs
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import Config

BASE = "https://nubela.co/proxycurl/api"


def _headers() -> dict[str, str]:
    if not Config.proxycurl_api_key:
        raise RuntimeError("PROXYCURL_API_KEY not set")
    return {"Authorization": f"Bearer {Config.proxycurl_api_key}"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_profile(linkedin_url: str) -> dict[str, Any]:
    """Fetch the full person-profile payload for a LinkedIn URL.

    Pulls a generous set of fields: experience, education, accomplishments,
    skills, current company, recommendations. Costs ~1 credit per call.
    """
    params = {
        "linkedin_profile_url": linkedin_url,
        "use_cache": "if-present",
        "fallback_to_cache": "on-error",
        "extra": "include",
        "github_profile_id": "include",
        "personal_email": "exclude",  # avoid extra cost
        "personal_contact_number": "exclude",
        "twitter_profile_id": "include",
        "facebook_profile_id": "exclude",
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.get(f"{BASE}/v2/linkedin", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
def fetch_recent_posts(linkedin_url: str, count: int = 10) -> list[dict[str, Any]]:
    """Fetch the user's recent LinkedIn posts/activity.

    Endpoint: /v2/linkedin/profile/posts (or /activities depending on plan tier).
    """
    params = {
        "linkedin_profile_url": linkedin_url,
        "count": count,
    }
    with httpx.Client(timeout=60.0) as client:
        # Use the activities endpoint — broader, includes reactions + comments + posts
        r = client.get(
            f"{BASE}/v2/linkedin/profile/posts",
            headers=_headers(),
            params=params,
        )
        if r.status_code == 404:
            # Some accounts don't have public posts; return empty rather than error
            return []
        r.raise_for_status()
        data = r.json()
        return data.get("posts", [])


def fetch_company(domain_or_url: str) -> dict[str, Any]:
    """Fetch company profile by domain or LinkedIn company URL."""
    if domain_or_url.startswith("http"):
        params = {"url": domain_or_url}
    else:
        params = {"resolve_numeric_id": "false", "company_domain": domain_or_url}
    with httpx.Client(timeout=60.0) as client:
        r = client.get(
            f"{BASE}/linkedin/company",
            headers=_headers(),
            params=params,
        )
        r.raise_for_status()
        return r.json()
