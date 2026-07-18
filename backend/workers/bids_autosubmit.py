"""Batch / auto submission of approved Freelancer bids.

Two callers, one engine:
  • MANUAL batch — the dashboard "Submit all ready" button submits every approved Freelancer
    bid the operator can see (they pulled the trigger).
  • AUTO — the daily job places approved Freelancer bids with NO click, gated hard by
    Config.freelancer_auto_submit (OFF by default) + a min-fit floor + a per-day cap, because
    unattended bidding burns Freelancer's bid quota and can flag a new account.

Freelancer ONLY — its API sanctions bid placement. Upwork proposals are never auto-submitted
(ToS = instant ban) and SAM has no submission API. Each placement runs the same guards as a
manual submit (workers/bids_submit.submit_freelancer_bid): reads the DB proposal, verifies
state, records the provider bid id.
"""
from __future__ import annotations

from typing import Any

import psycopg

from config import Config, require
from workers.bids_submit import submit_freelancer_bid

MANUAL_BATCH_CAP = 25  # sanity bound even on a human "submit all" click


def _submitted_today(cur) -> int:
    cur.execute(
        "select count(*) from bids where submitted_via = 'api' "
        "and submitted_at >= date_trunc('day', now())"
    )
    return int((cur.fetchone() or [0])[0] or 0)


def _ready_freelancer_bids(cur, *, min_fit: int | None) -> list[tuple[str, str, int]]:
    """(opportunity_id, title, fit) for approved, un-submitted Freelancer bids, best fit first."""
    cur.execute(
        """
        select o.id, o.title, coalesce(o.fit_score, 0)
        from opportunities o join bids b on b.opportunity_id = o.id
        where o.source = 'freelancer' and o.status = 'approved' and b.status = 'approved'
          and (%s is null or coalesce(o.fit_score, 0) >= %s)
        order by o.fit_score desc nulls last
        """,
        (min_fit, min_fit),
    )
    return [(str(r[0]), r[1], int(r[2])) for r in cur.fetchall()]


def _email_submitted(items: list[dict[str, Any]], *, auto: bool) -> None:
    if not items:
        return
    from workers.email_sender import notify

    how = "auto-submitted" if auto else "submitted"
    lines = [f"• {it['title'][:80]} — {it.get('amount')}" for it in items]
    body = (
        f"{len(items)} Freelancer bid{'s' if len(items) != 1 else ''} {how}:\n\n"
        + "\n".join(lines)
        + "\n\nOutcomes auto-track hourly; you'll be emailed on an award."
    )
    notify(f"{len(items)} Freelancer bid{'s' if len(items) != 1 else ''} {how}", body)


def submit_ready_freelancer(*, auto: bool) -> dict[str, Any]:
    """Submit approved Freelancer bids. `auto=True` applies the opt-in gate + min-fit + daily
    cap; `auto=False` (manual batch) submits everything approved, up to a sanity cap."""
    if not Config.freelancer_oauth_token:
        return {"skipped": "no freelancer token"}
    if auto and not Config.freelancer_auto_submit:
        return {"skipped": "FREELANCER_AUTO_SUBMIT off"}

    min_fit = Config.freelancer_auto_submit_min_fit if auto else None
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        ready = _ready_freelancer_bids(cur, min_fit=min_fit)
        if auto:
            remaining = max(0, Config.freelancer_auto_submit_daily_cap - _submitted_today(cur))
            ready = ready[:remaining]
        else:
            ready = ready[:MANUAL_BATCH_CAP]

    submitted: list[dict[str, Any]] = []
    errors: list[str] = []
    for opp_id, title, _fit in ready:
        try:
            res = submit_freelancer_bid(opp_id)  # est_price → amount inside; own transaction
            submitted.append({"title": title, "amount": res.get("amount")})
        except Exception as e:  # noqa: BLE001 — one bad bid must not stop the batch
            errors.append(f"{title[:50]}: {str(e)[:120]}")

    if submitted:
        try:
            _email_submitted(submitted, auto=auto)
        except Exception as e:  # noqa: BLE001
            errors.append(f"email: {e}")

    out: dict[str, Any] = {"auto": auto, "candidates": len(ready), "submitted": len(submitted)}
    if errors:
        out["errors"] = errors
        out["submit_failed"] = len(errors)  # alerts.scan_result pages on *_failed keys
    return out
