"""Push the current VENUES message bodies onto existing pending photobooth drafts.

Run after editing message text in scripts/seed_photobooth_route.py (the single
source of truth for bodies). Only touches drafts still in status='draft' — anything
already marked sent keeps the body that was actually sent. Also enforces the
operator's handwritten rule: fails loudly if any pending body contains a hyphen,
en dash, or em dash.

    uv run python -m scripts.update_photobooth_bodies
"""

from __future__ import annotations

import psycopg

from config import require
from scripts.seed_photobooth_route import VENUES

BANNED = ("-", "–", "—")  # hyphen, en dash, em dash


def main() -> None:
    violations = [v[0] for v in VENUES if any(ch in v[9] for ch in BANNED)]
    if violations:
        raise SystemExit(f"dash characters found in VENUES messages: {violations}")

    updated = 0
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        for name, area, tier, ig, email, subject, vibe, hook, busy, msg in VENUES:
            cur.execute(
                """
                update drafts d
                   set body = %s
                  from leads l
                 where l.id = d.lead_id
                   and l.linkedin_url = %s
                   and d.channel like 'manual_%%'
                   and d.status = 'draft'
                   and d.body is distinct from %s
                """,
                (msg, f"https://instagram.com/{ig}", msg),
            )
            updated += cur.rowcount
        conn.commit()
        print(f"bodies updated: {updated}")

        cur.execute(
            r"""
            select l.name from drafts d
            join leads l on l.id = d.lead_id
            join campaigns c on c.id = l.campaign_id
            where c.slug = 'photobooth-route' and d.status = 'draft'
              and (d.body like '%%-%%' or d.body like '%%' || chr(8211) || '%%'
                   or d.body like '%%' || chr(8212) || '%%')
            """
        )
        bad = [r[0] for r in cur.fetchall()]
        print(f"pending bodies containing dashes: {len(bad)}" + (f" -> {bad}" if bad else ""))


if __name__ == "__main__":
    main()
