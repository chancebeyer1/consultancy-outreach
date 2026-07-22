"""Upwork job-alert EMAIL ingestion — the ToS-safe route to Upwork jobs.

Upwork sends job-alert emails TO the operator (his saved-search matches). Reading his own
inbox and parsing them is not scraping Upwork's site — it's processing mail he legitimately
received. We hand the email body to the LLM to extract the postings (robust to Upwork's
changing email templates, unlike brittle HTML regex), normalize them to the common
opportunity shape (source='upwork'), and let the standard score → draft → ingest pipeline
take over. Nothing here touches upwork.com.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from clients import claude
from config import Config

# Upwork job URLs embed a ciphertext id (~ + hex). When present it's a stable external_id;
# otherwise we hash the title so re-parsing the same alert email doesn't duplicate the row.
_CIPHER = re.compile(r"~[0-9a-f]{12,}", re.I)

_EXTRACT_SYS = "You extract structured job postings from email text. Output only valid JSON, nothing else."
_EXTRACT_INSTR = """You are given the text of an Upwork job-alert email — job postings matching a saved search.
Extract EVERY distinct job posting in it. Return a JSON array; each item is:
{"title": string, "description": string (the snippet/summary shown for the job), "budget": string or null (e.g. "$500 fixed" or "$30-$60/hr"), "url": string or null (the job link if one is present)}
Ignore navigation, headers, footers, unsubscribe links, marketing blurbs, and account/settings text — only real job postings. If there are no job postings, return []."""


def is_upwork_alert(from_identifier: str | None, subject: str | None) -> bool:
    """Cheap pre-filter: does this inbox email look like an Upwork job alert? (Avoids sending
    unrelated mail to the LLM.)"""
    f = (from_identifier or "").lower()
    s = (subject or "").lower()
    if "upwork" not in f and "upwork" not in s:
        return False
    return "upwork.com" in f or any(k in s for k in ("job", "match", "saved search", "new jobs"))


def extract_jobs(subject: str, text: str) -> list[dict[str, Any]]:
    """LLM-extract job postings from one alert email → normalized opportunity dicts.
    Returns [] on any failure (best-effort, like every other source)."""
    payload = f"Subject: {subject}\n\n{(text or '')[:12000]}"
    try:
        result = claude.call_json(
            instruction=_EXTRACT_INSTR,
            user_payload=payload,
            system_prefix=_EXTRACT_SYS,
            model=Config.claude_model_draft,
            max_tokens=2000,
        )
    except Exception as e:  # noqa: BLE001
        print(f"WARNING upwork_email extract failed: {e}")
        return []
    if not isinstance(result, list):
        return []
    out: list[dict[str, Any]] = []
    for j in result:
        if not isinstance(j, dict):
            continue
        title = (j.get("title") or "").strip()
        if not title:
            continue
        url = j.get("url")
        m = _CIPHER.search(url or "")
        ext = m.group(0) if m else "email:" + hashlib.sha1(title.lower().encode("utf-8", "ignore")).hexdigest()[:16]
        out.append({
            "source": "upwork",
            "external_id": ext,
            "title": title[:200],
            "org": "Upwork client (via job alert)",
            "description": (j.get("description") or "")[:8000],
            "url": url,
            "budget": j.get("budget"),
            "location": "Remote",
            "deadline": None,
            "posted_at": None,
            "naics": None,
            "psc": None,
            "set_aside": None,
            "raw": {"via": "upwork_email", **j},
        })
    return out
