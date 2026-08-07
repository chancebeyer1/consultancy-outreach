"""Founder-search local runner — drafts venue posts and sweeps for candidates by hand.
Same logic the scheduled daily leg runs (workers.founders_draft / workers.founders_sweep).

    cd backend

    # dry run: draft venue posts / profile copy for every opted-in campaign, write nothing
    uv run python -m scripts.founders draft --dry-run

    # dry run: read-only discovery (HN Algolia; Reddit only if creds set), write nothing
    uv run python -m scripts.founders sweep --dry-run

    # for real (needs DATABASE_URL): drafts land on the dashboard /founders queue
    uv run python -m scripts.founders draft
    uv run python -m scripts.founders sweep

    # one campaign only
    uv run python -m scripts.founders draft --campaign panelpath-partners

Campaigns opt in via `founder_search = true` in backend/campaigns/<slug>/campaign.toml.
Nothing is ever auto-posted — a human pastes every post and sends every reachout.
"""
from __future__ import annotations

import sys
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(add_completion=False, help="Draft founder-search copy / sweep for candidates.")
console = Console()

_CampaignOpt = Annotated[str, typer.Option("--campaign", help="One campaign slug; default: all opted-in.")]
_DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Draft/match only; no DB writes.")]


def _print_result(result: dict) -> None:
    console.rule("[bold]Done")
    console.print({k: v for k, v in result.items() if k not in ("drafted_items", "errors")})
    for it in result.get("drafted_items", []):
        console.print(f"  [green]drafted[/green] {it}")
    for err in result.get("errors", []):
        console.print(f"  [yellow]note:[/yellow] {err}")
    if not result.get("dry_run") and result.get("drafted"):
        console.print("\n  next: review on the dashboard [bold]/founders[/bold] — you paste every post by hand")


@app.command()
def draft(campaign: _CampaignOpt = "", dry_run: _DryRunOpt = False) -> None:
    """Draft venue posts + profile copy for opted-in campaigns."""
    from workers.founders_draft import draft_all

    console.rule("[bold]Founder-search draft")
    _print_result(draft_all(campaign or None, dry_run=dry_run))


@app.command()
def sweep(campaign: _CampaignOpt = "", dry_run: _DryRunOpt = False) -> None:
    """Read-only discovery: HN who-wants-to-be-hired / who-is-hiring + r/cofounder."""
    from workers.founders_sweep import sweep_all

    console.rule("[bold]Founder-search sweep (read-only)")
    _print_result(sweep_all(campaign or None, dry_run=dry_run))


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
