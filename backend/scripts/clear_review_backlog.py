"""One-off (2026-08-16): clear the /drafts review backlog per operator instruction.

The operator wants the review queue to hold ONLY the photobooth-route manual drafts.
Three buckets, decided per the sendability data in the DB:

  1. APPROVE  — PanelPath pending drafts the senders can actually deliver:
                linkedin_connect (quota-paced), and email where the lead has a
                deliverable address. Approving hands them to the existing
                rate-limited senders; nothing sends in a burst.
  2. REJECT   — PanelPath email drafts whose lead has NO deliverable email
                (the email sender can never pick them up; they'd sit forever).
  3. REJECT   — pending drafts belonging to PAUSED campaigns (senders skip
                paused campaigns; if a campaign is ever unpaused, replenish
                re-drafts fresh — month-old drafts would be stale anyway).

Default is a dry run (prints counts, writes nothing).

    uv run python -m scripts.clear_review_backlog            # dry run
    uv run python -m scripts.clear_review_backlog --execute  # do it
"""

from __future__ import annotations

import sys

import psycopg

from config import require

REASON_NO_EMAIL = "bulk-clear 2026-08-16: lead has no deliverable email (unsendable)"
REASON_PAUSED = "bulk-clear 2026-08-16: campaign paused (operator emptied review queue)"

APPROVE_SQL = """
    update drafts d
       set status = 'approved', decided_at = now()
      from leads l join campaigns c on c.id = l.campaign_id
     where l.id = d.lead_id
       and d.status = 'draft'
       and c.slug like 'panelpath%%'
       and c.status = 'active'
       and (
            d.channel in ('linkedin_connect', 'linkedin_inmail')
            or (d.channel = 'email' and l.email is not null
                and l.email_status = 'deliverable')
       )
"""

REJECT_NO_EMAIL_SQL = """
    update drafts d
       set status = 'rejected', rejection_reason = %s, decided_at = now()
      from leads l join campaigns c on c.id = l.campaign_id
     where l.id = d.lead_id
       and d.status = 'draft'
       and c.slug like 'panelpath%%'
       and d.channel = 'email'
       and (l.email is null or coalesce(l.email_status, '') <> 'deliverable')
"""

REJECT_PAUSED_SQL = """
    update drafts d
       set status = 'rejected', rejection_reason = %s, decided_at = now()
      from leads l join campaigns c on c.id = l.campaign_id
     where l.id = d.lead_id
       and d.status = 'draft'
       and c.status <> 'active'
       and c.slug <> 'photobooth-route'
"""


COUNT_APPROVE = """
    select count(*) from drafts d
    join leads l on l.id = d.lead_id
    join campaigns c on c.id = l.campaign_id
    where d.status = 'draft' and c.slug like 'panelpath%%' and c.status = 'active'
      and (d.channel in ('linkedin_connect', 'linkedin_inmail')
           or (d.channel = 'email' and l.email is not null
               and l.email_status = 'deliverable'))
"""
COUNT_NO_EMAIL = """
    select count(*) from drafts d
    join leads l on l.id = d.lead_id
    join campaigns c on c.id = l.campaign_id
    where d.status = 'draft' and c.slug like 'panelpath%%' and d.channel = 'email'
      and (l.email is null or coalesce(l.email_status, '') <> 'deliverable')
"""
COUNT_PAUSED = """
    select count(*) from drafts d
    join leads l on l.id = d.lead_id
    join campaigns c on c.id = l.campaign_id
    where d.status = 'draft' and c.status <> 'active' and c.slug <> 'photobooth-route'
"""


def _count(cur, sql: str) -> int:
    cur.execute(sql)
    return int(cur.fetchone()[0])


def main() -> None:
    execute = "--execute" in sys.argv
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        n_approve = _count(cur, COUNT_APPROVE)
        n_no_email = _count(cur, COUNT_NO_EMAIL)
        n_paused = _count(cur, COUNT_PAUSED)
        print(f"approve (panelpath, sendable):        {n_approve}")
        print(f"reject  (panelpath, no email):        {n_no_email}")
        print(f"reject  (paused campaigns):           {n_paused}")

        if not execute:
            print("\nDRY RUN - nothing written. Re-run with --execute to apply.")
            return

        cur.execute(APPROVE_SQL)
        approved = cur.rowcount
        cur.execute(REJECT_NO_EMAIL_SQL, (REASON_NO_EMAIL,))
        rej_email = cur.rowcount
        cur.execute(REJECT_PAUSED_SQL, (REASON_PAUSED,))
        rej_paused = cur.rowcount
        conn.commit()
        print(f"\nAPPLIED: approved={approved} rejected_no_email={rej_email} "
              f"rejected_paused={rej_paused}")

        cur.execute("select count(*) from drafts where status = 'draft'")
        print(f"remaining pending drafts: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
