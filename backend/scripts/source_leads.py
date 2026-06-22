"""Automated lead sourcing — run a LinkedIn / Sales-Navigator search via Unipile
and write a run_pipeline-ready CSV of the targeted audience.

Replaces the manual "export a CSV from Sales Nav" step. Build the search once in the
Sales Navigator UI (precise filters: titles, geography, company size, keywords), copy
the browser URL, and put it in the campaign's campaign.toml as `search_url` (or pass
--search-url). This paginates the search, de-dupes against people already sourced for
the campaign, and writes runs/<campaign>-leads-<date>.csv.

    cd backend

    # use the campaign's saved search_url
    uv run python -m scripts.source_leads --campaign mortgage-discovery-sprint --limit 150

    # or an ad-hoc search URL (classic or Sales Navigator)
    uv run python -m scripts.source_leads --search-url "https://www.linkedin.com/sales/search/people?query=..." --limit 100

Then feed the CSV into the pipeline:

    uv run python -m scripts.run_pipeline runs/<file>.csv --campaign mortgage-discovery-sprint

This is read-only on LinkedIn, but it's still YOUR account hitting LinkedIn search —
keep volume reasonable and let --delay space the pages out. Sales Navigator search
needs a Sales Navigator seat on the connected account.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from campaigns_loader import load_campaign
from clients import unipile
from config import BACKEND_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

RUNS_DIR = BACKEND_DIR / "runs"
CSV_FIELDS = ["linkedin_url", "name", "company", "role", "location"]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")


@app.command()
def main(
    campaign: Annotated[
        str | None,
        typer.Option("--campaign", help="Campaign slug; sources from its search_url."),
    ] = None,
    search_url: Annotated[
        str | None,
        typer.Option("--search-url", help="Ad-hoc search URL (overrides the campaign's)."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max NEW leads to source this run."),
    ] = 100,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", help="Safety cap on pages fetched."),
    ] = 40,
    delay: Annotated[
        float,
        typer.Option("--delay", help="Seconds to pause between pages (be gentle)."),
    ] = 1.5,
    out: Annotated[
        Path | None,
        typer.Option(help="Output CSV path. Default: runs/<campaign>-leads-<date>.csv"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Fetch + preview but don't write CSV or ledger."),
    ] = False,
) -> None:
    # Resolve the search URL: explicit flag wins, else the campaign's saved one.
    slug = campaign or "search"
    if not search_url and campaign:
        c = load_campaign(campaign)
        search_url = c.search_url
        slug = c.slug
    if not search_url:
        console.print(
            "[red]No search URL.[/red] Pass --search-url, or set `search_url` in the "
            "campaign's campaign.toml."
        )
        raise typer.Exit(2)

    # Idempotency: skip people already sourced for this campaign.
    ledger_path = RUNS_DIR / f"sourced-{slug}.jsonl"
    seen = {r.get("linkedin_url") for r in _read_jsonl(ledger_path) if r.get("linkedin_url")}
    console.print(f"[dim]sourcing up to {limit} new leads · already sourced: {len(seen)}[/dim]")

    collected: list[dict[str, Any]] = []
    cursor: str | None = None
    pages = 0
    while len(collected) < limit and pages < max_pages:
        try:
            page = unipile.search_people(search_url=search_url, cursor=cursor)
        except Exception as e:  # noqa: BLE001 — script-level catch
            console.print(f"[red]search failed on page {pages + 1}: {e}[/red]")
            break
        items = page.get("items", [])
        if not items:
            break
        for lead in items:
            url = lead.get("linkedin_url")
            if not url or url in seen:
                continue
            seen.add(url)
            collected.append(lead)
            if len(collected) >= limit:
                break
        cursor = page.get("cursor")
        pages += 1
        if not cursor:
            break
        if delay:
            time.sleep(delay)

    if not collected:
        console.print("[yellow]No new leads (search exhausted or all already sourced).[/yellow]")
        return

    table = Table(title=f"Sourced · {len(collected)} new leads · {pages} page(s)")
    table.add_column("#", style="dim", width=3)
    table.add_column("Name")
    table.add_column("Role / Company", overflow="fold", max_width=44)
    table.add_column("LinkedIn", overflow="fold")
    for i, ld in enumerate(collected[:25], 1):
        rc = " · ".join(p for p in (ld.get("role"), ld.get("company")) if p)
        table.add_row(str(i), ld.get("name") or "?", rc or "—", ld.get("linkedin_url"))
    console.print(table)
    if len(collected) > 25:
        console.print(f"[dim]… +{len(collected) - 25} more[/dim]")

    if dry_run:
        console.print("[bold yellow]Dry run — nothing written.[/bold yellow]")
        return

    out_path = out or (RUNS_DIR / f"{slug}-leads-{datetime.now(UTC):%Y-%m-%d}.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for ld in collected:
            writer.writerow({k: ld.get(k, "") or "" for k in CSV_FIELDS})

    _append_jsonl(ledger_path, [{"linkedin_url": ld["linkedin_url"]} for ld in collected])

    console.rule("[bold]Sourced")
    console.print(f"  new leads: [green]{len(collected)}[/green]")
    console.print(f"  csv:       {out_path}")
    console.print(f"  ledger:    {ledger_path}")
    next_campaign = f" --campaign {slug}" if campaign else ""
    console.print(
        f"\n  next: [bold]uv run python -m scripts.run_pipeline {out_path}{next_campaign}[/bold]"
    )


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
