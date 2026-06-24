"""Cold-email sender — rotates across Maildoso mailboxes, warmup-ramped.

Sends approved first-touch `email` drafts via SMTP (clients/smtp_email), choosing a
mailbox per send so volume spreads evenly across the connected boxes. Four safety
layers stack:

  1. per-box daily cap, warmup-ramped from `ramp_started_at` (5/day → 25/day over weeks)
  2. global `email` daily cap          (sender_limits.quota)
  3. per-campaign fair-share of that cap (sender_limits.campaign_share) — so a
     multi-campaign experiment stays even, same as LinkedIn
  4. only `deliverable` (MillionVerifier) addresses are ever sent

Each send is recorded in `sends` with the `mailbox_id` and the SMTP Message-ID
(external_id) so the unibox can thread replies. Idempotent: a draft with a send row,
or a lead already emailed, is skipped.
"""
from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import smtp_email
from config import Config, require
from sender_limits import campaign_daily_sent, campaign_share, quota

# Warmup ramp: cold-send ceiling per box rises with weeks since ramp_started_at.
WARMUP_BASE = 5      # week 0 cold sends/day/box (Maildoso warms the box itself on top)
WARMUP_STEP = 5      # +5 per completed week
WARMUP_MAX = 25      # mature ceiling (also the stored daily_cap)
_ACTIVE_SEND = ("queued", "sent", "delivered")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _today() -> date:
    return datetime.now(UTC).date()


def _effective_cap(daily_cap: int | None, ramp_started_at: date | None, today: date) -> int:
    """Warmup-ramped per-day ceiling for one box."""
    weeks = 99 if ramp_started_at is None else max(0, (today - ramp_started_at).days // 7)
    ramped = WARMUP_BASE + weeks * WARMUP_STEP
    return max(0, min(daily_cap or WARMUP_MAX, ramped, WARMUP_MAX))


def _split_subject(raw: str, fallback: str = "Quick question") -> tuple[str, str]:
    """Email drafts are stored as 'Subject: ...\\n\\n<body>'. Split that out; if no
    Subject: prefix, use the fallback and treat the whole thing as the body."""
    text = (raw or "").strip()
    if text.lower().startswith("subject:"):
        first, _, rest = text.partition("\n")
        subj = first.split(":", 1)[1].strip()
        return (subj or fallback, rest.strip())
    return (fallback, text)


def _load_boxes(cur, today: date) -> list[dict[str, Any]]:
    """Active/warming boxes with remaining capacity today, longest-idle first."""
    cur.execute(
        """
        select mailbox_id, count(*) from sends
        where mailbox_id is not null
          and sent_at >= now() - interval '24 hours'
          and status = any(%s)
        group by mailbox_id
        """,
        (list(_ACTIVE_SEND),),
    )
    sent_today = {str(mid): int(n) for mid, n in cur.fetchall()}

    cur.execute(
        """
        select id, email, from_name, smtp_host, smtp_port, username, app_password,
               daily_cap, ramp_started_at, last_send_at
        from mailboxes
        where status in ('active', 'warming')
        """
    )
    boxes: list[dict[str, Any]] = []
    for (mid, email, from_name, sh, sp, user, pw, cap, ramp, last) in cur.fetchall():
        remaining = _effective_cap(cap, ramp, today) - sent_today.get(str(mid), 0)
        if remaining <= 0:
            continue
        boxes.append(
            {
                "id": str(mid), "email": email, "from_name": from_name,
                "smtp_host": sh, "smtp_port": sp, "username": user, "app_password": pw,
                "remaining": remaining, "last_send_at": last,
            }
        )
    return boxes


def _next_box(boxes: list[dict], used: dict[str, int]) -> dict | None:
    """Even rotation: fewest-used-this-run, then longest-idle, with capacity left."""
    avail = [b for b in boxes if b["remaining"] - used.get(b["id"], 0) > 0]
    if not avail:
        return None
    avail.sort(key=lambda b: (used.get(b["id"], 0), b["last_send_at"] or _EPOCH))
    return avail[0]


def _record_send(draft_id: str, message_id: str, mailbox_id: str) -> None:
    """Short-lived write so we never hold a txn across a slow SMTP call."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into sends (draft_id, provider, external_id, status, sent_at, mailbox_id)
                values (%s, 'maildoso', %s, 'sent', now(), %s)
                """,
                (draft_id, message_id, mailbox_id),
            )
            cur.execute("update mailboxes set last_send_at = now() where id = %s", (mailbox_id,))


