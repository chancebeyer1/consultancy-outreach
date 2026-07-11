"""Twilio SMS client — instant-response texts to inbound leads.

Inbound hand-raisers give a phone number and expect fast contact; SMS out-opens email for
them. Thin wrapper over Twilio's REST API (no SDK dependency). Gated on TWILIO_* env vars:
`configured()` is False when any is missing, and callers skip SMS + fall back to email.
"""

from __future__ import annotations

from typing import Any

import httpx

from config import Config

_API = "https://api.twilio.com/2010-04-01"


def configured() -> bool:
    return bool(
        Config.twilio_account_sid
        and Config.twilio_auth_token
        and Config.twilio_from_number
    )


def send_sms(to_number: str, body: str) -> dict[str, Any]:
    """Send one SMS. Returns {sid, status}. Raises on HTTP error (caller records failure).

    `to_number` should be E.164 (+1…); Twilio will reject non-E.164. Body over 1600 chars is
    rejected by Twilio, but our inbound texts are short by design.
    """
    if not configured():
        raise RuntimeError("Twilio not configured (TWILIO_* env vars unset)")

    resp = httpx.post(
        f"{_API}/Accounts/{Config.twilio_account_sid}/Messages.json",
        auth=(Config.twilio_account_sid, Config.twilio_auth_token),
        data={"To": to_number, "From": Config.twilio_from_number, "Body": body},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"sid": data.get("sid"), "status": data.get("status")}
