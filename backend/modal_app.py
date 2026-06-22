"""Modal entrypoint — scheduled workers that keep the pipeline running
without operator intervention.

Functions
---------
- `unipile_webhook`             on event       primary reply path — Unipile POSTs
                                               new messages/emails; we classify +
                                               persist within seconds.
- `pull_replies_cron`           hourly         fallback poll of Unipile (LinkedIn
                                               chats + email) in case a webhook is
                                               missed; classify, persist to Postgres.
- `progress_sequences_cron`     hourly         advance any lead whose next step is due.
- `pull_replies_now`            on-demand      same poll logic, one-shot.
- `health`                      on-demand      env + deps + DB + Unipile ping.

Deploy
------
    cd backend
    uv sync --extra worker
    modal token new                      # one-time auth
    modal deploy modal_app.py            # ships the cron(s) to production
    modal logs consultancy-outreach      # tail

Local dev
---------
    modal run modal_app.py::pull_replies_now           # one-shot
    modal run modal_app.py::health                     # smoke test

Secrets
-------
This app reads env vars via `modal.Secret.from_name("outreach")`. Create it
once with all the keys from .env:

    modal secret create outreach \\
        --from-dotenv .env

Reads:
  ANTHROPIC_API_KEY, UNIPILE_API_KEY, UNIPILE_DSN, UNIPILE_LINKEDIN_ACCOUNT_ID,
  UNIPILE_EMAIL_ACCOUNT_ID, DATABASE_URL, plus the optional CLAUDE_MODEL_* and
  LANDING_URL/CALCOM_URL strings used by the prompts. Set UNIPILE_WEBHOOK_SECRET
  to enable webhook auth (sent back as a custom header you configure in Unipile).
"""

from __future__ import annotations

import modal

# ---------------------------------------------------------------------------
# Image: install deps from pyproject.toml, ship the backend/ source tree.
# ---------------------------------------------------------------------------

PYPROJECT = "pyproject.toml"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "anthropic>=0.40.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.1",
        "pydantic>=2.9.0",
        "tenacity>=9.0.0",
        "rich>=13.9.0",
        "typer>=0.13.0",
        # worker extras
        "psycopg[binary]>=3.2.0",
        # fastapi endpoints
        "fastapi[standard]>=0.115.0",
    )
    # Drop the backend/ tree into /root/backend so imports work the same as
    # local: `from workers.replies import ...`. The local source path is the
    # parent dir of this file (modal_app.py is at backend/modal_app.py).
    # `campaigns_loader` is needed because the reply-classify path resolves the
    # active campaign's system prefix.
    .add_local_python_source(
        "clients",
        "workers",
        "config",
        "prompts_loader",
        "campaigns_loader",
    )
    # Prompts are referenced from prompts_loader → backend/prompts/*.md.
    # Campaign persona files back the file-seed fallback in campaigns_loader when
    # a campaign row is missing from the DB. add_local_dir mirrors them at runtime.
    .add_local_dir("prompts", remote_path="/root/prompts")
    .add_local_dir("campaigns", remote_path="/root/campaigns")
)

app = modal.App("consultancy-outreach", image=image)

# All scheduled functions share one secret bundle.
secrets = [modal.Secret.from_name("outreach")]


# ---------------------------------------------------------------------------
# Scheduled work
# ---------------------------------------------------------------------------


@app.function(
    schedule=modal.Cron("0 * * * *"),  # hourly — fallback; webhooks are primary
    secrets=secrets,
    timeout=600,
    retries=2,
)
def pull_replies_cron() -> dict:
    """Fallback poll of Unipile for inbound replies the webhook may have missed.

    Unipile's `unipile_webhook` is the primary, near-real-time path; this hourly
    sweep is a safety net. Conservatively scoped per run (limit=100) so a single
    tick finishes well inside the timeout even with classifier latency.
    """
    return _pull_replies_impl(limit=100, only_with_unread=True)


