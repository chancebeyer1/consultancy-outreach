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

import random
import sys
import time
from datetime import UTC, date, datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import smtp_email
from config import FREE_EMAIL_DOMAINS, Config, is_corporate_email, require
from sender_limits import campaign_daily_sent, campaign_share, quota

# Warmup ramp: cold-send ceiling per box rises with weeks since ramp_started_at, so volume
# scales to full automatically as the domains age (no manual flip). Starts at a safe trickle
# for fresh domains and climbs to ~25/box (30 boxes x 25 = the 750/day global cap) over ~6
# weeks. To go full immediately once you've confirmed the domains are warm, set BASE high.
WARMUP_BASE = 3      # cold sends/day/box at warmup start (week 0)
WARMUP_STEP = 4      # +4/day/box each completed week since ramp_started_at
WARMUP_MAX = 25      # mature ceiling per box
# Cap per box PER RUN so the daily volume spreads across the day's hourly ticks instead of
# bursting at the first run (better deliverability). 30 boxes x 2/run x ~24 runs comfortably
# covers the per-box daily caps; the per-box DAILY cap is what ultimately bounds volume.
EMAIL_PER_BOX_PER_RUN = 2
# Threaded follow-up cadence (days). FU1 fires this long after the first touch; FU2 after FU1;
# FU3 after FU2. Each is a short bump on the SAME thread, from the SAME box, and stops the moment
# the lead replies or the address bounces.
FU1_DELAY_DAYS = 3
FU2_DELAY_DAYS = 4
FU3_DELAY_DAYS = 5
# Recency guard for the newest step: don't fire FU3 at leads whose FU2 went out longer ago than
# this. Keeps already-contacted-but-gone-cold leads from getting a jarring out-of-the-blue bump
# when we extend the sequence (they only get FU3 if they're still in the recent-outreach window).
FU3_MAX_AGE_DAYS = 30
_ACTIVE_SEND = ("queued", "sent", "delivered")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _jitter() -> None:
    """A short randomized pause between real sends so a run drips instead of machine-gunning —
    more human, gentler on the boxes. Deliberately small so a full run (per-box-per-run caps bound
    it to a few dozen sends) stays well inside the Modal function timeout."""
    time.sleep(random.uniform(1.5, 5.0))


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
    """Even rotation: fewest-used-this-run, then longest-idle, with capacity left and
    under the per-run cap (so volume spreads across the day, not one burst)."""
    avail = [
        b for b in boxes
        if b["remaining"] - used.get(b["id"], 0) > 0 and used.get(b["id"], 0) < EMAIL_PER_BOX_PER_RUN
    ]
    if not avail:
        return None
    avail.sort(key=lambda b: (used.get(b["id"], 0), b["last_send_at"] or _EPOCH))
    return avail[0]


