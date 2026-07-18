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

from config import Config, require


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


def known_lead_keys(user_id: str | None = None) -> tuple[set[str], set[str]]:
    """(provider_ids, linkedin_urls) for every lead — lets the reply poller skip
    classifying messages from people we never contacted, saving the LLM call.

    `user_id` scopes the keys to that owner's leads for per-account reply pulls;
    unowned (user_id IS NULL) leads are always included so pre-backfill rows keep
    matching. None → all leads (the global single-user behavior)."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            if user_id:
                cur.execute(
                    "select provider_id, linkedin_url from leads "
                    "where user_id = %s or user_id is null",
                    (user_id,),
                )
            else:
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


def is_known_lead(
    *, provider_id: str | None = None, linkedin_url: str | None = None, user_id: str | None = None
) -> bool:
    """Whether a provider_id / linkedin_url belongs to a lead we contacted.

    `user_id` scopes the check to that owner's leads (unowned leads always match,
    same as known_lead_keys). None → any lead."""
    owner_clause = " and (user_id = %s or user_id is null)" if user_id else ""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            if provider_id:
                cur.execute(
                    f"select 1 from leads where provider_id = %s{owner_clause} limit 1",
                    (provider_id, user_id) if user_id else (provider_id,),
                )
                if cur.fetchone():
                    return True
            if linkedin_url:
                cur.execute(
                    f"select 1 from leads where linkedin_url = %s{owner_clause} limit 1",
                    (linkedin_url, user_id) if user_id else (linkedin_url,),
                )
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


def _owner_email(cur, lead_id) -> str | None:
    """The lead OWNER's login email (leads.user_id → profiles.email) — who gets the
    new-reply notification. None for unowned leads (admin NOTIFY_EMAIL still fires)."""
    cur.execute(
        "select p.email from leads l join profiles p on p.id = l.user_id where l.id = %s",
        (lead_id,),
    )
    row = cur.fetchone()
    return row[0] if row and row[0] else None


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
    new_alerts: list[tuple[dict[str, Any], str | None]] = []  # (record, owner email)
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
                        # A clear buying signal → open a deal in the pipeline (idempotent).
                        # Mirrors the email path (email_inbox) — before this, LinkedIn
                        # "interested" replies never created deals.
                        if (rec.get("intent") or "") == "interested":
                            try:
                                from workers.deals import ensure_deal

                                ensure_deal(str(lead_id), source="reply", cur=cur)
                            except Exception:  # noqa: BLE001 — never break reply ingestion
                                pass
                        if (rec.get("intent") or "") != "oof":  # don't ping on OOO auto-replies
                            new_alerts.append((rec, _owner_email(cur, lead_id)))
                    else:
                        skipped += 1
    finally:
        conn.close()

    # Alert on each new (non-OOO) LinkedIn reply — email replies alert in email_inbox,
    # so this closes the gap where LinkedIn replies fired no notification at all.
    # Multi-user: the lead OWNER gets the ping, and the admin NOTIFY_EMAIL always does
    # too (deduped when they're the same address; unset addresses just skip).
    for rec, owner_email in new_alerts:
        who = rec.get("lead_name") or "a lead"
        pinged: set[str] = set()
        for dest in (owner_email, Config.notify_email or None):
            if not dest or dest.lower() in pinged:
                continue
            pinged.add(dest.lower())
            try:
                from workers.email_sender import notify

                notify(
                    subject=f"New LinkedIn reply from {who}",
                    body=f"{who} just replied on LinkedIn:\n\n{(rec.get('body') or '')[:600]}\n\n"
                    f"Open the Replies page to respond.",
                    to_email=dest,
                )
            except Exception:  # noqa: BLE001 — a notification failure must never break ingestion
                pass
    return {"inserted": inserted, "skipped": skipped, "dropped": dropped}
