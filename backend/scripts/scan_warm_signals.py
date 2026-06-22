"""Warm-signal scraper — PARKED in the Unipile re-architecture.

This pulled profile-viewers / post-engagers lists from Apify LinkedIn actors.
Apify was dropped to consolidate the stack. Unipile can surface some of these
signals natively and may serve this later; for now the scraper is parked.

You can still run signal-triggered outreach: source a lead list however you
like (manual export, a one-off scrape, a CSV a partner sends you) and tag it at
ingest time so the trigger flows through the pipeline:

    uv run python -m scripts.run_pipeline leads.csv --trigger profile_view
    uv run python -m scripts.run_pipeline leads.csv --trigger post_engagement

`--trigger` accepts: list | profile_view | post_engagement | funding_event | new_role.
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


@app.command()
def main() -> None:
    console.print(
        "[yellow]scan_warm_signals is parked.[/yellow] Apify was removed in the "
        "Unipile re-architecture.\n\n"
        "Source a signal list yourself, then tag it at ingest:\n"
        "  [bold]uv run python -m scripts.run_pipeline leads.csv --trigger profile_view[/bold]\n"
        "  [bold]uv run python -m scripts.run_pipeline leads.csv --trigger post_engagement[/bold]"
    )
    raise typer.Exit(0)


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
