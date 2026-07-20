"""X / Twitter viral-post discovery via twitterapi.io.

Finds high-engagement AI tweets worth reacting to in a LinkedIn post. twitterapi.io is a cheap,
key-based REST wrapper over X search (no official X API needed, ~$0.15/1k tweets). We lean on
X's own search operators (min_faves, since, lang, -filter) to pull recent, high-like, original
tweets, then rank by engagement.

Optional dependency: if XSEARCH_API_KEY is unset, callers skip the tweet-reaction path. The
exact response shape is defensive-parsed; validate against a live key on first run.
"""
from __future__ import annotations

import datetime as _dt
import time
from typing import Any

import httpx

from config import require

_BASE = "https://api.twitterapi.io"


def configured() -> bool:
    import os

    return bool(os.environ.get("XSEARCH_API_KEY"))


def _headers() -> dict:
    return {"X-API-Key": require("XSEARCH_API_KEY")}


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


_MEDIA_KIND = {"photo": "photo", "video": "video", "animated_gif": "gif"}


def _media_items(t: dict) -> list[dict]:
    """Attached media as {url, kind} dicts, best-effort across twitterapi.io / X shapes.

    Native media lives under extended_entities / extendedEntities .media[] (entities.media only
    carries the first of up to four items, so prefer the extended list). `media_url_https` is the
    still for a photo and the poster/cover frame for a video or GIF — we render a single PNG card
    either way, tagging video/GIF so the card can stamp a ▶ play badge on the frame.
    """
    media = None
    for key in ("extendedEntities", "extended_entities", "entities"):
        c = t.get(key)
        if isinstance(c, dict) and isinstance(c.get("media"), list) and c["media"]:
            media = c["media"]
            break
    if media is None and isinstance(t.get("media"), list):
        media = t["media"]
    out: list[dict] = []
    seen: set[str] = set()
    for m in media or []:
        if not isinstance(m, dict):
            continue
        kind = _MEDIA_KIND.get((m.get("type") or "photo").lower(), "photo")
        u = (
            m.get("media_url_https") or m.get("media_url")
            or m.get("mediaUrlHttps") or m.get("mediaUrl") or ""
        )
        if isinstance(u, str) and u.startswith("http") and u not in seen:
            seen.add(u)
            out.append({"url": u, "kind": kind})
    return out[:4]  # X caps a tweet at four media items


def _normalize(t: dict) -> dict:
    a = t.get("author") or t.get("user") or {}
    return {
        "id": str(t.get("id") or t.get("tweet_id") or t.get("id_str") or ""),
        "url": t.get("url") or t.get("twitterUrl") or t.get("tweet_url") or "",
        "text": (t.get("text") or t.get("full_text") or "").strip(),
        "likes": _int(t.get("likeCount") or t.get("favorite_count") or t.get("likes")),
        "retweets": _int(t.get("retweetCount") or t.get("retweet_count") or t.get("retweets")),
        "replies": _int(t.get("replyCount") or t.get("reply_count")),
        "views": _int(t.get("viewCount") or t.get("views")),
        "author_name": (a.get("name") or "").strip(),
        "author_handle": (a.get("userName") or a.get("screen_name") or a.get("username") or "").lstrip("@"),
        "verified": bool(a.get("isBlueVerified") or a.get("verified") or a.get("is_blue_verified")),
        "created_at": t.get("createdAt") or t.get("created_at") or "",
        "media": _media_items(t),  # attached media {url,kind}, so a reaction card reproduces it
        # twitterapi.io doesn't reliably honor `-filter:replies`, but the response exposes isReply /
        # inReplyToId — so we exclude replies in Python (a reply reads out-of-context as a reaction).
        "is_reply": bool(t.get("isReply") or t.get("inReplyToId") or t.get("in_reply_to_id")),
    }


def search(query: str, *, query_type: str = "Top", limit: int = 20) -> list[dict]:
    """Run one advanced search; return normalized tweets (best-effort, never raises)."""
    params = {"query": query, "queryType": query_type}
    try:
        with httpx.Client(timeout=30, follow_redirects=True) as c:
            r = c.get(f"{_BASE}/twitter/tweet/advanced_search", headers=_headers(), params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:  # noqa: BLE001 — discovery is best-effort
        return []
    tweets = None
    if isinstance(data, dict):
        tweets = data.get("tweets")
        if not isinstance(tweets, list):
            inner = data.get("data") or data.get("result") or {}
            tweets = inner.get("tweets") if isinstance(inner, dict) else None
    out = [_normalize(t) for t in (tweets or []) if isinstance(t, dict)]
    return [t for t in out if t["id"] and t["text"]][:limit]


def search_viral(
    queries, *, min_likes: int = 250, since_days: int | None = None, per_query: int = 20, throttle: float = 5.5
) -> list[dict]:
    """Search several AI topics for high-like, original tweets; dedupe + rank by engagement.

    No date window by default — a genuinely viral AI take is evergreen for a LinkedIn reaction, and
    the caller's own `content_seen` dedupe guarantees we never react to the same tweet twice, so we
    want the widest pool. Pass `since_days` to bound recency (uses `since_time:<epoch>`; twitterapi.io
    does NOT support `since:DATE`). Queries are throttled to respect the free-tier 1-req/5s limit.
    """
    since_clause = ""
    if since_days:
        since_epoch = int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=since_days)).timestamp())
        since_clause = f" since_time:{since_epoch}"
    by_id: dict[str, dict] = {}
    for i, kw in enumerate(queries):
        if i:
            time.sleep(throttle)  # free tier: one request every 5 seconds
        # Always "Top" — it ranks by engagement (probe: 5k+ likes), whereas "Latest" only returns
        # fresh, near-zero-like tweets. `since_time` bounds recency WITHOUT giving up that ranking,
        # so "Top within the last N days" gives the biggest tweets in the window. We do NOT use
        # -filter:links (it returned zero — viral AI tweets link out); ad/course removal is handled
        # downstream by _looks_like_spam + _ai_relevant.
        q = f"{kw} min_faves:{min_likes} lang:en{since_clause}"
        for t in search(q, query_type="Top", limit=per_query):
            by_id[t["id"]] = t
    ranked = sorted(by_id.values(), key=lambda t: t["likes"] + t["retweets"] * 3, reverse=True)
    # Enforce quality in Python — twitterapi.io only guarantees a few operators (from/since_time/
    # until_time/OR), so we never trust min_faves or filter:replies in the query. Drop replies and
    # anything under the like floor here instead. Better to react to nothing than to weak content.
    return [t for t in ranked if t["likes"] >= min_likes and not t["is_reply"]]
