"""Redraft cold-email openers for leads ALREADY in the DB.

Sibling of workers.replenish.draft_connects_for_existing, for the email channel. Needed
whenever the email prompt changes: purging stale drafts leaves the LEADS in place, and Apollo
sourcing then skips them as already-seen, so nothing regenerates. This walks those leads and
writes a fresh opener from the current prompt (one Claude call each, no re-enrichment).

    uv run python -m scripts.redraft_emails --campaign panelpath-practices --limit 50
"""

from __future__ import annotations

import time
from typing import Any

import psycopg
import typer
from psycopg.types.json import Jsonb
from rich.console import Console

from campaigns_loader import load_campaign
from config import require
from workers.draft import Hook, ab_variant, draft_for_channel

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

AUTO_APPROVE_MIN_FIT = 60  # same floor the rest of the system auto-sends at


@app.command()
def main(
    campaign: str = typer.Option(..., "--campaign", help="campaign slug"),
    limit: int = typer.Option(50, "--limit", help="max leads to redraft this run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="draft but don't write"),
) -> None:
    camp = load_campaign(campaign)
    conn = psycopg.connect(require("DATABASE_URL"))
    try:
        with conn.cursor() as cur:
            cur.execute("select id, auto_send from campaigns where slug = %s", (campaign,))
            row = cur.fetchone()
            if not row:
                console.print(f"[red]campaign not found:[/red] {campaign}")
                raise typer.Exit(1)
            campaign_id, auto_send = str(row[0]), bool(row[1])
            # Leads with a deliverable email, scored, no email draft yet, no reply yet.
            cur.execute(
                """
                select l.id, l.name, l.company, l.role, sc.fit_score,
                       e.profile_json, e.company_signals_json, e.hooks_json
                from leads l
                join scores sc on sc.lead_id = l.id
                left join enrichments e on e.lead_id = l.id
                where l.campaign_id = %s
                  and l.email is not null
                  and coalesce(l.email_status, '') <> 'bounced'
                  and not exists (
                      select 1 from drafts d where d.lead_id = l.id and d.channel like 'email%%'
                  )
                  and not exists (select 1 from replies r where r.lead_id = l.id)
                order by sc.fit_score desc
                limit %s
                """,
                (campaign_id, limit),
            )
            candidates = cur.fetchall()

        console.print(f"redrafting {len(candidates)} email opener(s) for [bold]{campaign}[/bold]")
        drafted = approved = failed = 0
        started = time.monotonic()
        for lead_id, name, company, role, fit, profile, signals, hooks_json in candidates:
            enrichment: dict[str, Any] = {
                "profile": profile or {},
                "company_signals": signals or {},
                "recent_posts": [],
                "company": company,
                "name": name,      # first-name fallback for Apollo leads with no profile
                "role": role,
            }
            hooks = [Hook.from_json(h) for h in (hooks_json or [])]
            variant = ab_variant(str(lead_id), salt="email")
            try:
                body = draft_for_channel(
                    "email", enrichment, hooks[0] if hooks else None,
                    campaign=camp, variant=variant,
                )
            except Exception as e:  # noqa: BLE001 — one bad lead must not stop the batch
                console.print(f"  [yellow]skip[/yellow] {name}: {str(e)[:90]}")
                failed += 1
                continue
            if not body or not body.strip():
                failed += 1
                continue
            status = "approved" if (auto_send and int(fit or 0) >= AUTO_APPROVE_MIN_FIT) else "draft"
            drafted += 1
            approved += 1 if status == "approved" else 0
            if dry_run:
                continue
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into drafts (lead_id, channel, step_index, hook, body, status,
                                        variant, generated_at)
                    values (%s, 'email', 0, %s, %s, %s, %s, now())
                    on conflict (lead_id, channel, step_index, variant) do nothing
                    """,
                    (lead_id, Jsonb(hooks[0].__dict__ if hooks else None), body, status, variant),
                )
            conn.commit()
        console.print(
            f"[green]done[/green] — drafted {drafted} ({approved} auto-approved), "
            f"failed {failed}, {time.monotonic() - started:.0f}s"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    app()