@app.function(
    schedule=modal.Cron("17 * * * *"),  # every hour at :17 (offset from replies cron)
    secrets=secrets,
    timeout=900,
    retries=1,
)
def progress_sequences_cron() -> dict:
    """Advance every lead whose next sequence step is due.

    Reads sends + replies + drafts from Postgres, finds leads with an
    approved-but-unsent next-step draft past its wait window, sends via
    Unipile. Idempotent — re-running is safe.
    """
    from workers.sequence_send import progress_sequences

    return progress_sequences(limit=50)


@app.function(
    schedule=modal.Cron("33 * * * *"),  # every hour at :33 (offset from others)
    secrets=secrets,
    timeout=1200,
    retries=1,
)
def replenish_queue_cron() -> dict:
    """Smart sourcing: auto-pull fresh leads when a campaign queue runs low.

    For each active campaign with a search_url configured:
    1. Count messageable leads (drafted but not sent/rejected) in the last 7 days
    2. If count < threshold (20), pull fresh leads from search_url
    3. Enrich + score + draft them
    4. Ingest directly to Postgres

    Deduplication via runs/sourced-<campaign_slug>.jsonl ledger prevents re-messaging.
    """
    from workers.replenish import replenish_all_campaigns

    return replenish_all_campaigns(dry_run=False)


