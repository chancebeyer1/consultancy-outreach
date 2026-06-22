"""Phase 1 CLI — generate a personalized outreach draft for one LinkedIn URL.

Usage (from the project root):

    cd backend
    uv run python -m scripts.draft_one https://linkedin.com/in/example
    uv run python -m scripts.draft_one https://linkedin.com/in/example --save out.json
    uv run python -m scripts.draft_one --from-enrichment cached.json    # skip API calls

This is the validation tool: read every output, edit the prompts in
backend/prompts/ until messages feel like they were hand-written by you.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

# Force UTF-8 on Windows consoles (cp1252 chokes on rich's box-drawing chars).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from campaigns_loader import load_campaign
from workers import draft, enrich, score

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


@app.command()
def main(
    linkedin_url: Annotated[
        str | None,
        typer.Argument(help="LinkedIn profile URL of the prospect."),
    ] = None,
    save: Annotated[
        Path | None,
        typer.Option(help="Write the full enrichment+drafts JSON to this path."),
    ] = None,
    from_enrichment: Annotated[
        Path | None,
        typer.Option(help="Skip API calls; load enrichment from a previously saved JSON file."),
    ] = None,
    skip_score: Annotated[
        bool,
        typer.Option("--skip-score", help="Skip the LLM ICP-fit scoring step."),
    ] = False,
    campaign: Annotated[
        str | None,
        typer.Option(
            help="Campaign slug (or id) — selects the ICP + offer. Omitted → default campaign."
        ),
    ] = None,
) -> None:
    try:
        active_campaign = load_campaign(campaign)
    except (FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]Couldn't load campaign '{campaign or 'default'}':[/red] {e}")
        raise typer.Exit(2) from e
    console.print(
        f"[dim]Campaign: [bold]{active_campaign.name}[/bold] ({active_campaign.slug})[/dim]"
    )

    if from_enrichment:
        console.print(f"[dim]Loading enrichment from {from_enrichment}[/dim]")
        enrichment = json.loads(from_enrichment.read_text(encoding="utf-8"))
    else:
        if not linkedin_url:
            console.print("[red]Provide a LinkedIn URL or --from-enrichment[/red]")
            raise typer.Exit(2)
        console.rule("[bold cyan]1. Enrich")
        with console.status("Calling Unipile + Tavily..."):
            enrichment = enrich.enrich(linkedin_url)
        _summarize_enrichment(enrichment)

    # 2. Score
    score_obj: dict[str, object] | None = None
    if not skip_score:
        console.rule("[bold cyan]2. Score")
        with console.status("Asking Claude to score ICP fit..."):
            score_obj = score.score(enrichment, campaign=active_campaign)
        _print_score(score_obj)
        if isinstance(score_obj.get("fit_score"), int) and score_obj["fit_score"] < 60:
            console.print("[yellow]Fit score < 60. Proceeding anyway since this is Phase 1.[/yellow]")

    # 3. Hooks
    console.rule("[bold cyan]3. Extract hooks")
    with console.status("Extracting hooks..."):
        hooks = draft.extract_hooks(enrichment, campaign=active_campaign)
    _print_hooks(hooks)
    chosen = draft.pick_hook(hooks, "linkedin_dm")
    if not chosen:
        console.print("[red]No hooks extracted — drafting will be generic.[/red]")

    # 4. Drafts
    console.rule("[bold cyan]4. Drafts")
    drafts_out: dict[str, str] = {}
    for channel in ["linkedin_connect", "linkedin_dm", "email"]:
        with console.status(f"Drafting {channel}..."):
            body = draft.draft_for_channel(channel, enrichment, chosen, campaign=active_campaign)
        drafts_out[channel] = body
        console.print(
            Panel(
                body,
                title=f"[bold]{channel}[/bold]  ({len(body)} chars)",
                border_style="green",
            )
        )

    # 5. Save
    if save:
        save.write_text(
            json.dumps(
                {
                    "enrichment": enrichment,
                    "score": score_obj,
                    "hooks": [h.__dict__ for h in hooks],
                    "chosen_hook": chosen.__dict__ if chosen else None,
                    "drafts": drafts_out,
                },
                default=str,
                indent=2,
            ),
            encoding="utf-8",
        )
        console.print(f"[dim]Saved to {save}[/dim]")


def _summarize_enrichment(enrichment: dict) -> None:
    profile = enrichment.get("profile") or {}
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_row("Name", profile.get("full_name") or "?")
    table.add_row("Headline", profile.get("headline") or "?")
    table.add_row("Company", enrichment.get("company") or "?")
    table.add_row(
        "Location",
        (profile.get("city") or "") + ", " + (profile.get("country_full_name") or ""),
    )
    table.add_row("Recent posts", str(len(enrichment.get("recent_posts") or [])))
    table.add_row("Company signals", str(sum(len(v) for v in (enrichment.get("company_signals") or {}).values())))
    console.print(table)


def _print_score(score_obj: dict) -> None:
    fit = score_obj.get("fit_score")
    color = "green" if isinstance(fit, int) and fit >= 75 else "yellow" if isinstance(fit, int) and fit >= 60 else "red"
    console.print(
        Panel.fit(
            f"[bold {color}]{fit}[/bold {color}]   segment: {score_obj.get('segment')}\n\n"
            f"{score_obj.get('rationale')}",
            title="ICP fit",
            border_style=color,
        )
    )
    strong = score_obj.get("strong_signals") or []
    dq = score_obj.get("disqualifiers") or []
    if strong:
        console.print("[green]Strong signals:[/green] " + ", ".join(strong))
    if dq:
        console.print("[red]Disqualifiers:[/red] " + ", ".join(dq))


def _print_hooks(hooks: list) -> None:
    if not hooks:
        console.print("[yellow]No hooks extracted.[/yellow]")
        return
    table = Table(title="Hooks (highest signal first)")
    table.add_column("S", style="bold")
    table.add_column("Type")
    table.add_column("Reference", max_width=60, overflow="fold")
    table.add_column("Why", max_width=40, overflow="fold")
    for h in hooks:
        table.add_row(str(h.signal_strength), h.type, h.reference, h.why_it_matters)
    console.print(table)


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
