"""Cross-run provider cooldowns (DB-backed, Modal-safe).

When a provider imposes a temporary account-level throttle — notably LinkedIn's
422 `cannot_resend_yet` / "You have reached a temporary provider limit" — the
right response is to stop attempting that channel for several hours, not to keep
retrying every cron tick. Each failed invite re-pokes LinkedIn and can extend the
block, so we persist a `blocked_until` in Postgres and skip the channel until it
passes. The cron then probes again at the cooldown interval (hours), not minutes,
and auto-recovers once LinkedIn clears the limit.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import psycopg

from config import require

# Default backoff when LinkedIn says "try again later". Probing every few hours
# (vs every 47-min cron tick) is gentle enough to age out the block while still
# resuming on its own. Repeated trips just refresh the window.
DEFAULT_COOLDOWN_HOURS = 6.0


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def active(key: str) -> tuple[bool, Optional[datetime], Optional[str]]:
    """Return (is_cooling_down, blocked_until, reason). Fails open (no cooldown)
    if the table/DB is unreachable — we'd rather attempt a send than silently stall."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select blocked_until, reason from provider_cooldowns "
                "where key=%s and blocked_until > now()",
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return False, None, None
            return True, row[0], row[1]
    except Exception:  # noqa: BLE001
        return False, None, None


def trip(key: str, *, hours: float = DEFAULT_COOLDOWN_HOURS, reason: str = "") -> None:
    """Start (or refresh) a cooldown ending `hours` from now. Never raises."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into provider_cooldowns (key, blocked_until, reason, hits, updated_at)
                values (%s, now() + (%s * interval '1 hour'), %s, 1, now())
                on conflict (key) do update set
                    blocked_until = now() + (%s * interval '1 hour'),
                    reason = excluded.reason,
                    hits = provider_cooldowns.hits + 1,
                    updated_at = now()
                """,
                (key, hours, reason[:300], hours),
            )
    except Exception as e:  # noqa: BLE001
        print("provider_cooldown.trip failed:", str(e)[:200])


def clear(key: str) -> None:
    """Remove a cooldown (e.g. operator override). Never raises."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("delete from provider_cooldowns where key=%s", (key,))
    except Exception as e:  # noqa: BLE001
        print("provider_cooldown.clear failed:", str(e)[:200])