@app.function(secrets=secrets, timeout=600)
def progress_sequences_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand sequence advance. `modal run modal_app.py::progress_sequences_now --dry-run`."""
    from workers.sequence_send import progress_sequences

    return progress_sequences(dry_run=dry_run, limit=limit)


@app.function(
    schedule=modal.Cron("47 * * * *"),  # every hour at :47 (offset from the others)
    secrets=secrets,
    timeout=900,
    retries=1,
)
def send_approved_cron() -> dict:
    """Send first-touch drafts the operator approved in the dashboard.

    Dashboard approve → drafts.status='approved' in Postgres → this cron sends the
    cold opener (linkedin_connect / email) via Unipile, respecting the rolling-window
    cap. The DB-driven counterpart to scripts/send_approvals.py, so first contact runs
    on Modal without the operator's machine. Follow-ups stay with progress_sequences.
    """
    from workers.sequence_send import send_approved_first_touch

    return send_approved_first_touch(limit=20)


@app.function(secrets=secrets, timeout=600)
def send_approved_now(dry_run: bool = False, limit: int | None = None) -> dict:
    """On-demand first-touch send. `modal run modal_app.py::send_approved_now --dry-run`."""
    from workers.sequence_send import send_approved_first_touch

    return send_approved_first_touch(dry_run=dry_run, limit=limit)


@app.function(secrets=secrets, timeout=600)
def pull_replies_now(limit: int = 100, include_read: bool = False) -> dict:
    """On-demand trigger of the same logic — for ad-hoc runs from CLI.

    Usage:
        modal run modal_app.py::pull_replies_now
        modal run modal_app.py::pull_replies_now --limit 50 --include-read
    """
    return _pull_replies_impl(limit=limit, only_with_unread=not include_read)


def _pull_replies_impl(*, limit: int, only_with_unread: bool) -> dict:
    """Shared body — runs inside the Modal container, so backend/* is on path."""
    from workers.replies import fetch_and_classify_new_replies
    from workers.replies_db import existing_external_ids, insert_replies

    seen = existing_external_ids(limit=5000)
    new_records = fetch_and_classify_new_replies(
        seen_message_ids=seen,
        limit=limit,
        only_with_unread=only_with_unread,
    )
    if not new_records:
        return {"new_records": 0, "inserted": 0}

    counts = insert_replies(new_records)
    return {"new_records": len(new_records), **counts}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.function(secrets=secrets, timeout=60)
def health() -> dict:
    """Verify env, deps, DB connectivity, and Unipile reachability."""
    import os

    from config import Config

    checks = {
        "anthropic_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "unipile_api_key": bool(Config.unipile_api_key),
        "unipile_dsn": bool(Config.unipile_dsn),
        "unipile_linkedin_account_id": bool(Config.unipile_linkedin_account_id),
        "unipile_email_account_id": bool(Config.unipile_email_account_id),
        "database_url": bool(Config.database_url),
        "claude_model_draft": Config.claude_model_draft,
    }

    # Unipile ping — lists connected accounts.
    if Config.unipile_api_key and Config.unipile_dsn:
        try:
            from clients import unipile

            accounts = unipile.health()
            items = accounts.get("items", accounts) if isinstance(accounts, dict) else accounts
            checks["unipile_accounts"] = len(items) if isinstance(items, list) else None
        except Exception as e:  # noqa: BLE001
            checks["unipile_error"] = str(e)

    # Quick DB ping
    if Config.database_url:
        try:
            import psycopg

            with psycopg.connect(Config.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("select count(*) from replies")
                    checks["replies_count"] = cur.fetchone()[0]
        except Exception as e:  # noqa: BLE001
            checks["db_error"] = str(e)

    return checks


# ---------------------------------------------------------------------------
# Webhook receiver — near-real-time reply latency (replaces the hourly poll)
# ---------------------------------------------------------------------------
#
# Configure Unipile (Webhooks in the dashboard, or POST /webhooks) to send
# `message_received` (messaging) and `mail_received` (email) events to the URL
# printed by `modal deploy`:
#   https://<workspace>--consultancy-outreach-unipile-webhook.modal.run
#
# Auth: Unipile lets you attach custom headers to a webhook. Set a shared secret
# as a header (e.g. X-Unipile-Secret) and put the same value in
# UNIPILE_WEBHOOK_SECRET; the receiver rejects mismatches. If the secret is
# unset, the check is skipped (rotate the URL on any leak).


@app.function(secrets=secrets, timeout=60)
@modal.fastapi_endpoint(method="POST")
def unipile_webhook(request_body: dict, x_unipile_secret: str | None = None) -> dict:
    """Receive Unipile inbound-message + inbound-email webhooks.

    Classifies the message and persists to Postgres. One endpoint handles both
    channels — we branch on the event type.

    Messaging payload (LinkedIn DM):
      { "event": "message_received", "account_id", "chat_id", "message_id",
        "message": "<text>", "sender": {"attendee_name": "...",
        "attendee_provider_id": "..."}, "timestamp": "..." }

    Email payload:
      { "event": "mail_received", "email_id" | "id",
        "from_attendee": {"identifier": "...", "display_name": "..."},
        "subject": "...", "body_plain" | "body": "...", "date": "..." }
    """
    import os

    from fastapi import HTTPException

    from workers.replies import classify_message
    from workers.replies_db import insert_replies

    secret = os.environ.get("UNIPILE_WEBHOOK_SECRET")
    if secret and x_unipile_secret != secret:
        raise HTTPException(status_code=401, detail="bad webhook secret")

    event = (request_body.get("event") or request_body.get("event_type") or "").lower()
    email_events = {"mail_received", "email_received", "mail.received", "email.received"}
    message_events = {"message_received", "message.received", "message"}

    if event in email_events:
        from_attendee = request_body.get("from_attendee") or {}
        body = request_body.get("body_plain") or request_body.get("body") or ""
        if not body:
            return {"ok": True, "skipped": "empty body"}
        record = classify_message(
            channel="email",
            external_id=str(
                request_body.get("email_id") or request_body.get("id") or ""
            ),
            text=body,
            lead_name=from_attendee.get("display_name"),
            received_at=request_body.get("date"),
        )
    elif event in message_events:
        text = request_body.get("message") or request_body.get("text") or ""
        if not text:
            return {"ok": True, "skipped": "empty body"}
        sender = request_body.get("sender") or {}
        record = classify_message(
            channel="linkedin_dm",
            external_id=str(
                request_body.get("message_id") or request_body.get("id") or ""
            ),
            text=text,
            lead_name=sender.get("attendee_name") or sender.get("name"),
            received_at=request_body.get("timestamp"),
        )
    else:
        return {"ok": True, "skipped": f"event={event}"}

    if record is None:
        raise HTTPException(status_code=500, detail="classifier failed")

    counts = insert_replies([record])
    return {"ok": True, "record_id": record["message_id"], **counts}
