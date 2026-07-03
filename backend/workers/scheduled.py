"""Scheduled follow-up replies — auto-send when due.

The operator schedules a drafted reply for a future date on /replies ("reconnect in the fall").
A daily Modal cron calls send_due_scheduled(), which sends every pending row whose due_at has
passed (LinkedIn via Unipile, email via SMTP) and marks it sent/failed. Cancelable in the UI
before it fires. Only the operator ever creates these rows — no classifier auto-schedules.
"""

from __future__ import annotations

from typing import Any

import psycopg

from clients import smtp_email, unipile
from config import require


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _pick_box() -> dict[str, Any] | None:
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select email, from_name, smtp_host, smtp_port, username, app_password
                from mailboxes where status in ('active', 'warming')
                order by email limit 1
                """
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "email": row[0], "from_name": row[1], "smtp_host": row[2],
        "smtp_port": row[3], "username": row[4], "app_password": row[5],
    }


def _mark(sid: str, status: str, error: str | None = None) -> None:
    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "update scheduled_replies set status = %s, error = %s, "
                    "sent_at = case when %s = 'sent' then now() else sent_at end where id = %s",
                    (status, error, status, sid),
                )
    finally:
        conn.close()


def send_due_scheduled(*, dry_run: bool = False, limit: int = 50) -> dict[str, Any]:
    """Send scheduled replies whose due_at has passed. Idempotent per-row (status flips to sent)."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select s.id, s.channel, s.chat_id, s.provider_id, s.body,
                       l.email, l.linkedin_url, l.provider_id,
                       p.unipile_account_id
                from scheduled_replies s
                join leads l on l.id = s.lead_id
                left join profiles p on p.id = l.user_id
                where s.status = 'pending' and s.due_at <= now()
                order by s.due_at asc
                limit %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    sent = failed = 0
    for sid, channel, chat_id, provider_id, body, email, linkedin_url, lead_pid, acct in rows:
        if dry_run:
            continue
        try:
            if str(channel or "").startswith("linkedin"):
                # acct = lead owner's connected account (multi-user); None → env global
                if chat_id:
                    unipile.send_chat_message(chat_id, body, account_id=acct)
                else:
                    pid = provider_id or lead_pid
                    if not pid and linkedin_url:
                        pid = unipile.resolve_provider_id(linkedin_url, account_id=acct)
                    if not pid:
                        raise RuntimeError("no LinkedIn send target")
                    unipile.send_linkedin_message(pid, body, account_id=acct)
            else:
                if not email:
                    raise RuntimeError("lead has no email")
                box = _pick_box()
                if not box:
                    raise RuntimeError("no available mailbox")
                smtp_email.send(
                    smtp_host=box["smtp_host"], smtp_port=box["smtp_port"],
                    username=box["username"], password=box["app_password"],
                    from_email=box["email"], from_name=box.get("from_name") or "Chance Beyer",
                    to_email=email, subject="following up", body=body,
                )
            _mark(str(sid), "sent")
            sent += 1
        except Exception as e:  # noqa: BLE001
            _mark(str(sid), "failed", str(e)[:200])
            failed += 1

    return {"due": len(rows), "sent": sent, "failed": failed, "dry_run": dry_run}
