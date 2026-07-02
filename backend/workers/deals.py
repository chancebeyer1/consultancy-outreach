"""Deal pipeline helpers.

A deal is auto-created the moment a reply is classified 'interested' — one open deal per lead.
The dashboard then moves it through stages (interested -> call_booked -> proposal_sent ->
won/lost) and tracks value. ensure_deal() is idempotent; backfill_deals() seeds deals from any
past interested replies so the pipeline isn't empty on day one.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from config import require


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def ensure_deal(lead_id: str, *, source: str = "reply", cur=None) -> str | None:
    """Create an open deal for a lead if one doesn't already exist. Returns the deal id.

    Pulls contact/company/campaign/owner from the lead. Pass an existing cursor to run inside a
    caller's transaction; otherwise it opens its own connection.
    """
    if not lead_id:
        return None

    def _run(c) -> str | None:
        c.execute(
            "select id from deals where lead_id = %s and stage not in ('won','lost') limit 1",
            (lead_id,),
        )
        row = c.fetchone()
        if row:
            return str(row[0])
        c.execute(
            "select name, company, campaign_id, user_id from leads where id = %s", (lead_id,)
        )
        lead = c.fetchone()
        name, company, campaign_id, user_id = lead if lead else (None, None, None, None)
        c.execute(
            """
            insert into deals (lead_id, campaign_id, user_id, contact_name, company, stage, source)
            values (%s, %s, %s, %s, %s, 'interested', %s)
            on conflict (lead_id) where (lead_id is not null and stage not in ('won','lost'))
            do nothing
            returning id
            """,
            (lead_id, campaign_id, user_id, name, company, source),
        )
        r = c.fetchone()
        return str(r[0]) if r else None

    if cur is not None:
        return _run(cur)
    with _connect() as conn, conn.cursor() as c:
        return _run(c)


def backfill_deals() -> dict:
    """Create deals for any past replies classified 'interested' that don't have one yet."""
    created = 0
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select distinct lead_id from replies where lead_id is not null and intent = 'interested'"
        )
        lead_ids = [r[0] for r in cur.fetchall()]
        for lid in lead_ids:
            if ensure_deal(str(lid), source="reply", cur=cur):
                created += 1
    return {"interested_leads": len(lead_ids), "deals_ensured": created}


if __name__ == "__main__":
    import json

    print(json.dumps(backfill_deals()))
