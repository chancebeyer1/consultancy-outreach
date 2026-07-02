"""Fetch and clean the visible text of a public web page (a prospect's homepage) for the audit
agent. Best-effort: strips scripts/styles/tags, collapses whitespace, truncates. No JS rendering,
so SPA-heavy sites yield less, which is fine because the agent also has Tavily results.
"""
from __future__ import annotations

import re

import httpx

_SCRIPT = re.compile(r"<(script|style|noscript|svg|head)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n\s*\n+")
_ENTITIES = (("&amp;", "&"), ("&nbsp;", " "), ("&#39;", "'"), ("&rsquo;", "'"),
             ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&mdash;", ", "))


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    return url


def domain_of(url: str) -> str:
    m = re.match(r"^https?://([^/]+)", normalize_url(url), re.IGNORECASE)
    host = (m.group(1) if m else url or "").lower()
    return host[4:] if host.startswith("www.") else host


def fetch_text(url: str, *, max_chars: int = 6000, timeout: float = 15.0) -> str:
    url = normalize_url(url)
    if not url:
        return ""
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as c:
            r = c.get(url)
            r.raise_for_status()
            html = r.text
    except Exception:  # noqa: BLE001 — scraping is best-effort
        return ""
    html = _SCRIPT.sub(" ", html)
    text = _TAG.sub(" ", html)
    for a, b in _ENTITIES:
        text = text.replace(a, b)
    text = _NL.sub("\n", _WS.sub(" ", text))
    return text.strip()[:max_chars]
