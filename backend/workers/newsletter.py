"""The Agent Brief — an agent-curated weekly newsletter.

generate_issue() pulls the week's high-signal AI items, has Claude curate the few that matter
and write a sharp, no-hype issue in the Agentry voice, and stores it as a draft for review.
send_issue() emails the approved issue to opted-in subscribers via Resend (NOT the cold-email
boxes). Human-in-the-loop: nothing sends until the operator approves.
"""
from __future__ import annotations

import json
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import claude, news
from config import Config, require
from prompts_loader import load_prompt
from workers.content import _sanitize


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def generate_issue(*, dry_run: bool = False) -> dict[str, Any]:
    """Draft this week's issue from recent high-signal AI items."""
    try:
        stories = news.fetch_all_sources()
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": f"news fetch failed: {e}"}
    if not stories:
        return {"generated": False, "reason": "no AI stories in window"}

    candidates = [
        {k: s.get(k) for k in ("title", "url", "summary", "source_kind", "points", "num_comments")}
        for s in stories[:14]
    ]
    try:
        result = claude.call_json(
            instruction=load_prompt("draft_newsletter"),
            user_payload=json.dumps(
                {"candidates": candidates, "audit_url": "https://agentry.contentdrip.ai/audit"},
                indent=2,
            ),
            model=Config.claude_model_draft,
            max_tokens=1600,
        )
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": f"generation failed: {e}"}

    subject = _sanitize((result or {}).get("subject") or "")[:140]
    body = _sanitize((result or {}).get("body") or "")
    if not subject or not body:
        return {"generated": False, "reason": "model returned an empty issue"}

    if dry_run:
        return {"generated": True, "dry_run": True, "subject": subject, "body": body}

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into newsletter_issues (subject, body, status) values (%s,%s,'draft') returning id",
            (subject, body),
        )
        issue_id = str(cur.fetchone()[0])
    _notify(subject)
    return {"generated": True, "id": issue_id, "subject": subject}


def add_subscriber(email: str, *, name: str | None = None, source: str = "site") -> dict[str, Any]:
    """Opt someone into the newsletter (idempotent; re-subscribes if previously unsubscribed)."""
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email:
        return {"ok": False, "error": "invalid email"}
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into subscribers (email, name, source) values (%s,%s,%s) "
                "on conflict (email) do update set unsubscribed_at = null, "
                "name = coalesce(excluded.name, subscribers.name) returning id",
                (email, name or None, source),
            )
            return {"ok": True, "id": str(cur.fetchone()[0])}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:150]}


def send_issue(issue_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Send an approved issue to all active subscribers via Resend, then mark it sent."""
    if not issue_id:
        return {"ok": False, "error": "missing issue id"}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select subject, body, status from newsletter_issues where id=%s", (issue_id,))
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "issue not found"}
        subject, body, status = row
        if status == "sent":
            return {"ok": False, "error": "already sent"}
        cur.execute("select email from subscribers where unsubscribed_at is null order by created_at")
        subs = [r[0] for r in cur.fetchall()]
    if not subs:
        return {"ok": False, "error": "no active subscribers yet"}

    if dry_run:
        return {"ok": True, "dry_run": True, "would_send": len(subs)}

    from clients import resend

    unsub = f"mailto:{Config.notify_email or 'hello@contentdrip.ai'}?subject=unsubscribe"
    footer = (
        "\n\n---\nYou are receiving this because you subscribed to The Agent Brief.\n"
        "To unsubscribe, reply with the word unsubscribe."
    )
    sent, failed = 0, 0
    for email in subs:
        try:
            resend.send(
                to_email=email, subject=subject, text=body + footer,
                from_addr=Config.newsletter_from, headers={"List-Unsubscribe": f"<{unsub}>"},
            )
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1

    if sent == 0:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update newsletter_issues set error=%s where id=%s",
                ("All sends failed. Verify your Resend sending domain (NEWSLETTER_FROM).", issue_id),
            )
        return {"ok": False, "error": "All sends failed. Verify your Resend sending domain.", "failed": failed}

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "update newsletter_issues set status='sent', sent_at=now(), recipients=%s, error=null where id=%s",
            (sent, issue_id),
        )
    return {"ok": True, "sent": sent, "failed": failed, "subscribers": len(subs)}


def _notify(subject: str) -> None:
    try:
        from workers.email_sender import notify

        notify(
            subject="New Agent Brief draft ready",
            body=(
                f"This week's newsletter draft is ready to review and send.\n\n"
                f"Subject: {subject}\n\nReview, edit, and send it in the dashboard (Newsletter tab)."
            ),
        )
    except Exception:  # noqa: BLE001
        pass
