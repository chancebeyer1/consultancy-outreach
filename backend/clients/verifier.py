"""MillionVerifier — verify an email before sending, to limit bounces.

Cheapest reliable verifier; only bills 'ok'/'invalid' results (catch-all, unknown,
disposable come back free). Policy: send to 'ok'; optionally risk 'catch_all';
never send to 'invalid' / 'disposable' / 'unknown'.

Docs: https://developer.millionverifier.com/
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import require

_BASE = "https://api.millionverifier.com/api/v3"


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)


@_RETRY
def verify(email: str, *, timeout: int = 20) -> dict[str, Any]:
    """Verify one address. Returns MillionVerifier's raw result dict.

    Key fields: `result` (ok | catch_all | unknown | invalid | disposable | error),
    `quality` (good | risky | bad), `resultcode`, `subresult`.
    """
    params = {"api": require("MILLIONVERIFIER_API_KEY"), "email": email, "timeout": timeout}
    with httpx.Client(timeout=timeout + 10) as c:
        r = c.get(f"{_BASE}/", params=params)
        r.raise_for_status()
        return r.json()


def is_sendable(result: dict[str, Any], *, allow_catch_all: bool = False) -> bool:
    """Whether we should send to this address given a verify() result.

    'ok' always; 'catch_all' only when explicitly allowed (higher bounce risk).
    """
    res = (result.get("result") or "").lower()
    if res == "ok":
        return True
    return allow_catch_all and res == "catch_all"


@_RETRY
def credits() -> int:
    """Remaining verification credits on the account (validates the API key)."""
    with httpx.Client(timeout=20) as c:
        r = c.get(f"{_BASE}/credits", params={"api": require("MILLIONVERIFIER_API_KEY")})
        r.raise_for_status()
        data = r.json()
    if isinstance(data, dict):
        return int(data.get("credits", data.get("credit", 0)) or 0)
    return int(data or 0)
