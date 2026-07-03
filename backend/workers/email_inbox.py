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

import re

import psycopg

from campaigns_loader import load_campaign
from clients import smtp_email
from config import Config, require
from workers import email_sender, reply_triage

# Subject/sender markers for machine-generated mail we never alert on.
_AUTO_SUBJECT = (
    "out of office", "out of the office", "automatic reply", "auto-reply", "autoreply",
    "auto response", "automatic response", "away from", "on vacation", "delivery status",
    "undeliverable", "mail delivery failed", "returned mail",
)
_AUTO_SENDER = ("mailer-daemon", "postmaster", "no-reply", "noreply", "donotreply", "bounce")

# Warmup-network signature (Instantly etc.): a "tracking code" — an ALL-CAPS alphanumeric
# token, 5-9 chars, mixing at least one LETTER and one DIGIT (e.g. 'E7C6SPF', 'H8QB7KX').
# Every warmup email a box receives carries one (constant per box) in both subject and body,
# next to a random tag that varies in form ('REYBPMS …', 'count__please …', 'blood__glad …').
# Ordinary words never mix capitals and digits, so the code itself is the clean, format-proof
# fingerprint — we don't depend on the tag beside it.
_WARMUP_CODE = re.compile(r"\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{5,9}\b")
_WARMUP_PHRASES = (
    "take you off our list",
    "read your thoughts about this post",
    "idea for a new website",
    "idea for a new app",
    "enjoying your weekly newsletter",
    "send you a new quote",
    "add me on facebook",
    "thanks for signing up on our website",
    "spoke with your advisor",
    "add to my newsletter",
)


def _has_tracking_code(text: str) -> bool:
    return bool(_WARMUP_CODE.search(text))


def _is_warmup(msg: dict) -> bool:
    """True for email-warmup traffic (Instantly's network) so it never enters the inbox.

    Callers gate this on "not matched to a lead" so a genuine prospect reply that happens to
    contain a code-like token is never mistaken for warmup.
    """
    subject = msg.get("subject") or ""
    body = msg.get("body") or ""
    if _has_tracking_code(subject) or _has_tracking_code(body):
        return True
    low = f"{subject} {body}".lower()
    return any(p in low for p in _WARMUP_PHRASES)


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _is_auto(msg: dict) -> bool:
    subj = (msg.get("subject") or "").lower()
    if any(k in subj for k in _AUTO_SUBJECT):
        return True
    frm = (msg.get("from_email") or "").lower()
    return frm.startswith(_AUTO_SENDER) or not frm


