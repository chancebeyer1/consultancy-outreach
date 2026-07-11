"""High-signal AI news capture.

Hacker News via the Algolia API (free, no key, no rate limit) is the primary source: it's
what builders actually read and argue about, and points/comments are a built-in quality
signal. We pull recent stories above a points threshold, then keep only AI-relevant titles.
The discussion thread is itself signal, so we keep its URL too.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

_HN = "https://hn.algolia.com/api/v1/search_by_date"
_ARXIV = "https://export.arxiv.org/api/query"
# Curated, reliable feeds (Atom or RSS). Each is fetched best-effort — a broken feed is skipped.
_FEEDS = (
    ("simonwillison", "https://simonwillison.net/atom/everything/"),
    ("huggingface", "https://huggingface.co/blog/feed.xml"),
)
_ATOM = "{http://www.w3.org/2005/Atom}"

# AI-relevance keywords (lowercased, word-ish). Broad enough to catch the space, specific
# enough to skip "real-estate agent" / "fashion model". The LLM selection step filters further.
_AI_TERMS = (
    "ai ", " ai", "a.i.", "llm", "gpt", "claude", "anthropic", "openai", "gemini", "mistral",
    "llama", "deepseek", "agent", "agentic", "machine learning", " ml ", "deep learning",
    "neural", "transformer", "diffusion", "embedding", " rag", "fine-tun", "inference",
    "chatbot", "copilot", "hugging face", "model", "prompt", "reasoning", "multimodal",
    "open-source ai", "foundation model", "mcp", "context window", "token",
)


def _is_ai_relevant(title: str) -> bool:
    t = f" {title.lower()} "
    return any(term in t for term in _AI_TERMS)


def fetch_ai_stories(*, hours: int = 48, min_points: int = 30, limit: int = 15) -> list[dict[str, Any]]:
    """Recent AI-relevant HN stories, highest-points first.

    Returns normalized items: {source_kind, id, title, url, discussion_url, points,
    num_comments, created_at}. `url` is the linked article (None for Ask/Show-HN text posts).
    """
    cutoff = int(time.time()) - hours * 3600
    params = {
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff},points>{min_points}",
        "hitsPerPage": 100,
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.get(_HN, params=params)
        r.raise_for_status()
        hits = r.json().get("hits", [])

    items: list[dict[str, Any]] = []
    for h in hits:
        title = (h.get("title") or "").strip()
        if not title or not _is_ai_relevant(title):
            continue
        oid = str(h.get("objectID"))
        items.append({
            "source_kind": "hn",
            "id": oid,
            "title": title,
            "url": h.get("url"),
            "discussion_url": f"https://news.ycombinator.com/item?id={oid}",
            "points": int(h.get("points") or 0),
            "num_comments": int(h.get("num_comments") or 0),
            "created_at": h.get("created_at"),
        })

    items.sort(key=lambda x: x["points"], reverse=True)
    return items[:limit]


def fetch_arxiv(*, max_results: int = 6) -> list[dict[str, Any]]:
    """Most recent cs.AI / cs.LG / cs.CL papers from the arXiv Atom API (free)."""
    params = {
        "search_query": "cat:cs.AI OR cat:cs.LG OR cat:cs.CL",
        "sortBy": "submittedDate", "sortOrder": "descending", "max_results": max_results,
    }
    with httpx.Client(timeout=30.0, follow_redirects=True) as c:
        r = c.get(_ARXIV, params=params)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    items: list[dict[str, Any]] = []
    for e in root.findall(f"{_ATOM}entry"):
        title = " ".join((e.findtext(f"{_ATOM}title") or "").split())
        if not title:
            continue
        link = ""
        for ln in e.findall(f"{_ATOM}link"):
            if ln.get("type") == "text/html" or ln.get("rel") == "alternate":
                link = ln.get("href") or ""
                break
        ident = (e.findtext(f"{_ATOM}id") or link)
        link = link or ident
        items.append({
            "source_kind": "arxiv", "id": ident.rsplit("/", 1)[-1], "title": title,
            "url": link, "discussion_url": link,
            "summary": " ".join((e.findtext(f"{_ATOM}summary") or "").split())[:500],
            "points": 0, "num_comments": 0, "created_at": e.findtext(f"{_ATOM}published"),
        })
    return items


def _parse_feed(text: str, per_feed: int) -> list[tuple[str, str]]:
    """Return [(title, link)] from an Atom or RSS document. Tolerant of both shapes."""
    root = ET.fromstring(text)
    out: list[tuple[str, str]] = []
    entries = root.findall(f".//{_ATOM}entry")
    if entries:  # Atom
        for e in entries[:per_feed]:
            title = " ".join((e.findtext(f"{_ATOM}title") or "").split())
            link = ""
            for ln in e.findall(f"{_ATOM}link"):
                if ln.get("rel") in (None, "alternate"):
                    link = ln.get("href") or ""
                    break
            if title and link:
                out.append((title, link))
    else:  # RSS
        for it in root.findall(".//item")[:per_feed]:
            title = " ".join((it.findtext("title") or "").split())
            link = (it.findtext("link") or "").strip()
            if title and link:
                out.append((title, link))
    return out


def fetch_rss(*, per_feed: int = 4) -> list[dict[str, Any]]:
    """Recent items from the curated feeds. Each feed is best-effort; failures are skipped."""
    items: list[dict[str, Any]] = []
    for name, url in _FEEDS:
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as c:
                r = c.get(url)
                r.raise_for_status()
                pairs = _parse_feed(r.text, per_feed)
        except Exception:  # noqa: BLE001 — a broken/blocked feed must not break the run
            continue
        for title, link in pairs:
            if not _is_ai_relevant(title) and name != "simonwillison":
                continue  # SW is AI-heavy already; other feeds get the relevance gate
            items.append({
                "source_kind": "rss", "id": f"{name}:{abs(hash(link)) % (10**12)}",
                "title": title, "url": link, "discussion_url": link,
                "points": 0, "num_comments": 0, "created_at": None,
            })
    return items


def fetch_all_sources() -> list[dict[str, Any]]:
    """HN (primary) + arXiv + curated feeds, merged. Each source is best-effort."""
    out: list[dict[str, Any]] = []
    for fn in (
        lambda: fetch_ai_stories(hours=72, min_points=30, limit=12),
        lambda: fetch_arxiv(max_results=6),
        fetch_rss,
    ):
        try:
            out.extend(fn())
        except Exception:  # noqa: BLE001
            continue
    return out
