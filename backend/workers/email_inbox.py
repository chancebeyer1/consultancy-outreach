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

from campaigns_loader import load_campaign
from clients import smtp_email
from config import require
from workers import email_sender, reply_triage

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
            "select id, campaign_id, name, role, company from leads where lower(email) = lower(%s) limit 1",
            (from_email,),
        )
        row = cur.fetchone()
        if row:
            return row
    if in_reply_to:
        cur.execute(
            """
            select l.id, l.campaign_id, l.name, l.role, l.company
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
            m["_box_id"] = _mid
            fetched.append(m)

    # 2. Store EVERY inbound into the unified inbox (the boxes' INBOX is warmup-free, so this
    # is real mail only), then raise curated alerts for the human, lead-matched ones.
    auto = skipped = stored = inbox_stored = 0
    new_replies: list[dict] = []
    camp_cache: dict[str, Any] = {}

    def _campaign(cid: str | None):
        if not cid:
            return None
        if cid not in camp_cache:
            try:
                camp_cache[cid] = load_campaign(cid)
            except Exception:  # noqa: BLE001
                camp_cache[cid] = None
        return camp_cache[cid]

    with _connect() as conn:
        with conn.cursor() as cur:
            for m in fetched:
                is_auto = _is_auto(m)
                lead = _resolve_lead(cur, m.get("from_email", ""), m.get("in_reply_to"))
                lead_id = lead[0] if lead else None
                campaign_id = lead[1] if lead else None
                lead_name = lead[2] if lead else None
                lead_role = lead[3] if lead else None
                lead_company = lead[4] if lead else None
                mid = m.get("message_id") or None

                already = False
                if mid and lead and not is_auto:
                    cur.execute("select 1 from replies where external_id = %s", (mid,))
                    already = cur.fetchone() is not None

                # Matched human reply → draft a campaign-aware response + classify it. Only the
                # few real replies cost an LLM call; the inbox composer pre-fills with it.
                cls: dict[str, Any] = {}
                if lead and not is_auto and not already:
                    try:
                        cls = reply_triage.classify_reply(
                            reply_body=(m.get("body") or "")[:4000],
                            original_message=None,
                            lead_name=lead_name, lead_role=lead_role, lead_company=lead_company,
                            campaign=_campaign(str(campaign_id) if campaign_id else None),
                        )
                    except Exception:  # noqa: BLE001
                        cls = {}
                suggested = cls.get("suggested_reply")

                if not dry_run:
                    cur.execute(
                        """
                        insert into inbox_messages
                            (mailbox_id, mailbox_email, from_email, from_name, subject, body,
                             message_id, in_reply_to, lead_id, campaign_id, is_auto,
                             suggested_reply, received_at)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                        on conflict (message_id) do nothing
                        """,
                        (m.get("_box_id"), m.get("_box"), m.get("from_email"), m.get("from_name"),
                         m.get("subject"), (m.get("body") or "")[:8000], mid, m.get("in_reply_to"),
                         lead_id, campaign_id, is_auto, suggested),
                    )
                    inbox_stored += 1

                if is_auto:
                    auto += 1
                    continue
                if not lead:
                    skipped += 1  # in the inbox, but not tied to our outreach → no alert
                    continue
                if already:
                    continue
                rec = {
                    "lead_id": str(lead_id), "campaign_id": str(campaign_id) if campaign_id else None,
                    "lead_name": lead_name, "from_email": m.get("from_email"),
                    "subject": m.get("subject"), "body": (m.get("body") or "")[:4000],
                }
                if not dry_run:
                    cur.execute(
                        """
                        insert into replies
                            (lead_id, channel, external_id, body, sentiment, intent, summary,
                             suggested_reply, next_action, received_at)
                        values (%s, 'email', %s, %s, %s, %s, %s, %s, %s, now())
                        """,
                        (lead_id, mid, rec["body"], cls.get("sentiment"), cls.get("intent"),
                         cls.get("summary"), suggested, cls.get("next_action")),
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
        "inbox_stored": inbox_stored,
        "auto_filtered": auto,
        "noise_skipped": skipped,
        "replies_stored": stored,
        "alerts_sent": notified,
        "errors": errors,
        "dry_run": dry_run,
        "details": {"replies": [{k: r[k] for k in ("lead_name", "from_email", "subject")} for r in new_replies]},
    }
