"""Bulk-record the photobooth first touches as manually sent (operator sent all 45 by hand).

Mirrors what the dashboard's "Mark sent" button does per card: drafts.status='sent'
plus a sends row with provider='manual'. Idempotent — a draft that already has a
sends row is skipped, so re-running never double-counts.

    uv run python -m scripts.mark_photobooth_sent            # dry run
    uv run python -m scripts.mark_photobooth_sent --execute
"""

from __future__ import annotations

import sys

import psycopg

from config import require

SELECT_PENDING = """
    select d.id, l.name, d.channel
      from drafts d
      join leads l on l.id = d.lead_id
      join campaigns c on c.id = l.campaign_id
     where c.slug = 'photobooth-route'
       and d.status = 'draft'
       and d.channel like 'manual_%'
       and not exists (select 1 from sends s where s.draft_id = d.id)
     order by l.name
"""


def main() -> None:
    execute = "--execute" in sys.argv
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute(SELECT_PENDING)
        rows = cur.fetchall()
        print(f"first touches to mark sent: {len(rows)}")
        if not execute:
            print("\nDRY RUN - nothing written. Re-run with --execute to apply.")
            return

        ids = [r[0] for r in rows]
        cur.execute(
            "update drafts set status = 'sent', decided_at = now() where id = any(%s)", (ids,)
        )
        updated = cur.rowcount
        cur.executemany(
            "insert into sends (draft_id, provider, status) values (%s, 'manual', 'sent')",
            [(i,) for i in ids],
        )
        # Lead lifecycle: first touch is out, so these are contacted, not just drafted.
        cur.execute(
            """
            update leads l set status = 'sent', updated_at = now()
              from campaigns c
             where c.id = l.campaign_id and c.slug = 'photobooth-route'
               and l.status = 'drafted'
            """
        )
        leads = cur.rowcount
        conn.commit()
        print(f"APPLIED: drafts marked sent={updated}, sends rows={len(ids)}, leads advanced={leads}")


if __name__ == "__main__":
    main()
