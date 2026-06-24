"""Unibox — sweep all Maildoso inboxes via IMAP, surface real prospect replies.

Polls each active mailbox for unseen INBOX mail, then keeps ONLY messages tied to our
outreach — matched to a lead by sender address, or threaded to one of our sends
(In-Reply-To -> sends.external_id). Everything else (warmup traffic, newsletters,
cold noise) is ignored, so the alerts stay signal-only. Auto-responders / OOO are
filtered out. Each kept reply is stored (channel='email', deduped on Message-ID) and
triggers a notification to NOTIFY_EMAIL, sent from a Maildoso box.

Messages are marked seen as they're read, so each is processed exactly once.
"""
from __future__ import annotations

import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import smtp_email
from config import require
from workers import email_sender

# Subject/sender markers for machine-generated mail we never alert on.
_AUTO_SUBJECT = (
    "out of office", "out of the office", "automatic reply", "auto-reply", "autoreply",
    "auto response", "automatic response", "away from", "on vacation", "delivery status",
    "undeliverable", "mail delivery failed", "returned mail",
)
_AUTO_SENDER = ("mailer-daemon", "postmaster", "no-reply", "noreply", "donotreply", "bounce")


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _is_auto(msg: dict) -> bool:
    subj = (msg.get("subject") or "").lower()
    if any(k in subj for k in _AUTO_SUBJECT):
        return True
    frm = (msg.get("from_email") or "").lower()
    return frm.startswith(_AUTO_SENDER) or not frm


def _resolve_lead(cur, from_email: str, in_reply_to: str | None) -> tuple | None:
    """Resolve a reply to a lead: first by sender address, then by thread."""
    if from_email:
        cur.execute(
            "select id, campaign_id, name from leads where lower(email) = lower(%s) limit 1",
            (from_email,),
        )
        row = cur.fetchone()
        if row:
            return row
    if in_reply_to:
        cur.execute(
            """
            select l.id, l.campaign_id, l.name
            from sends s
            join drafts d on d.id = s.draft_id
            join leads l on l.id = d.lead_id
            where s.external_id = %s
            limit 1
            """,
            (in_reply_to,),
        )
        row = cur.fetchone()
        if row:
            return row
    return None


def poll_inboxes(*, limit_per_box: int = 25, dry_run: bool = False, notify_alerts: bool = True) -> dict[str, Any]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select id, email, imap_host, imap_port, username, app_password
                from mailboxes where status in ('active', 'warming')
                """
            )
            boxes = cur.fetchall()

    # 1. Fetch unseen mail from every box (network only; no DB held).
    fetched: list[dict] = []
    errors: list[dict] = []
    for (_mid, email, ih, ip, user, pw) in boxes:
        try:
            msgs = smtp_email.fetch_replies(
                imap_host=ih, imap_port=ip, username=user, password=pw,
                unseen_only=True, limit=limit_per_box, mark_seen=not dry_run,
            )
        except Exception as e:  # noqa: BLE001
            errors.append({"box": email, "error": str(e)[:160]})
            continue
        for m in msgs:
            m["_box"] = email
            fetched.append(m)

    # 2. Keep only real prospect replies; store them (one DB connection, fast work).
    auto = skipped = stored = 0
    new_replies: list[dict] = []
    with _connect() as conn:
        with conn.cursor() as cur:
            for m in fetched:
                if _is_auto(m):
                    auto += 1
                    continue
                lead = _resolve_lead(cur, m.get("from_email", ""), m.get("in_reply_to"))
                if not lead:
                    skipped += 1  # warmup / unrelated noise
                    continue
                lead_id, campaign_id, lead_name = lead
                mid = m.get("message_id") or None
                if mid:
                    cur.execute("select 1 from replies where external_id = %s", (mid,))
                    if cur.fetchone():
                        continue  # already ingested
                rec = {
                    "lead_id": str(lead_id), "campaign_id": str(campaign_id) if campaign_id else None,
                    "lead_name": lead_name, "from_email": m.get("from_email"),
                    "subject": m.get("subject"), "body": (m.get("body") or "")[:4000],
                }
                if not dry_run:
                    cur.execute(
                        """
                        insert into replies (lead_id, channel, external_id, body, received_at)
                        values (%s, 'email', %s, %s, now())
                        """,
                        (lead_id, mid, rec["body"]),
                    )
                    stored += 1
                new_replies.append(rec)

    # 3. Alert on every (human, matched) reply, sent from a Maildoso box.
    notified = 0
    if notify_alerts and not dry_run:
        for r in new_replies:
            body = (
                f"From: {r['from_email']}\n"
                f"Lead: {r['lead_name'] or '(unknown)'}\n"
                f"Subject: {r['subject'] or '(none)'}\n\n"
                f"{r['body'][:1500]}\n\n"
                f"— open the unibox to reply."
            )
            try:
                if email_sender.notify(subject=f"New reply from {r['lead_name'] or r['from_email']}", body=body).get("sent"):
                    notified += 1
            except Exception as e:  # noqa: BLE001
                errors.append({"notify": r["from_email"], "error": str(e)[:160]})

    return {
        "boxes_polled": len(boxes),
        "fetched": len(fetched),
        "auto_filtered": auto,
        "noise_skipped": skipped,
        "replies_stored": stored,
        "alerts_sent": notified,
        "errors": errors,
        "dry_run": dry_run,
        "details": {"replies": [{k: r[k] for k in ("lead_name", "from_email", "subject")} for r in new_replies]},
    }
