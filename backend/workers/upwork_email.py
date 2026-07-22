"""Pull Upwork job-alert emails from the connected mailbox and run them through the bid
pipeline (score → draft → ingest), same as any other opportunity source.

Reuses opportunity_sourcing's scoring/drafting/ingest so an email-sourced Upwork job is
treated identically to an API-sourced one — it lands in /bids, fit-scored, with a drafted
proposal when it's a strong-fit software job.
"""
from __future__ import annotations

from typing import Any

from campaigns_loader import load_campaign
from clients import unipile, upwork_email
from config import Config
from prompts_loader import system_prefix
from workers.opportunity_sourcing import (
    BIDS_CAMPAIGN,
    MIN_FIT_TO_DRAFT,
    SCORE_LIMIT,
    _admin_user_id,
    _connect,
    _draft,
    _ingest,
    _score,
)


def ingest_upwork_emails(*, account_id: str | None = None, dry_run: bool = False, limit_emails: int = 40) -> dict[str, Any]:
    """Scan the connected inbox for Upwork job alerts, extract postings, and pipe them into
    the bid queue. `account_id` selects which connected mailbox receives the alerts (defaults
    to UPWORK_ALERT_EMAIL_ACCOUNT_ID, else the main email account)."""
    if not Config.unipile_api_key:
        return {"skipped": "no unipile"}
    acct = account_id or Config.upwork_alert_email_account_id or None
    try:
        emails = unipile.list_emails(role="inbox", limit=limit_emails, account_id=acct)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}

    alerts = [
        e for e in emails
        if isinstance(e, dict)
        and upwork_email.is_upwork_alert((e.get("from_attendee") or {}).get("identifier"), e.get("subject"))
    ]
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
    for opp in fresh[:SCORE_LIMIT]:
        fit = _score(opp, prefix)
        scored += 1
        bid = None
        if int(fit.get("fit_score") or 0) >= MIN_FIT_TO_DRAFT and bool(fit.get("is_software")):
            bid = _draft(opp, fit, prefix, owner_id)
            if bid:
                drafted += 1
        if not dry_run and Config.database_url and _ingest(opp, fit, bid, owner_id):
            ingested += 1

    return {
        "emails_scanned": len(emails),
        "alerts": len(alerts),
        "jobs_found": len(jobs),
        "new": len(fresh),
        "scored": scored,
        "drafted": drafted,
        "ingested": ingested,
    }
