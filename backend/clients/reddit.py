"""Reddit — READ-ONLY discovery client (official API, `read` scope).

HARD RULE: this module only ever READS. There is no submit, comment, vote, or private
message path here and none may be added. Recruiting or pitching people who posted a
complaint breaks subreddit rules and reads as spam; the pipeline reaches buyers on
channels where cold contact is legitimate (LinkedIn, email, phone) and uses Reddit
purely to learn what the work actually feels like.

Post authors are omitted by default. The value is the described pain, not who described
it, and storing usernames would turn a research corpus into a contact list this system
must never build. `include_author=True` is a deliberate opt-in for the one caller with a
different job — the founder reachout queue, which drafts a message a human then sends to
a named person on a channel where that contact is welcome. Anything writing pain_signals
must leave it off.

Auth reuses the founders module's script-app refresh-token grant
(REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_REFRESH_TOKEN). Every call degrades
to [] when unconfigured, so an unset .env means "this source is skipped", never a crash.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from config import Config

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_API = "https://oauth.reddit.com"

# Reddit's OAuth budget is 100 requests/minute averaged over 10 minutes. A sweep makes
# roughly one call per venue, so this pause keeps a wide sweep comfortably legal.
_PAUSE_S = 0.7

_token_cache: dict[str, Any] = {"value": "", "expires_at": 0.0}


def configured() -> bool:
    return bool(
        Config.reddit_client_id and Config.reddit_client_secret and Config.reddit_refresh_token
    )


def _token() -> str:
    """Access token via the refresh-token grant, cached until shortly before expiry.

    Reddit issues hour-long tokens; re-exchanging on every call would waste a request
    from the same budget the listing calls draw on.
    """
    now = time.time()
    if _token_cache["value"] and now < float(_token_cache["expires_at"]):
        return str(_token_cache["value"])
    r = httpx.post(
        _TOKEN_URL,
        auth=(Config.reddit_client_id, Config.reddit_client_secret),
        data={"grant_type": "refresh_token", "refresh_token": Config.reddit_refresh_token},
        headers={"User-Agent": Config.reddit_user_agent},
        timeout=30.0,
    )
    r.raise_for_status()
    payload = r.json()
    token = payload.get("access_token")
    if not token:
        raise RuntimeError("reddit token exchange returned no access_token")
    _token_cache["value"] = str(token)
    _token_cache["expires_at"] = now + float(payload.get("expires_in") or 3600) - 120
    return str(token)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_token()}", "User-Agent": Config.reddit_user_agent}


def _normalize(
    child: dict[str, Any], venue: str, *, include_author: bool = False
) -> dict[str, Any] | None:
    """One listing child → our normalized signal shape. None when unusable.

    `external_id` is Reddit's fullname (t3_xxxxx), stable across edits and the dedup key.
    `include_author` adds the username; see the module docstring before passing it.
    """
    d = child.get("data") or {}
    fullname = d.get("name")
    permalink = d.get("permalink")
    if not fullname or not permalink:
        return None
    title = (d.get("title") or "").strip()
    body = (d.get("selftext") or "").strip()
    if len(f"{title}{body}") < 40:
        return None  # a bare title with no substance can't be scored for real pain
    row: dict[str, Any] = {
        "source": "reddit",
        "external_id": str(fullname),
        "url": f"https://www.reddit.com{permalink}",
        "venue": venue,
        "title": title[:300],
        # Capped: the scorer only needs enough to judge the task, and the cap bounds
        # both the LLM bill and what a research corpus retains verbatim.
        "text": body[:4000],
        "posted_at": float(d.get("created_utc") or 0) or None,
        "upvotes": int(d.get("score") or 0),
        "num_comments": int(d.get("num_comments") or 0),
    }
    if include_author:
        # Absent unless asked for, so a caller that never opts in cannot store it by accident.
        row["author"] = d.get("author") or None
    return row


def _listing(path: str, params: dict[str, str], venue: str, limit: int,
             *, include_author: bool = False) -> list[dict[str, Any]]:
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{_API}{path}", params=params, headers=_headers())
        r.raise_for_status()
        children = (r.json().get("data") or {}).get("children") or []
    out: list[dict[str, Any]] = []
    for ch in children:
        row = _normalize(ch, venue, include_author=include_author)
        if row:
            out.append(row)
        if len(out) >= limit:
            break
    time.sleep(_PAUSE_S)
    return out


def search(
    subreddit: str,
    query: str,
    *,
    limit: int = 25,
    time_filter: str = "year",
    sort: str = "relevance",
) -> list[dict[str, Any]]:
    """Search one subreddit. Returns [] when unconfigured; raises on API failure so the
    caller can isolate a single venue without losing the sweep."""
    if not configured():
        return []
    return _listing(
        f"/r/{subreddit}/search",
        {
            "q": query,
            "restrict_sr": "1",
            "sort": sort,
            "t": time_filter,
            "limit": str(min(limit * 2, 100)),
        },
        f"r/{subreddit}",
        limit,
    )


def newest(subreddit: str, *, limit: int = 25,
           include_author: bool = False) -> list[dict[str, Any]]:
    """Newest posts in one subreddit (no keyword filter).

    `include_author=True` is an opt-in the module docstring governs — pass it only when
    the caller has a legitimate reason to address a person, never for the pain corpus.
    """
    if not configured():
        return []
    return _listing(f"/r/{subreddit}/new", {"limit": str(min(limit * 2, 100))},
                    f"r/{subreddit}", limit, include_author=include_author)