def send_email_first_touch(*, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    """Send approved first-touch `email` drafts to verified-deliverable leads."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select d.id, d.lead_id, d.body, d.edited_body,
                       l.email, l.name, l.company, l.campaign_id
                from drafts d
                join leads l on l.id = d.lead_id
                left join campaigns c on c.id = l.campaign_id
                where d.status = 'approved'
                  and d.channel = 'email'
                  and l.email is not null
                  and l.email_status = 'deliverable'
                  and (c.status is null or c.status = 'active')
                  and not exists (select 1 from sends s where s.draft_id = d.id)
                  and not exists (
                      select 1 from sends s2
                      join drafts d2 on d2.id = s2.draft_id
                      where d2.lead_id = d.lead_id and d2.channel = 'email'
                  )
                order by d.generated_at asc
                """
            )
            rows = cur.fetchall()
            cur.execute("select count(*) from campaigns where status = 'active'")
            n_campaigns = int((cur.fetchone() or [1])[0] or 1)
            today = _today()
            boxes = _load_boxes(cur, today)

    if limit is not None:
        rows = rows[:limit]

    pushed: list[dict] = []
    blocked_quota: list[str] = []
    blocked_fairness: list[str] = []
    blocked_no_box: list[str] = []
    failed: list[dict] = []

    email_left = quota("email").allowed
    cam_window = campaign_daily_sent("email")
    cam_run: dict[str, int] = {}
    used: dict[str, int] = {}

    for draft_id, lead_id, body, edited_body, email, name, company, campaign_id in rows:
        cid = str(campaign_id) if campaign_id else None
        subject, send_body = _split_subject(edited_body or body)

        if dry_run:
            box = _next_box(boxes, used)
            pushed.append({"lead_id": str(lead_id), "to": email, "subject": subject,
                           "via": box["email"] if box else None})
            if box:
                used[box["id"]] = used.get(box["id"], 0) + 1
            continue

        if email_left <= 0:
            blocked_quota.append(str(lead_id))
            continue
        # Per-campaign fair share of the global email cap.
        if cid and n_campaigns > 1:
            share_used = cam_window.get(cid, 0) + cam_run.get(cid, 0)
            if share_used >= campaign_share("email", n_campaigns):
                blocked_fairness.append(str(lead_id))
                continue

        box = _next_box(boxes, used)
        if box is None:
            blocked_no_box.append(str(lead_id))
            continue

        try:
            resp = smtp_email.send(
                smtp_host=box["smtp_host"], smtp_port=box["smtp_port"],
                username=box["username"], password=box["app_password"],
                from_email=box["email"], from_name=box["from_name"],
                to_email=email, subject=subject, body=send_body,
            )
            _record_send(str(draft_id), resp.get("message_id", ""), box["id"])
            used[box["id"]] = used.get(box["id"], 0) + 1
            email_left -= 1
            cam_run[cid] = cam_run.get(cid, 0) + 1 if cid else 0
            pushed.append({"lead_id": str(lead_id), "to": email, "via": box["email"]})
        except Exception as e:  # noqa: BLE001
            failed.append({"lead_id": str(lead_id), "via": box["email"], "error": str(e)[:200]})

    return {
        "candidates": len(rows),
        "pushed": len(pushed),
        "blocked_quota": len(blocked_quota),
        "blocked_fairness": len(blocked_fairness),
        "blocked_no_box": len(blocked_no_box),
        "failed": len(failed),
        "boxes_available": len(boxes),
        "details": {"pushed": pushed, "failed": failed},
        "dry_run": dry_run,
    }


def _pick_one_box() -> dict | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            boxes = _load_boxes(cur, _today())
    return _next_box(boxes, {}) if boxes else None


def notify(subject: str, body: str, *, to_email: str | None = None) -> dict[str, Any]:
    """Send an internal notification (e.g. 'new reply') from a Maildoso box."""
    dest = to_email or Config.notify_email
    if not dest:
        return {"sent": False, "reason": "NOTIFY_EMAIL not set"}
    box = _pick_one_box()
    if not box:
        return {"sent": False, "reason": "no available mailbox"}
    resp = smtp_email.send(
        smtp_host=box["smtp_host"], smtp_port=box["smtp_port"],
        username=box["username"], password=box["app_password"],
        from_email=box["email"], from_name="Outreach Bot",
        to_email=dest, subject=subject, body=body,
    )
    return {"sent": True, "via": box["email"], "to": dest, "message_id": resp.get("message_id")}


def send_test(to_email: str) -> dict[str, Any]:
    """One real send to prove end-to-end SMTP deliverability (not just login)."""
    box = _pick_one_box()
    if not box:
        return {"sent": False, "reason": "no available mailbox"}
    resp = smtp_email.send(
        smtp_host=box["smtp_host"], smtp_port=box["smtp_port"],
        username=box["username"], password=box["app_password"],
        from_email=box["email"], from_name=box["from_name"],
        to_email=to_email,
        subject="Maildoso deliverability test",
        body="This is an automated test send from the outreach system. "
             "If you can read this, SMTP sending works end to end.",
    )
    return {"sent": True, "via": box["email"], "to": to_email, "message_id": resp.get("message_id")}
