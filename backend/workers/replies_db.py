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


def known_lead_keys() -> tuple[set[str], set[str]]:
    """(provider_ids, linkedin_urls) for every lead — lets the reply poller skip
    classifying messages from people we never contacted, saving the LLM call."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("select provider_id, linkedin_url from leads")
            pids: set[str] = set()
            urls: set[str] = set()
            for pid, url in cur.fetchall():
                if pid:
                    pids.add(pid)
                if url:
                    urls.add(url)
            return pids, urls
    finally:
        conn.close()


def is_known_lead(*, provider_id: str | None = None, linkedin_url: str | None = None) -> bool:
    """Whether a provider_id / linkedin_url belongs to a lead we contacted."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            if provider_id:
                cur.execute("select 1 from leads where provider_id = %s limit 1", (provider_id,))
                if cur.fetchone():
                    return True
            if linkedin_url:
                cur.execute("select 1 from leads where linkedin_url = %s limit 1", (linkedin_url,))
                if cur.fetchone():
                    return True
            return False
    finally:
        conn.close()


def _match_lead(cur, *, provider_id: str | None, linkedin_url: str | None) -> str | None:
    """Resolve lead_id for a reply by matching someone we actually contacted.

    Match by LinkedIn provider_id first (the reliable member-id key, stored when we
    contact a lead), then by linkedin_url. We do NOT create stub leads: a message
    from someone not in our pipeline returns None, and insert_replies drops it — so
    the operator's normal inbox never leaks into /replies.
    """
    if provider_id:
        cur.execute("select id from leads where provider_id = %s", (provider_id,))
        row = cur.fetchone()
        if row:
            return row[0]
    if linkedin_url:
        cur.execute("select id from leads where linkedin_url = %s", (linkedin_url,))
        row = cur.fetchone()
        if row:
            return row[0]
    return None


def _connect_draft_id(cur, lead_id) -> str | None:
    """The lead's connect-note draft id — it carries the A/B variant. Attributing a LinkedIn reply
    back to it lets us measure reply rate (not just accept rate) per connect-note variant."""
    cur.execute(
        "select id from drafts where lead_id = %s and channel = 'linkedin_connect' "
        "order by generated_at asc limit 1",
        (lead_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def insert_replies(records: list[dict[str, Any]]) -> dict[str, int]:
    """Insert classified reply records. Returns counts.

    Each record is the shape returned by
    workers.replies.fetch_and_classify_new_replies — keyed by message_id +
    classification fields. Skips dupes via ON CONFLICT (external_id).
    """
    if not records:
        return {"inserted": 0, "skipped": 0, "dropped": 0}

    conn = _connect()
    inserted = 0
    skipped = 0
    dropped = 0
    new_alerts: list[dict[str, Any]] = []
    try:
        with conn:
            with conn.cursor() as cur:
                for rec in records:
                    lead_id = _match_lead(
                        cur,
                        provider_id=rec.get("provider_id"),
                        linkedin_url=rec.get("linkedin_url"),
                    )
                    if lead_id is None:
                        # Not a lead we've contacted — inbox noise, don't persist.
                        dropped += 1
                        continue
                    draft_id = _connect_draft_id(cur, lead_id)
                    cur.execute(
                        """
                        insert into replies
                            (lead_id, draft_id, channel, external_id, body,
                             sentiment, intent, summary, suggested_reply,
                             next_action, received_at, chat_id)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        on conflict (external_id) where external_id is not null do nothing
                        """,
                        (
                            lead_id,
                            draft_id,
                            rec.get("channel") or "linkedin_dm",
                            rec.get("message_id"),
                            rec.get("body") or "",
                            rec.get("sentiment"),
                            rec.get("intent"),
                            rec.get("summary"),
                            rec.get("suggested_reply"),
                            rec.get("next_action"),
                            rec.get("received_at"),
                            rec.get("chat_id"),
                        ),
                    )
                    if cur.rowcount > 0:
                        inserted += 1
                        if (rec.get("intent") or "") != "oof":  # don't ping on OOO auto-replies
                            new_alerts.append(rec)
                    else:
                        skipped += 1
    finally:
        conn.close()

    # Alert the operator on each new (non-OOO) LinkedIn reply — email replies alert in email_inbox,
    # so this closes the gap where LinkedIn replies fired no notification at all.
    for rec in new_alerts:
        try:
            from workers.email_sender import notify

            who = rec.get("lead_name") or "a lead"
            notify(
                subject=f"New LinkedIn reply from {who}",
                body=f"{who} just replied on LinkedIn:\n\n{(rec.get('body') or '')[:600]}\n\n"
                f"Open the Replies page to respond.",
            )
        except Exception:  # noqa: BLE001 — a notification failure must never break ingestion
            pass
    return {"inserted": inserted, "skipped": skipped, "dropped": dropped}