# Bounce / non-delivery report signatures (a superset of the auto markers, focused on hard
# failures we act on). When one lands we mark the failed lead and tally the box's health.
_BOUNCE_SENDER = ("mailer-daemon", "postmaster", "mail-daemon")
_BOUNCE_SUBJECT = (
    "undeliverable", "delivery status notification", "mail delivery failed", "returned mail",
    "failure notice", "delivery has failed", "address not found", "could not be delivered",
    "delivery incomplete", "message not delivered", "delivery failure",
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
BOUNCE_PAUSE_THRESHOLD = 5  # cumulative bounces on a box before we auto-pause it


def _is_bounce(msg: dict) -> bool:
    frm = (msg.get("from_email") or "").lower()
    if frm.startswith(_BOUNCE_SENDER):
        return True
    subj = (msg.get("subject") or "").lower()
    return any(k in subj for k in _BOUNCE_SUBJECT)


def _handle_bounce(cur, m: dict) -> None:
    """A delivery failure landed in a box: mark the failed recipient's lead 'bounced' (no more
    touches), tally the box's bounce_count, and auto-pause a box past the threshold — a high
    bounce rate wrecks domain reputation, so we stop sending from it until it's reviewed."""
    body = m.get("body") or ""
    box_id = m.get("_box_id")
    box_email = (m.get("_box") or "").lower()
    for addr in {a.lower() for a in _EMAIL_RE.findall(body)}:
        if addr == box_email or addr.startswith(_BOUNCE_SENDER) or "daemon" in addr:
            continue
        cur.execute(
            "update leads set email_status = 'bounced', updated_at = now() "
            "where lower(email) = %s and coalesce(email_status, '') <> 'bounced'",
            (addr,),
        )
    if not box_id:
        return
    cur.execute(
        "update mailboxes set bounce_count = bounce_count + 1, last_error = %s, "
        "updated_at = now() where id = %s returning bounce_count, status",
        (f"bounce: {(m.get('subject') or '')[:140]}", box_id),
    )
    row = cur.fetchone()
    if row and row[0] >= BOUNCE_PAUSE_THRESHOLD and row[1] in ("active", "warming"):
        cur.execute("update mailboxes set status = 'paused', updated_at = now() where id = %s", (box_id,))
        try:
            from activity import log as _alog

            _alog(
                "mailbox_paused", source="worker", channel="email",
                summary=f"Auto-paused {m.get('_box')} after {row[0]} bounces",
                meta={"mailbox": m.get("_box"), "bounce_count": row[0]},
            )
        except Exception:  # noqa: BLE001
            pass


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


def _email_opener_draft_id(cur, lead_id) -> str | None:
    """The lead's first-touch email draft id — it carries the A/B variant. A reply anywhere in the
    thread counts for the opener's variant, so we attribute every email reply back to it."""
    cur.execute(
        "select id from drafts where lead_id = %s and channel = 'email' and step_index = 0 "
        "order by generated_at asc limit 1",
        (lead_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


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
    auto = skipped = stored = inbox_stored = warmup = bounced = 0
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
                # Delivery-failure reports: mark the bounced lead + box health, then drop it
                # (never store or alert). Auto-pauses a box with too many bounces.
                if _is_bounce(m):
                    _handle_bounce(cur, m)
                    bounced += 1
                    continue
                is_auto = _is_auto(m)
                lead = _resolve_lead(cur, m.get("from_email", ""), m.get("in_reply_to"))
                # Warmup-network traffic (Instantly) carries a tracking code and never comes
                # from one of our leads. Gating on "no lead match" means a real prospect reply
                # is never dropped, even if its text happens to contain a code-like token.
                if not lead and _is_warmup(m):
                    warmup += 1
                    continue  # never store or alert
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
                    # Store OOO / auto-replies in /replies too — greyed as 'oof' — so the replies
                    # page is the complete inbox and /inbox can retire. No LLM call, no alert.
                    if lead and not dry_run:
                        draft_id = _email_opener_draft_id(cur, lead_id)
                        cur.execute(
                            """
                            insert into replies
                                (lead_id, draft_id, channel, external_id, body, sentiment, intent,
                                 summary, suggested_reply, next_action, received_at)
                            values (%s, %s, 'email', %s, %s, 'neutral', 'oof', %s, null, null, now())
                            on conflict (external_id) where external_id is not null do nothing
                            """,
                            (lead_id, draft_id, mid, (m.get("body") or "")[:4000],
                             "Out-of-office / automatic reply"),
                        )
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
                    draft_id = _email_opener_draft_id(cur, lead_id)
                    cur.execute(
                        """
                        insert into replies
                            (lead_id, draft_id, channel, external_id, body, sentiment, intent, summary,
                             suggested_reply, next_action, received_at)
                        values (%s, %s, 'email', %s, %s, %s, %s, %s, %s, %s, now())
                        """,
                        (lead_id, draft_id, mid, rec["body"], cls.get("sentiment"), cls.get("intent"),
                         cls.get("summary"), suggested, cls.get("next_action")),
                    )
                    stored += 1
                    # A clear buying signal → open a deal in the pipeline (idempotent).
                    if cls.get("intent") == "interested":
                        try:
                            from workers.deals import ensure_deal

                            ensure_deal(str(lead_id), source="reply", cur=cur)
                        except Exception:  # noqa: BLE001
                            pass
                new_replies.append(rec)
                try:
                    from activity import log as _alog

                    _alog(
                        "reply_received", source="worker", channel="email",
                        lead_id=rec.get("lead_id"), campaign_id=rec.get("campaign_id"),
                        summary=f"Reply from {rec.get('lead_name') or rec.get('from_email')}",
                        meta={"from": rec.get("from_email"), "subject": rec.get("subject")},
                    )
                except Exception:  # noqa: BLE001
                    pass

    # 3. Alert on every (human, matched) reply, sent from a Maildoso box. Multi-user: the
    # lead OWNER (leads.user_id → profiles.email) gets the ping, and the admin NOTIFY_EMAIL
    # always does too (deduped when they're the same; owner lookup is best-effort).
    notified = 0
    if notify_alerts and not dry_run:
        owner_emails: dict[str, str] = {}
        lead_ids = [r["lead_id"] for r in new_replies if r.get("lead_id")]
        if lead_ids:
            try:
                with _connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "select l.id, p.email from leads l "
                            "join profiles p on p.id = l.user_id "
                            "where l.id = any(%s::uuid[]) and p.email is not null",
                            (lead_ids,),
                        )
                        owner_emails = {str(lid): em for lid, em in cur.fetchall()}
            except Exception:  # noqa: BLE001 — owner lookup failing must not kill the alerts
                owner_emails = {}
        for r in new_replies:
            body = (
                f"From: {r['from_email']}\n"
                f"Lead: {r['lead_name'] or '(unknown)'}\n"
                f"Subject: {r['subject'] or '(none)'}\n\n"
                f"{r['body'][:1500]}\n\n"
                f"— open the unibox to reply."
            )
            pinged: set[str] = set()
            for dest in (owner_emails.get(r.get("lead_id") or ""), Config.notify_email or None):
                if not dest or dest.lower() in pinged:
                    continue
                pinged.add(dest.lower())
                try:
                    if email_sender.notify(
                        subject=f"New reply from {r['lead_name'] or r['from_email']}",
                        body=body, to_email=dest,
                    ).get("sent"):
                        notified += 1
                except Exception as e:  # noqa: BLE001
                    errors.append({"notify": r["from_email"], "error": str(e)[:160]})

    return {
        "boxes_polled": len(boxes),
        "fetched": len(fetched),
        "warmup_filtered": warmup,
        "bounces_handled": bounced,
        "inbox_stored": inbox_stored,
        "auto_filtered": auto,
        "noise_skipped": skipped,
        "replies_stored": stored,
        "alerts_sent": notified,
        "errors": errors,
        "dry_run": dry_run,
        "details": {"replies": [{k: r[k] for k in ("lead_name", "from_email", "subject")} for r in new_replies]},
    }
