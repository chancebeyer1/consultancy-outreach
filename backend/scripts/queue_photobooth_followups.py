"""Queue the photobooth follow-up bump as a second manual draft per venue.

Run about 6 days after the first touch (first touches went out 2026-08-16, so on or
after 2026-08-22). Creates step_index=1 manual drafts for venues that were contacted
and have NOT replied, so they show up in the dashboard /drafts queue for manual send.

Skips any venue with a reply logged, and any that already has a follow-up queued.

    uv run python -m scripts.queue_photobooth_followups            # dry run
    uv run python -m scripts.queue_photobooth_followups --execute
"""

from __future__ import annotations

import sys

import psycopg
from psycopg.types.json import Jsonb

from config import require

FOLLOWUP = (
    "Hi, following up on the photo booth. Still picking my first few spots on the "
    "westside. Free to the bar, I handle all upkeep, you keep a cut of every strip. "
    "Worth a quick look? 3237101190. Thanks,"
)

SELECT_TARGETS = """
    select l.id, l.name, d.channel
      from drafts d
      join leads l on l.id = d.lead_id
      join campaigns c on c.id = l.campaign_id
     where c.slug = 'photobooth-route'
       and d.step_index = 0
       and d.status = 'sent'
       and not exists (select 1 from replies r where r.lead_id = l.id)
       and not exists (
             select 1 from drafts d2
              where d2.lead_id = l.id and d2.step_index = 1
           )
     order by l.name
"""


def main() -> None:
    assert not any(ch in FOLLOWUP for ch in ("-", "–", "—")), "no dashes allowed"
    execute = "--execute" in sys.argv
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        cur.execute(SELECT_TARGETS)
        rows = cur.fetchall()
        print(f"venues needing a follow up: {len(rows)}")
        if not execute:
            for _, name, ch in rows[:5]:
                print(f"  {name} ({ch})")
            if len(rows) > 5:
                print(f"  ... and {len(rows) - 5} more")
            print("\nDRY RUN - nothing written. Re-run with --execute to apply.")
            return

        hook = {
            "type": "follow-up",
            "reference": "bump, 6 days after first touch",
            "why_it_matters": "one bump only; non responders get a walk in instead",
            "signal_strength": 1,
        }
        for lead_id, _name, channel in rows:
            cur.execute(
                """
                insert into drafts (lead_id, channel, step_index, hook, body, status, variant)
                values (%s, %s, 1, %s, %s, 'draft', 'manual')
                on conflict (lead_id, channel, step_index, variant) do nothing
                """,
                (lead_id, channel, Jsonb(hook), FOLLOWUP),
            )
        conn.commit()
        print(f"APPLIED: queued {len(rows)} follow ups in /drafts")


if __name__ == "__main__":
    main()
