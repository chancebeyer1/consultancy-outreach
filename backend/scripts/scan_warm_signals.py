"""Pull warm-signal lead lists from Apify actors.

Two signal sources supported in v1:

  - profile-viewers  : people who recently viewed your LinkedIn profile
  - post-engagers    : people who liked/commented on a specific post of yours

Both run through Apify actors. You'll need:
  1. APIFY_API_TOKEN in .env
  2. A LinkedIn session cookie (`li_at`) — most Apify LinkedIn actors require
     it as input. Export from your browser's cookies (DevTools → Application
     → Cookies → linkedin.com → li_at).

Output: a CSV of (linkedin_url, company, signal_summary) that you pipe into
run_pipeline with the matching --trigger:

    uv run python -m scripts.scan_warm_signals profile-viewers \\
        --li-at "AQE..."                                          \\
        --out runs/profile-viewers-2026-05.csv

    uv run python -m scripts.run_pipeline runs/profile-viewers-2026-05.csv \\
        --trigger profile_view

Actor ids are configurable. Defaults below point at well-known LinkedIn
scrapers on the Apify marketplace. Verify the actor input schema in the
Apify dashboard before running — input keys differ between actors.
"""

from __future__ import annotations

import csv
import datetime
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from clients import apify
from config import BACKEND_DIR

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

# Default Apify actor ids — override at CLI if you find a better one.
# These are placeholder paths; verify before first run by browsing
# https://apify.com/store?search=linkedin
DEFAULT_ACTORS = {
    "profile-viewers": os.environ.get(
        "APIFY_ACTOR_PROFILE_VIEWERS", "apify/linkedin-profile-views-scraper"
    ),
    "post-engagers": os.environ.get(
        "APIFY_ACTOR_POST_ENGAGERS", "apify/linkedin-post-engagers-scraper"
    ),
}


def _normalize_item(item: dict[str, Any]) -> dict[str, str]:
    """Different actors use different field names. Normalize to what we need."""
    url = (
        item.get("linkedinUrl")
        or item.get("profileUrl")
        or item.get("url")
        or item.get("linkedin_url")
        or ""
    )
    name = item.get("fullName") or item.get("name") or item.get("displayName") or ""
    company = item.get("company") or item.get("currentCompany") or item.get("headline") or ""
    headline = item.get("headline") or ""
    return {
        "linkedin_url": url.strip(),
        "name": name.strip(),
        "company": company.strip(),
        "headline": headline.strip(),
    }


def _write_csv(rows: list[dict[str, str]], signal_kind: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["linkedin_url", "company", "signal_kind", "signal_summary"])
        for row in rows:
            summary_bits = [row["name"]]
            if row["headline"]:
                summary_bits.append(row["headline"])
            w.writerow(
                [
                    row["linkedin_url"],
                    row["company"],
                    signal_kind,
                    " — ".join(summary_bits),
                ]
            )


@app.command()
def main(
    signal: Annotated[
        str,
        typer.Argument(help="Which signal to scan. One of: profile-viewers, post-engagers."),
    ],
    li_at: Annotated[
        str | None,
        typer.Option(help="LinkedIn `li_at` session cookie. Often required by the actor."),
    ] = None,
    post_url: Annotated[
        str | None,
        typer.Option(help="For 'post-engagers': the LinkedIn post URL to scan."),
    ] = None,
    actor_id: Annotated[
        str | None,
        typer.Option(help="Override the Apify actor id."),
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option(help="Output CSV. Default: runs/<signal>-<date>.csv"),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option(help="Max seconds to wait for the actor run."),
    ] = 600,
) -> None:
    if signal not in DEFAULT_ACTORS:
        console.print(f"[red]Unknown signal '{signal}'. Use: {', '.join(DEFAULT_ACTORS)}[/red]")
        raise typer.Exit(2)

    actor = actor_id or DEFAULT_ACTORS[signal]

    # Build actor input — these keys are the LOWEST-COMMON-DENOMINATOR
    # across LinkedIn actors; you may need to tweak for the specific actor.
    input_payload: dict[str, Any] = {}
    if li_at:
        input_payload["cookie"] = [{"name": "li_at", "value": li_at, "domain": ".linkedin.com"}]
    if signal == "post-engagers":
        if not post_url:
            console.print("[red]post-engagers needs --post-url[/red]")
            raise typer.Exit(2)
        input_payload["postUrls"] = [post_url]
    elif signal == "profile-viewers":
        # Most "who viewed you" scrapers don't need extra input beyond the
        # session cookie — they hit the logged-in user's own URL.
        input_payload["maxResults"] = 100

    console.rule(f"[bold cyan]Apify · {signal} · actor={actor}")

    run, items = apify.run_actor_and_collect(
        actor, input_payload, timeout_s=timeout
    )

    if run.get("status") != "SUCCEEDED":
        console.print(
            f"[red]Actor run did not succeed (status={run.get('status')}). Inspect at:"
            f"\n  https://console.apify.com/actors/runs/{run.get('id')}[/red]"
        )
        raise typer.Exit(1)

    rows = [_normalize_item(it) for it in items]
    rows = [r for r in rows if r["linkedin_url"] and "linkedin.com/in/" in r["linkedin_url"]]

    if not rows:
        console.print("[yellow]Actor returned no usable LinkedIn URLs.[/yellow]")
        raise typer.Exit(1)

    out_path = out or BACKEND_DIR / "runs" / f"{signal}-{datetime.date.today().isoformat()}.csv"
    _write_csv(rows, signal, out_path)

    table = Table(title="Scan complete")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("dataset items", str(len(items)))
    table.add_row("usable rows", str(len(rows)))
    table.add_row("output", str(out_path))
    console.print(table)

    trigger = "profile_view" if signal == "profile-viewers" else "post_engagement"
    console.print(
        f"\n[dim]Next:[/dim] [bold]uv run python -m scripts.run_pipeline {out_path} "
        f"--trigger {trigger}[/bold]"
    )


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
