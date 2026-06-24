"""Append-only activity log — one row per meaningful action, for audit + the /activity feed.

Every action emits to stdout (so it shows in Modal logs) AND best-effort to the
`activity_log` table. Logging must NEVER break the action it describes, so any DB error
is swallowed. Granular per-entity records (each send/reply/lead) also live in their domain
tables (sends / replies / inbox_messages); this is the unified, human-readable timeline.
"""
from __future__ import annotations

import logging
from typing import Any

from config import Config

logger = logging.getLogger("outreach")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def log(
    action: str,
    *,
    summary: str | None = None,
    actor: str = "system",
    source: str = "worker",
    channel: str | None = None,
    entity_type: str | None = None,
    entity_id: Any = None,
    campaign_id: Any = None,
    lead_id: Any = None,
    meta: dict | None = None,
) -> None:
    """Record one action. Resilient: never raises."""
    logger.info("[%s] %s %s", action, summary or "", meta or "")
    url = Config.database_url
    if not url:
        return
    try:
        import psycopg
        from psycopg.types.json import Jsonb

        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into activity_log
                        (actor, action, source, channel, entity_type, entity_id,
                         campaign_id, lead_id, summary, meta)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        actor, action, source, channel, entity_type,
                        str(entity_id) if entity_id else None,
                        str(campaign_id) if campaign_id else None,
                        str(lead_id) if lead_id else None,
                        summary,
                        Jsonb(meta) if meta is not None else None,
                    ),
                )
    except Exception:
        pass  # logging must never break the action it describes
