"""Hacker News "Ask HN: Who is hiring?" — the monthly hiring megathread, via the free
Algolia HN Search API (no key, no auth). The single best zero-cost signal source for
startup contract/AI-build work: each top-level comment is one company's job post.

Flow:
  1. Find the latest "Who is hiring?" story posted by the `whoishiring` account.
  2. Fetch that story's item tree; each top-level child comment is a posting.
  3. Keyword-filter comments to AI/agent/contract work — the fit-scorer does the rest.

APIs: https://hn.algolia.com/api  ·  story item: /api/v1/items/<id>
"""
from __future__ import annotations

import html as _html
import re
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
_ITEM = "https://hn.algolia.com/api/v1/items/"

_TAG = re.compile(r"<[^>]+>")

# Only surface postings that mention AI/agent work AND ideally contract/remote terms.
# Word-boundary regex, NOT substring membership: "ai"/"ml" are substrings of ubiquitous
# words (email, available, html), which made a substring gate pass nearly everything.
_AI_RE = re.compile(
    r"\b(a\.?i\.?|llm|agents?|machine learning|ml|gen ?ai|generative|nlp|gpt|rag"
    r"|chatbots?|automation)\b",
    re.IGNORECASE,
)
_CONTRACT_HINTS = ("contract", "contractor", "freelance", "consult", "part-time",
                   "part time", "remote", "1099")


def _clean(raw: str) -> str:
    """Strip tags, then unescape entities with the stdlib (covers the full entity set —
    a hand-kept list silently leaks anything it doesn't know, e.g. &#38; or &nbsp;)."""
    text = _TAG.sub(" ", raw or "")
    text = _html.unescape(text)
    # \xa0: html.unescape turns &nbsp; into a non-breaking space — collapse it too.
    return re.sub(r"[ \t\xa0]+", " ", text).strip()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _latest_thread_id() -> str | None:
    """objectID of the most recent 'Who is hiring?' story from the whoishiring account."""
    params = {
        "tags": "story,author_whoishiring",
        "query": "hiring",
        "hitsPerPage": "5",
    }
    with httpx.Client(timeout=30.0) as c:
        r = c.get(_SEARCH, params=params)
        r.raise_for_status()
        hits = r.json().get("hits") or []
    for h in hits:
        title = (h.get("title") or "").lower()
        if "who is hiring" in title:
            return h.get("objectID")
    return hits[0].get("objectID") if hits else None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _fetch_thread(thread_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=45.0) as c:
        r = c.get(f"{_ITEM}{thread_id}")
        r.raise_for_status()
        return r.json()


def _matches(text: str) -> bool:
    return bool(_AI_RE.search(text))


def _first_line(text: str) -> str:
    line = text.strip().split("\n", 1)[0].strip()
    return (line[:140] + "…") if len(line) > 140 else line or "(HN who-is-hiring post)"


def fetch_opportunities(*, limit: int = 60) -> list[dict[str, Any]]:
    """AI/software postings from the latest HN who-is-hiring thread. Best-effort → []."""
    try:
        thread_id = _latest_thread_id()
        if not thread_id:
            return []
        thread = _fetch_thread(thread_id)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING hn_hiring fetch failed: {e}")
        return []
    children = thread.get("children") or []
    out: list[dict[str, Any]] = []
    for ch in children:
        if not isinstance(ch, dict) or not ch.get("text"):
            continue
        text = _clean(ch["text"])
        if len(text) < 40 or not _matches(text):
            continue
        cid = str(ch.get("id") or "")
        is_contract = any(h in text.lower() for h in _CONTRACT_HINTS)
        out.append({
            "source": "hn_hiring",
            "external_id": cid,
            "title": _first_line(text),
            "org": ch.get("author") or None,
            "description": text[:8000],
            "url": f"https://news.ycombinator.com/item?id={cid}" if cid else None,
            "budget": None,
            "location": "Remote" if "remote" in text.lower() else None,
            "deadline": None,
            "posted_at": ch.get("created_at") or None,
            "naics": None,
            "psc": None,
            "set_aside": None,
            "raw": {"contract_hint": is_contract, "thread_id": thread_id, **ch},
        })
        if len(out) >= limit:
            break
    return out
