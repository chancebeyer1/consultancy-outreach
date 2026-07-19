"""Resend email client — for transactional mail (tool-result copies, operator notifications), NOT
cold outreach.

Cold email goes through the warmed Maildoso boxes; transactional mail sends from a verified Resend
domain (NEWSLETTER_FROM). Keeping the two streams separate protects the cold-sending domains.

https://resend.com/docs
"""
from __future__ import annotations

from typing import Any

import httpx

from config import require

URL = "https://api.resend.com/emails"


def send(
    *,
    to_email: str,
    subject: str,
    text: str,
    from_addr: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Send one email via Resend. Raises on a non-2xx so callers can count failures."""
    key = require("RESEND_API_KEY")
    body: dict[str, Any] = {"from": from_addr, "to": [to_email], "subject": subject, "text": text}
    if headers:
        body["headers"] = headers
    with httpx.Client(timeout=30.0) as c:
        r = c.post(URL, headers={"Authorization": f"Bearer {key}"}, json=body)
        r.raise_for_status()
        return r.json()
