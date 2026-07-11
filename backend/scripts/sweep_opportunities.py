"""Sweep for software / AI-agent work and draft bids — the local runner for the bidding
module (workers.opportunity_sourcing). Same logic the scheduled sweep runs, invocable by hand.

    cd backend

    # dry run: fetch + fit-score, draft nothing, write nothing — just see what's out there
    uv run python -m scripts.sweep_opportunities --dry-run

    # for real: score, draft high-fit proposals, ingest to Postgres (needs DATABASE_URL)
    uv run python -m scripts.sweep_opportunities

Sources are opt-in by env var (see .env.example): SAM.gov + Upwork need keys; RemoteOK, HN
"who is hiring", and LinkedIn-via-Unipile need nothing extra. An unconfigured source is just
skipped. Nothing is ever auto-submitted — review + submit drafted bids from the dashboard /bids.
"""
from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console

from workers.opportunity_sourcing import source_all

app = typer.Typer(add_completion=False, help="Sweep contract/freelance sources and draft bids.")
console = Console()


@app.command()
def run(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Fetch + score only; no drafts, no DB writes.")] = False,
    time_budget: Annotated[float, typer.Option(help="Seconds before deferring the rest to the next sweep.")] = 500.0,
) -> None:
    console.rule("[bold]Opportunity sweep")
    result = source_all(dry_run=dry_run, time_budget_s=time_budget)
    console.rule("[bold]Done")
    console.print(
        f"  gathered: {result['gathered']}  new: {result['new']}  "
        f"scored: [cyan]{result['scored']}[/cyan]  drafted: [green]{result['drafted']}[/green]  "
        f"ingested: {result['ingested']}  ({result['elapsed_s']}s)"
    )
    for err in result.get("errors", []):
        console.print(f"  [yellow]note:[/yellow] {err}")
    if not dry_run and result["drafted"]:
        console.print("\n  next: review the drafted bids in the dashboard [bold]/bids[/bold]")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
