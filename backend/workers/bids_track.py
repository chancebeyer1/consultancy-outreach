"""Bid response tracking — polls the source platforms for outcomes on submitted bids.

Freelancer.com only for now (its API exposes award status; we hold the id of every bid we
placed). Upwork needs proposal/offer scopes we haven't been granted; SAM.gov awards will be
watched via public award notices once federal submission is possible; HN/RemoteOK/LinkedIn
responses arrive by email and are marked won/lost by hand in /bids.

Runs on the hourly dispatcher: ZERO API calls when there are no outstanding submitted bids,
one bids-lookup call otherwise. Hourly matters because a Freelancer award must be ACCEPTED
within their acceptance window — so an award triggers an immediate email alert.
"""
from __future__ import annotations

from typing import Any

import psycopg

from clients import freelancer
from config import Config, require

# award_status → our opportunity status. Unknown/pending values leave the bid untouched.
_WON = frozenset({"awarded"})
_LOST = frozenset({"rejected", "revoked", "canceled"})


def _alert_award(title: str, url: str | None, amount: str | None) -> dict[str, Any]:
    """Immediate email on an award — accepting it is time-boxed on Freelancer's side."""
    from workers.email_sender import notify

    body = (
        f"Your Freelancer bid was AWARDED:\n\n  {title}\n"
        + (f"  bid: {amount}\n" if amount else "")
        + (f"  {url}\n" if url else "")
        + "\nGo accept the award on Freelancer — awards expire if not accepted promptly."
    )
    return notify("You WON a bid — accept it on Freelancer", body)


def poll_freelancer_bids() -> dict[str, Any]:
    """One tracking pass. Returns a summary dict for the activity log."""
    if not Config.freelancer_oauth_token:
        return {"skipped": "no freelancer token"}

    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select b.id, b.external_id, b.est_price, o.id, o.title, o.url
            from bids b join opportunities o on o.id = b.opportunity_id
            where o.source = 'freelancer' and b.status = 'submitted'
              and o.status = 'submitted' and b.external_id is not null
            """
        )
        outstanding = cur.fetchall()
    if not outstanding:
        return {"checked": 0}

    by_provider_id = {str(ext): (bid_id, opp_id, title, url, est)
                      for bid_id, ext, est, opp_id, title, url in outstanding}
    try:
        remote = freelancer.get_my_bids(bid_ids=[int(x) for x in by_provider_id])
    except Exception as e:  # noqa: BLE001 — transient API failure: retry next tick
        return {"checked": len(outstanding), "error": str(e)[:200]}

    won = lost = pending = 0
    alert_failed = 0
    for rb in remote:
        pid = str(rb.get("id"))
        if pid not in by_provider_id:
            continue
        bid_id, opp_id, title, url, est = by_provider_id[pid]
        status = str(rb.get("award_status") or "").lower()
        if status in _WON:
            new_status = "won"
            won += 1
        elif status in _LOST:
            new_status = "lost"
            lost += 1
        else:
            pending += 1
            continue
        with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
            cur.execute("update opportunities set status = %s where id = %s", (new_status, opp_id))
        print(f"  bid {pid} → {new_status}: {title[:60]}")
        if new_status == "won":
            try:
                res = _alert_award(title, url, est)
                if not res.get("sent"):
                    alert_failed += 1
            except Exception:  # noqa: BLE001
                alert_failed += 1

    out: dict[str, Any] = {"checked": len(outstanding), "won": won, "lost": lost, "pending": pending}
    if alert_failed:
        out["alert_email_failed"] = alert_failed  # alerts.scan_result pages on *_failed keys
    return out
