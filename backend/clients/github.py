"""GitHub client — pull a user's public repos to surface technical signals."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

BASE = "https://api.github.com"


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if Config.github_token:
        h["Authorization"] = f"Bearer {Config.github_token}"
    return h


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))
def fetch_user(username: str) -> dict[str, Any] | None:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{BASE}/users/{username}", headers=_headers())
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))
def fetch_repos(username: str, limit: int = 10) -> list[dict[str, Any]]:
    """Pull the user's most recently pushed public repos."""
    params = {"per_page": limit, "sort": "pushed", "type": "owner"}
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{BASE}/users/{username}/repos", headers=_headers(), params=params)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json()


def summarize(username: str) -> dict[str, Any]:
    """One-shot: bio + top repos summarized for prompt injection."""
    user = fetch_user(username)
    if not user:
        return {}
    repos = fetch_repos(username)
    return {
        "username": username,
        "name": user.get("name"),
        "bio": user.get("bio"),
        "blog": user.get("blog"),
        "company": user.get("company"),
        "followers": user.get("followers"),
        "public_repos": user.get("public_repos"),
        "top_repos": [
            {
                "name": r.get("name"),
                "description": r.get("description"),
                "language": r.get("language"),
                "stars": r.get("stargazers_count"),
                "pushed_at": r.get("pushed_at"),
                "topics": r.get("topics", []),
            }
            for r in repos[:8]
        ],
    }
