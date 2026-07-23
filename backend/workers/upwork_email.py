"""Pull Upwork job-alert emails from the connected mailbox and run them through the bid
pipeline (score → draft → ingest), same as any other opportunity source.

Reuses opportunity_sourcing's scoring/drafting/ingest so an email-sourced Upwork job is
treated identically to an API-sourced one — it lands in /bids, fit-scored, with a drafted
proposal when it's a strong-fit software job.
"""
from __future__ import annotations

import json
from typing import Any

from campaigns_loader import load_campaign
from clients import unipile, upwork_email
from config import Config
from prompts_loader import system_prefix
from workers.opportunity_sourcing import (
    BIDS_CAMPAIGN,
    DRAFT_LIMIT,
    MIN_FIT_TO_DRAFT,
    SCORE_LIMIT,
    _admin_user_id,
    _connect,
    _draft,
    _ingest,
    _score,
)


def ingest_upwork_emails(
    *,
    account_id: str | None = None,
    dry_run: bool = False,
    limit_emails: int = 40,
    score_cap: int | None = None,
    draft_cap: int | None = None,
    skip_seen: bool = False,
) -> dict[str, Any]:
    """Scan the connected inbox for Upwork job alerts, extract postings, and pipe them into
    the bid queue. `account_id` selects which connected mailbox receives the alerts (defaults
    to UPWORK_ALERT_EMAIL_ACCOUNT_ID, else the main email account). `limit_emails` is how many
    inbox emails to scan (raise it to backfill history); `score_cap`/`draft_cap` bound LLM cost
    per run. `skip_seen=True` (the hourly cron) only LLM-extracts alert emails not seen in a
    prior run — so re-checking the inbox every hour costs nothing when there's nothing new."""
    score_cap = score_cap or SCORE_LIMIT
    draft_cap = draft_cap or DRAFT_LIMIT
    if not Config.unipile_api_key:
        return {"skipped": "no unipile"}
    acct = account_id or Config.upwork_alert_email_account_id or None
    # Unipile's /emails endpoint rejects large limits (limit=300 → 400). 200 is the tested ceiling.
    limit_emails = min(max(1, limit_emails), 200)
    try:
        emails = unipile.list_emails(role="inbox", limit=limit_emails, account_id=acct)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}

    alerts = [
        e for e in emails
        if isinstance(e, dict)
        and upwork_email.is_upwork_alert((e.get("from_attendee") or {}).get("identifier"), e.get("subject"))
    ]

    # Cost guard for the hourly cron: only extract alert emails we haven't processed before
    # (tracked by email id in app_settings). Manual/backfill runs pass skip_seen=False.
    seen_ids: list[str] = []
    if skip_seen and Config.database_url:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select value from app_settings where key = 'upwork_email_seen_ids'")
            row = cur.fetchone()
        seen_ids = list(row[0]) if row and isinstance(row[0], list) else []
        seen_set = set(seen_ids)
        alerts = [e for e in alerts if str(e.get("id")) not in seen_set]

    if not alerts:
        return {"emails_scanned": len(emails), "alerts": 0}

    # Dedup ledger (Upwork rows only) + owner, one query.
    existing: set[tuple[str, str]] = set()
    owner_id: str | None = None
    if Config.database_url:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select source, external_id from opportunities where source = 'upwork'")
            existing = {(s, e) for s, e in cur.fetchall()}
            owner_id = _admin_user_id(cur)

    prefix = system_prefix(load_campaign(BIDS_CAMPAIGN))

    jobs: list[dict[str, Any]] = []
    for em in alerts:
        body = em.get("body_plain") or em.get("body") or ""
        jobs.extend(upwork_email.extract_jobs(em.get("subject") or "", body))

    fresh: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for j in jobs:
        key = (j["source"], str(j["external_id"]))
        if key in existing or key in seen:
            continue
        seen.add(key)
        fresh.append(j)

    scored = drafted = ingested = 0
    for opp in fresh[:score_cap]:
        fit = _score(opp, prefix)
        scored += 1
        bid = None
        if (
            int(fit.get("fit_score") or 0) >= MIN_FIT_TO_DRAFT
            and bool(fit.get("is_software"))
            and drafted < draft_cap
        ):
            bid = _draft(opp, fit, prefix, owner_id)
            if bid:
                drafted += 1
        if not dry_run and Config.database_url and _ingest(opp, fit, bid, owner_id):
            ingested += 1
        # In a dry run, show what was found + how it scored so we can eyeball the real format.
        if dry_run:
            print(f"  [upwork-email] fit={fit.get('fit_score')} sw={fit.get('is_software')} "
                  f"{'DRAFT' if bid else '    '}  {(opp.get('title') or '')[:60]}")

    # Remember which alert emails we processed so the hourly cron skips them next time (bound
    # to the last 300 ids). Only when actually persisting (not dry_run) and tracking is on.
    if skip_seen and not dry_run and Config.database_url:
        new_ids = [str(e.get("id")) for e in alerts if e.get("id")]
        merged = (new_ids + seen_ids)[:300]
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into app_settings (key, value) values ('upwork_email_seen_ids', %s) "
                "on conflict (key) do update set value = excluded.value",
                (json.dumps(merged),),
            )
            conn.commit()

    return {
        "emails_scanned": len(emails),
        "alerts": len(alerts),
        "jobs_found": len(jobs),
        "new": len(fresh),
        "scored": scored,
        "drafted": drafted,
        "ingested": ingested,
        "deferred": max(0, len(fresh) - score_cap),
    }
