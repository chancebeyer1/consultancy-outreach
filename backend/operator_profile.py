"""Operator profile — the sender's own background, used to ground AI drafts in TRUE facts.

Global operator bio lives in app_settings.operator_bio (edited at dashboard /settings).
Multi-user: each profile can carry its own bio_md; drafts for a campaign speak as the
campaign OWNER, so pass the owner's user_id. A non-admin owner with no bio gets '' —
never the global bio, which is the admin's identity and would leak into their voice.
Read fresh on each call so a dashboard edit takes effect immediately.
"""

from __future__ import annotations


def operator_bio(user_id: str | None = None) -> str:
    """Background text for the sender. user_id → that profile's bio (admin falls back to
    the global app_settings bio; non-admin falls back to ''). No user_id → global bio.
    Returns '' on any failure (fail-open to no context)."""
    try:
        import psycopg

        from config import require

        with psycopg.connect(require("DATABASE_URL")) as c, c.cursor() as cur:
            if user_id:
                cur.execute("select bio_md, is_admin from profiles where id = %s", (user_id,))
                row = cur.fetchone()
                if row and row[0]:
                    return str(row[0])
                if not (row and row[1]):  # unknown user or non-admin: never the global bio
                    return ""
            cur.execute("select value from app_settings where key = 'operator_bio'")
            row = cur.fetchone()
            if not row or not row[0]:
                return ""
            return row[0] if isinstance(row[0], str) else str(row[0])
    except Exception:  # noqa: BLE001
        return ""
