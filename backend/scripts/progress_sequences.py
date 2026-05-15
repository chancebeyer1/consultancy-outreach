"""Local runner for the sequence engine.

Same logic the Modal cron runs (`progress_sequences_cron`), exposed as a CLI
so you can:
  - dry-run to see what *would* be pushed before deploying the cron
  - rerun after an outage without scheduling weirdness

Usage:

    cd backend
    uv sync --extra worker

    # show what would be sent — no Heyreach calls
    uv run python -m scripts.progress_sequences --dry-run

    # actually push due steps to Heyreach
    uv run python -m scripts.progress_sequences

    # cap how many to push per run (respect daily caps)
    uv run python -m scripts.progress_sequences --limit 15
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from workers.sequence_send import progress_sequences

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


@app.command()
def main(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Don't actually push to Heyreach."),
    ] = False,
    limit: Annotated[
        int | None,
        typer.Option(help="Cap how many leads to advance this run."),
    ] = None,
) -> None:
    result = progress_sequences(dry_run=dry_run, limit=limit)

    table = Table(title="sequence pass", show_header=False)
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("actionable", str(result["actionable"]))
    table.add_row("pushed", str(result["pushed"]))
    table.add_row("blocked (no approved draft)", str(result["blocked_no_draft"]))
    table.add_row("blocked (no Heyreach campaign id)", str(result["blocked_no_campaign"]))
    table.add_row("failed", str(result["failed"]))
    table.add_row("dry run", str(result["dry_run"]))
    console.print(table)

    details = result.get("details", {})
    if details.get("pushed"):
        console.print("\n[green]Pushed:[/green]")
        for p in details["pushed"]:
            console.print(f"  • lead={p['lead_id']}  step={p['channel']}  draft={p['draft_id']}")
    if details.get("blocked_no_draft"):
        console.print(
            f"\n[yellow]Blocked — no approved draft for next step (lead ids):[/yellow] "
            f"{details['blocked_no_draft']}"
        )
        console.print(
            "[dim]→ Review pending drafts in the dashboard for these leads and approve.[/dim]"
        )
    if details.get("blocked_no_campaign"):
        console.print(
            f"\n[red]Blocked — no Heyreach campaign id configured:[/red] "
            f"{details['blocked_no_campaign']}"
        )
    if details.get("failed"):
        console.print("\n[red]Failed:[/red]")
        for f in details["failed"]:
            console.print(f"  ✗ {f['lead_id']}  {f['error']}")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
