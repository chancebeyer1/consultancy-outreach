"""Bid submission — places an approved bid on the source platform via its official API.

Currently Freelancer.com only: their API sanctions programmatic bid placement (the official
SDK ships it). Upwork stays manual (ToS bans automated proposals — instant ban) and SAM.gov
has no submission API. Every call here is HUMAN-INITIATED (a dashboard Submit click or an
explicit CLI run) — the sweep never calls this. The proposal text is read from the DB
(edited_body wins), so what the operator last saved is exactly what gets submitted.
"""
from __future__ import annotations

import re
from typing import Any

import psycopg

from clients import freelancer
from config import Config, require

# Sources whose official API permits programmatic bid placement.
API_SUBMITTABLE = frozenset({"freelancer"})

_MONEY = re.compile(r"(\d[\d,]*(?:\.\d+)?)")


def _amount_from_est_price(est_price: str | None) -> float | None:
    """Best-effort: first money-looking number in the drafted estimate ('$1,500 USD (fixed)'
    → 1500.0). None if nothing parseable — the caller must then supply an explicit amount."""
    if not est_price:
        return None
    m = _MONEY.search(est_price)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
        return value if value > 0 else None
    except ValueError:
        return None


def submit_freelancer_bid(
    opportunity_id: str,
    *,
    amount: float | None = None,
    period_days: int = 7,
) -> dict[str, Any]:
    """Submit the (approved or draft) bid for one Freelancer opportunity. Returns a summary
    dict; raises with a clear message on any guard failure so the UI can show it."""
    if not Config.freelancer_oauth_token:
        raise RuntimeError("FREELANCER_OAUTH_TOKEN not configured")

    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select o.source, o.external_id, o.title, o.status,
                   b.id, b.status, coalesce(b.edited_body, b.body), b.est_price
            from opportunities o
            join bids b on b.opportunity_id = o.id
            where o.id = %s
            """,
            (opportunity_id,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("no bid found for this opportunity")
        source, project_ext_id, title, opp_status, bid_id, bid_status, body, est_price = row

        if source not in API_SUBMITTABLE:
            raise RuntimeError(f"source '{source}' does not allow API submission — submit by hand")
        if bid_status == "submitted":
            raise RuntimeError("this bid was already submitted")
        if bid_status == "rejected" or opp_status in ("passed", "submitted", "won", "lost"):
            raise RuntimeError(f"bid/opportunity not in a submittable state ({bid_status}/{opp_status})")
        if not body or not body.strip():
            raise RuntimeError("bid body is empty")

        final_amount = amount if amount and amount > 0 else _amount_from_est_price(est_price)
        if not final_amount:
            raise RuntimeError("no bid amount — pass one explicitly (est_price wasn't parseable)")

        result = freelancer.place_bid(
            project_id=int(project_ext_id),
            amount=final_amount,
            period_days=period_days,
            description=body.strip(),
        )
        provider_bid_id = str(result.get("id"))

        cur.execute(
            """
            update bids set status='submitted', submitted_at=now(), decided_at=coalesce(decided_at, now()),
                            external_id=%s, submitted_via='api'
            where id=%s
            """,
            (provider_bid_id, bid_id),
        )
        cur.execute("update opportunities set status='submitted' where id=%s", (opportunity_id,))

    return {
        "submitted": True,
        "title": title,
        "amount": final_amount,
        "period_days": period_days,
        "provider_bid_id": provider_bid_id,
    }
