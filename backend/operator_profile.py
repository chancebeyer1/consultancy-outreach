"""Operator profile — the sender's own background, used to ground AI drafts in TRUE facts.

Stored in app_settings.operator_bio (edited at dashboard /settings). Read fresh on each call so a
dashboard edit takes effect immediately. Shared by reply drafting (workers.reply_triage) and cold
outreach drafting (workers.draft) so both speak with the operator's real credentials.
"""

from __future__ import annotations


def operator_bio() -> str:
    """Return the operator's background text, or '' if unset / unreadable (fail-open to no context)."""
    try:
        import psycopg

        from config import require

        with psycopg.connect(require("DATABASE_URL")) as c, c.cursor() as cur:
            cur.execute("select value from app_settings where key = 'operator_bio'")
            row = cur.fetchone()
            if not row or not row[0]:
                return ""
            return row[0] if isinstance(row[0], str) else str(row[0])
    except Exception:  # noqa: BLE001
        return ""
