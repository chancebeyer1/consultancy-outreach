"""Postgres persistence for reply records.

Used by the Modal cron path. Local CLI path uses runs/replies.jsonl instead
(see scripts/pull_replies.py). The two share the worker that fetches +
classifies (workers/replies.fetch_and_classify_new_replies); this module
just handles the write.

Idempotency: replies.external_id is unique-indexed, so the upsert is a
straight ON CONFLICT (external_id) DO NOTHING. The set of already-seen
message ids is also queryable for the worker's seen_message_ids parameter.
"""

from __future__ import annotations

from typing import Any

from config import require


def _connect():
    """Open a psycopg connection. Imported lazily so the local CLI doesn't
    require the [worker] extras."""
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError(
            "psycopg not installed. Run: uv sync --extra worker"
        ) from e
    return psycopg.connect(require("DATABASE_URL"), autocommit=False)


def existing_external_ids(limit: int = 5000) -> set[str]:
    """Return external_ids already persisted. Caller passes this to
    workers.replies.fetch_and_classify_new_replies as seen_message_ids.

    Limited by `limit` rows (newest first) so we don't pull the whole table
    every cron tick. 5000 is well above any realistic 15-min batch size.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select external_id from replies "
                "where external_id is not null "
                "order by received_at desc "
                "limit %s",
                (limit,),
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def _ensure_lead(cur, *, linkedin_url: str | None, name: str | None, company: str | None) -> str | None:
    """Resolve lead_id for a reply.

    If we already have the lead, return its id. Otherwise insert a stub
    so the foreign key references something real. Returns None only when
    the reply has no linkedin_url to anchor on (rare — orphan reply).
    """
    if not linkedin_url:
        return None
    cur.execute("select id from leads where linkedin_url = %s", (linkedin_url,))
    row = cur.fetchone()
    if row:
        return row[0]

    # Stub: minimal lead so the FK resolves. Marked as 'replied' status
    # since we only get here if a reply just landed.
    cur.execute(
        """
        insert into leads (linkedin_url, name, company, status, source, trigger)
        values (%s, %s, %s, 'replied', 'reply_orphan', 'list')
        on conflict (linkedin_url) do nothing
        returning id
        """,
        (linkedin_url, name, company),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    # Race: another writer inserted between SELECT and INSERT. Re-read.
    cur.execute("select id from leads where linkedin_url = %s", (linkedin_url,))
    row = cur.fetchone()
    return row[0] if row else None


def insert_replies(records: list[dict[str, Any]]) -> dict[str, int]:
    """Insert classified reply records. Returns counts.

    Each record is the shape returned by
    workers.replies.fetch_and_classify_new_replies — keyed by message_id +
    classification fields. Skips dupes via ON CONFLICT (external_id).
    """
    if not records:
        return {"inserted": 0, "skipped": 0, "orphan": 0}

    conn = _connect()
    inserted = 0
    skipped = 0
    orphan = 0
    try:
        with conn:
            with conn.cursor() as cur:
                for rec in records:
                    lead_id = _ensure_lead(
                        cur,
                        linkedin_url=rec.get("linkedin_url"),
                        name=rec.get("lead_name"),
                        company=rec.get("lead_company"),
                    )
                    if lead_id is None:
                        orphan += 1
                        # Persist anyway — lead_id is nullable.
                    cur.execute(
                        """
                        insert into replies
                            (lead_id, channel, external_id, body,
                             sentiment, intent, summary, suggested_reply,
                             next_action, received_at)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        on conflict (external_id) do nothing
                        """,
                        (
                            lead_id,
                            rec.get("channel") or "linkedin_dm",
                            rec.get("message_id"),
                            rec.get("body") or "",
                            rec.get("sentiment"),
                            rec.get("intent"),
                            rec.get("summary"),
                            rec.get("suggested_reply"),
                            rec.get("next_action"),
                            rec.get("received_at"),
                        ),
                    )
                    if cur.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1
    finally:
        conn.close()
    return {"inserted": inserted, "skipped": skipped, "orphan": orphan}