def _split_subject(body: str) -> tuple[str | None, str]:
    """Email drafts embed the subject as a leading 'Subject: ...' line; split it out."""
    import re

    m = re.match(r"^\s*Subject:\s*(.+?)\r?\n\r?\n(.*)$", body or "", re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()[:200], m.group(2).strip()
    return None, (body or "").strip()


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
            # Mirror our outbound into the unified inbox so a thread shows both sides.
            try:
                cur.execute("select coalesce(edited_body, body), lead_id from drafts where id = %s", (draft_id,))
                row = cur.fetchone()
                if row and row[1] and message_id:
                    subject, text = _split_subject(row[0] or "")
                    cur.execute("select campaign_id from leads where id = %s", (row[1],))
                    camp = cur.fetchone()
                    cur.execute("select email from mailboxes where id = %s", (mailbox_id,))
                    mb = cur.fetchone()
                    cur.execute(
                        """
                        insert into inbox_messages
                            (mailbox_id, mailbox_email, from_name, subject, body, message_id,
                             lead_id, campaign_id, direction, is_auto, received_at)
                        values (%s,%s,'You',%s,%s,%s,%s,%s,'out',false, now())
                        on conflict (message_id) do nothing
                        """,
                        (mailbox_id, mb[0] if mb else None, subject, (text or "")[:8000],
                         message_id, row[1], camp[0] if camp else None),
                    )
            except Exception:  # noqa: BLE001 — inbox mirroring is best-effort
                pass


def send_email_first_touch(
    *, dry_run: bool = False, limit: int | None = None, time_budget_s: float | None = None,
) -> dict[str, Any]:
    """Send approved first-touch `email` drafts to verified-deliverable leads.

    `time_budget_s` bounds the run's wall clock: each send costs ~5-10s (SMTP round-trip +
    human jitter), and when the trailing-24h quota window rolls off overnight a single tick
    can otherwise try to drain 90+ sends in one go — blowing the dispatcher's per-job
    watchdog (the 2026-07-03/04 send_approved timeouts). Once the budget is spent the rest
    is DEFERRED to the next hourly tick, which also smooths bursts (better deliverability).
    """
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
                  and lower(split_part(l.email, '@', 2)) <> all(%s)
                  and (c.status is null or c.status = 'active')
                  and not exists (select 1 from sends s where s.draft_id = d.id)
                  and not exists (
                      select 1 from sends s2
                      join drafts d2 on d2.id = s2.draft_id
                      where d2.lead_id = d.lead_id and d2.channel = 'email'
                  )
                order by d.generated_at asc
                """,
                (list(FREE_EMAIL_DOMAINS),),
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
    deferred = 0
    deadline = (time.monotonic() + time_budget_s) if time_budget_s else None

    email_left = quota("email").allowed
    cam_window = campaign_daily_sent("email")
    cam_run: dict[str, int] = {}
    used: dict[str, int] = {}

    for i, (draft_id, lead_id, body, edited_body, email, name, company, campaign_id) in enumerate(rows):
        if deadline is not None and time.monotonic() > deadline:
            deferred = len(rows) - i
            break
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
            _jitter()  # human-like pause before the next send
        except Exception as e:  # noqa: BLE001
            failed.append({"lead_id": str(lead_id), "via": box["email"], "error": str(e)[:200]})

    return {
        "candidates": len(rows),
        "pushed": len(pushed),
        "blocked_quota": len(blocked_quota),
        "blocked_fairness": len(blocked_fairness),
        "blocked_no_box": len(blocked_no_box),
        "failed": len(failed),
        "deferred": deferred,
        "boxes_available": len(boxes),
        "details": {"pushed": pushed, "failed": failed},
        "dry_run": dry_run,
    }


def _due_followups(cur) -> list[dict[str, Any]]:
    """Leads with an email follow-up step due. Stops automatically on reply or bounce.

    Each row carries the SAME box that sent the opener, the thread's message-id to reply on,
    and the opener's draft body (for the original subject).
    """
    active = list(_ACTIVE_SEND)
    out: list[dict[str, Any]] = []

    def _rows(channel: str, items: list) -> None:
        for lid, email, name, company, role, cid, msgid, box, body in items:
            out.append({
                "lead_id": str(lid), "email": email, "name": name, "company": company,
                "role": role, "campaign_id": str(cid) if cid else None,
                "thread_msgid": msgid, "box_id": str(box) if box else None,
                "ft_body": body, "channel": channel,
            })

    # FU1 — opener sent >= FU1_DELAY days ago, no reply, not bounced, no FU1 yet.
    cur.execute(
        """
        select l.id, l.email, l.name, l.company, l.role, l.campaign_id,
               s.external_id, s.mailbox_id, d.body
        from leads l
        join drafts d on d.lead_id = l.id and d.channel = 'email'
        join sends s on s.draft_id = d.id and s.status = any(%s)
        left join campaigns c on c.id = l.campaign_id
        where (c.status is null or c.status = 'active')
          and l.email is not null
          and coalesce(l.email_status, '') <> 'bounced'
          and s.sent_at <= now() - make_interval(days => %s)
          and not exists (select 1 from replies r where r.lead_id = l.id)
          and not exists (
              select 1 from drafts d2 join sends s2 on s2.draft_id = d2.id
              where d2.lead_id = l.id and d2.channel = 'email_followup_1'
          )
        """,
        (active, FU1_DELAY_DAYS),
    )
    _rows("email_followup_1", cur.fetchall())

    # FU2 — FU1 sent >= FU2_DELAY days ago, no reply, not bounced, no FU2 yet. Threads on FU1,
    # sends from the opener's box, keeps the opener's subject.
    cur.execute(
        """
        select l.id, l.email, l.name, l.company, l.role, l.campaign_id,
               s1.external_id, s0.mailbox_id, d0.body
        from leads l
        join drafts d0 on d0.lead_id = l.id and d0.channel = 'email'
        join sends s0 on s0.draft_id = d0.id and s0.status = any(%s)
        join drafts d1 on d1.lead_id = l.id and d1.channel = 'email_followup_1'
        join sends s1 on s1.draft_id = d1.id and s1.status = any(%s)
        left join campaigns c on c.id = l.campaign_id
        where (c.status is null or c.status = 'active')
          and l.email is not null
          and coalesce(l.email_status, '') <> 'bounced'
          and s1.sent_at <= now() - make_interval(days => %s)
          and not exists (select 1 from replies r where r.lead_id = l.id)
          and not exists (
              select 1 from drafts d2 join sends s2 on s2.draft_id = d2.id
              where d2.lead_id = l.id and d2.channel = 'email_followup_2'
          )
        """,
        (active, active, FU2_DELAY_DAYS),
    )
    _rows("email_followup_2", cur.fetchall())

    # FU3 — FU2 sent between FU3_DELAY and FU3_MAX_AGE days ago (recency-guarded), no reply, not
    # bounced, no FU3 yet. Threads on FU2, sends from the opener's box, keeps the opener's subject.
    # Only recently-contacted leads reach this newest step (cold-for-a-month leads are skipped).
    cur.execute(
        """
        select l.id, l.email, l.name, l.company, l.role, l.campaign_id,
               s2.external_id, s0.mailbox_id, d0.body
        from leads l
        join drafts d0 on d0.lead_id = l.id and d0.channel = 'email'
        join sends s0 on s0.draft_id = d0.id and s0.status = any(%s)
        join drafts d2 on d2.lead_id = l.id and d2.channel = 'email_followup_2'
        join sends s2 on s2.draft_id = d2.id and s2.status = any(%s)
        left join campaigns c on c.id = l.campaign_id
        where (c.status is null or c.status = 'active')
          and l.email is not null
          and coalesce(l.email_status, '') <> 'bounced'
          and s2.sent_at <= now() - make_interval(days => %s)
          and s2.sent_at >= now() - make_interval(days => %s)
          and not exists (select 1 from replies r where r.lead_id = l.id)
          and not exists (
              select 1 from drafts d3 join sends s3 on s3.draft_id = d3.id
              where d3.lead_id = l.id and d3.channel = 'email_followup_3'
          )
        """,
        (active, active, FU3_DELAY_DAYS, FU3_MAX_AGE_DAYS),
    )
    _rows("email_followup_3", cur.fetchall())
    # Corporate mailboxes only — never follow up to a personal inbox (Maildoso policy). Catches
    # any leads that got a personal-email opener before the corporate-only gate went in.
    out = [r for r in out if is_corporate_email(r.get("email"))]
    return out


def _ensure_followup_draft(
    lead_id: str, channel: str, name: str | None, company: str | None,
    role: str | None, campaign_id: str | None,
) -> tuple[str, str]:
    """Find or generate the follow-up draft (body only). Returns (draft_id, body)."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, body, edited_body from drafts where lead_id = %s and channel = %s "
                "order by step_index limit 1",
                (lead_id, channel),
            )
            row = cur.fetchone()
    if row:
        return str(row[0]), (row[2] or row[1])

    from campaigns_loader import load_campaign
    from workers.draft import draft_for_channel

    campaign = load_campaign(campaign_id) if campaign_id else None
    first = (name or "").split(" ")[0] if name else None
    enrichment = {
        "profile": {"first_name": first, "full_name": name, "headline": role},
        "company": company, "recent_posts": [], "company_signals": {},
    }
    raw = draft_for_channel(channel, enrichment, None, campaign=campaign)
    _, fu_body = _split_subject(raw)  # strip any stray Subject: line — follow-ups are body-only
    step = int(channel.rsplit("_", 1)[-1]) if channel[-1:].isdigit() else 1  # _1/_2/_3 -> 1/2/3
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into drafts (lead_id, channel, step_index, body, status, generated_at)
                values (%s, %s, %s, %s, 'approved', now())
                on conflict (lead_id, channel, step_index, variant) do update
                  set body = excluded.body, generated_at = now()
                returning id
                """,
                (lead_id, channel, step, fu_body),
            )
            draft_id = str(cur.fetchone()[0])
    return draft_id, fu_body


def send_email_followups(
    *, dry_run: bool = False, limit: int | None = None, time_budget_s: float | None = None,
) -> dict[str, Any]:
    """Send threaded email follow-ups (FU1/FU2) due for leads who haven't replied.

    Each follow-up goes out on the original thread (In-Reply-To + 'Re:' subject), from the
    SAME box that sent the opener, under the same per-box warmup cap, global cap and
    per-campaign fair share as first touch. Auto-stops on reply (no replies row) or bounce
    (email_status='bounced'); a paused/at-cap box simply defers to a later tick.

    `time_budget_s`: same watchdog-safety bound as first touch — and heavier per send here,
    because each follow-up also drafts its body via Claude (~3-8s) before the SMTP call.
    Remaining due items simply stay due and go out next tick.
    """
    with _connect() as conn:
        with conn.cursor() as cur:
            due = _due_followups(cur)
            cur.execute("select count(*) from campaigns where status = 'active'")
            n_campaigns = int((cur.fetchone() or [1])[0] or 1)
            boxes = _load_boxes(cur, _today())
    box_by_id = {b["id"]: b for b in boxes}

    if limit is not None:
        due = due[:limit]

    pushed: list[dict] = []
    blocked_no_box: list[str] = []
    blocked_quota: list[str] = []
    blocked_fairness: list[str] = []
    failed: list[dict] = []
    deferred = 0
    deadline = (time.monotonic() + time_budget_s) if time_budget_s else None

    email_left = quota("email").allowed
    cam_window = campaign_daily_sent("email")
    cam_run: dict[str, int] = {}
    used: dict[str, int] = {}

    for i, item in enumerate(due):
        if deadline is not None and time.monotonic() > deadline:
            deferred = len(due) - i
            break
        cid = item["campaign_id"]
        box = box_by_id.get(item["box_id"] or "")
        # Threading + domain consistency require the box that sent the opener. If it's paused
        # (bounces) or out of capacity this run, defer to a later tick.
        if (
            box is None
            or (box["remaining"] - used.get(box["id"], 0)) <= 0
            or used.get(box["id"], 0) >= EMAIL_PER_BOX_PER_RUN
        ):
            blocked_no_box.append(item["lead_id"])
            continue

        orig_subject, _ = _split_subject(item["ft_body"])
        subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

        if dry_run:
            pushed.append({"lead_id": item["lead_id"], "channel": item["channel"], "via": box["email"]})
            used[box["id"]] = used.get(box["id"], 0) + 1
            continue

        if email_left <= 0:
            blocked_quota.append(item["lead_id"])
            continue
        if cid and n_campaigns > 1:
            if cam_window.get(cid, 0) + cam_run.get(cid, 0) >= campaign_share("email", n_campaigns):
                blocked_fairness.append(item["lead_id"])
                continue

        try:
            draft_id, fu_body = _ensure_followup_draft(
                item["lead_id"], item["channel"], item["name"], item["company"],
                item["role"], item["campaign_id"],
            )
        except Exception as e:  # noqa: BLE001
            failed.append({"lead_id": item["lead_id"], "error": f"draft: {str(e)[:160]}"})
            continue

        try:
            resp = smtp_email.send(
                smtp_host=box["smtp_host"], smtp_port=box["smtp_port"],
                username=box["username"], password=box["app_password"],
                from_email=box["email"], from_name=box["from_name"],
                to_email=item["email"], subject=subject, body=fu_body,
                in_reply_to=item["thread_msgid"] or None,
                references=item["thread_msgid"] or None,
            )
            _record_send(draft_id, resp.get("message_id", ""), box["id"])
            used[box["id"]] = used.get(box["id"], 0) + 1
            email_left -= 1
            if cid:
                cam_run[cid] = cam_run.get(cid, 0) + 1
            pushed.append({"lead_id": item["lead_id"], "channel": item["channel"], "via": box["email"]})
            _jitter()  # human-like pause before the next send
        except Exception as e:  # noqa: BLE001
            failed.append({"lead_id": item["lead_id"], "via": box["email"], "error": str(e)[:200]})

    return {
        "due": len(due),
        "pushed": len(pushed),
        "blocked_no_box": len(blocked_no_box),
        "blocked_quota": len(blocked_quota),
        "blocked_fairness": len(blocked_fairness),
        "failed": len(failed),
        "deferred": deferred,
        "details": {"pushed": pushed, "failed": failed},
        "dry_run": dry_run,
    }


def _pick_one_box() -> dict | None:
    with _connect() as conn:
        with conn.cursor() as cur:
            boxes = _load_boxes(cur, _today())
    return _next_box(boxes, {}) if boxes else None


def _notify_box() -> dict | None:
    """A STABLE box for internal alerts — always the same sender so you can whitelist it
    once in Gmail (rotating senders look spammy + can't be whitelisted). Notifications
    don't record sends, so this doesn't touch warmup-cap accounting."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select email, from_name, smtp_host, smtp_port, username, app_password
                from mailboxes where status in ('active', 'warming')
                order by email limit 1
                """
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "email": row[0], "from_name": row[1], "smtp_host": row[2],
        "smtp_port": row[3], "username": row[4], "app_password": row[5],
    }


def notify(subject: str, body: str, *, to_email: str | None = None) -> dict[str, Any]:
    """Send an internal notification (e.g. 'new reply') to the operator.

    Prefers **Resend** (transactional — lands in the inbox) over a Maildoso box (cold domain →
    Gmail spam). from = a verified NEWSLETTER_FROM if set, else Resend's shared onboarding@resend.dev,
    which delivers to the Resend account owner's OWN inbox with no domain verification — exactly the
    self-notification case. Falls back to SMTP if Resend isn't configured or errors.
    """
    import os

    dest = to_email or Config.notify_email
    if not dest:
        return {"sent": False, "reason": "NOTIFY_EMAIL not set"}

    resend_err: str | None = None
    if os.environ.get("RESEND_API_KEY"):
        try:
            from clients import resend

            from_addr = os.environ.get("NEWSLETTER_FROM") or "Agentry <onboarding@resend.dev>"
            resp = resend.send(to_email=dest, subject=subject, text=body, from_addr=from_addr)
            return {"sent": True, "via": "resend", "to": dest, "message_id": resp.get("id")}
        except Exception as e:  # noqa: BLE001 — fall through to SMTP
            resend_err = str(e)[:160]

    box = _notify_box()
    if not box:
        return {"sent": False, "reason": f"resend failed ({resend_err}); no mailbox" if resend_err else "no available mailbox"}
    resp = smtp_email.send(
        smtp_host=box["smtp_host"], smtp_port=box["smtp_port"],
        username=box["username"], password=box["app_password"],
        # Use the box's real From name (not "Outreach Bot") — a botty display name on a
        # cold domain gets filtered hard; mirror the email that actually delivered.
        from_email=box["email"], from_name=box.get("from_name") or "Chance Beyer",
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
