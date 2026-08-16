"""One-off: inspect the pending-drafts review queue (what /drafts shows and why).

Read-only. Run: uv run python -m scripts.inspect_drafts_queue
"""

from __future__ import annotations

import psycopg

from config import require


def main() -> None:
    with psycopg.connect(require("DATABASE_URL")) as conn, conn.cursor() as cur:
        print("== campaigns (DB truth) ==")
        cur.execute(
            "select slug, status, auto_send, coalesce(array_to_string(channels, '+'), '-') "
            "from campaigns order by status, slug"
        )
        for slug, status, auto, ch in cur.fetchall():
            print(f"  {slug:32s} status={status:8s} auto_send={auto} channels={ch}")

        print("\n== pending drafts (status='draft') by campaign x channel ==")
        cur.execute(
            """
            select coalesce(c.slug, '(no campaign)'), d.channel, count(*)
            from drafts d
            join leads l on l.id = d.lead_id
            left join campaigns c on c.id = l.campaign_id
            where d.status = 'draft'
            group by 1, 2 order by 1, 2
            """
        )
        total = 0
        for slug, channel, n in cur.fetchall():
            total += n
            print(f"  {slug:32s} {channel:18s} {n}")
        print(f"  TOTAL: {total}")

        print("\n== PanelPath pending breakdown (sendability) ==")
        cur.execute(
            """
            select c.slug, d.channel,
                   case when s.fit_score is null then 'unscored'
                        when s.fit_score >= 60 then 'fit>=60' else 'fit<60' end,
                   case when d.channel like 'linkedin%%' then 'n/a'
                        when l.email is null then 'no-email'
                        else coalesce(l.email_status, 'unknown') end,
                   count(*)
            from drafts d
            join leads l on l.id = d.lead_id
            join campaigns c on c.id = l.campaign_id
            left join scores s on s.lead_id = l.id
            where d.status = 'draft' and c.slug like 'panelpath%%'
            group by 1, 2, 3, 4 order by 1, 2, 3, 4
            """
        )
        for slug, channel, fit, estat, n in cur.fetchall():
            print(f"  {slug:22s} {channel:18s} {fit:9s} email={estat:14s} {n}")

        print("\n== oldest / newest pending panelpath draft ==")
        cur.execute(
            """
            select min(d.generated_at)::date, max(d.generated_at)::date
            from drafts d join leads l on l.id = d.lead_id
            join campaigns c on c.id = l.campaign_id
            where d.status = 'draft' and c.slug like 'panelpath%%'
            """
        )
        print(f"  {cur.fetchone()}")

        print("\n== admin profile ==")
        cur.execute("select id, name from profiles where is_admin limit 1")
        row = cur.fetchone()
        print(f"  id={row[0]} name={row[1]}" if row else "  none")

        print("\n== photobooth campaign exists? ==")
        cur.execute("select count(*) from campaigns where slug = 'photobooth-route'")
        print(f"  {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
