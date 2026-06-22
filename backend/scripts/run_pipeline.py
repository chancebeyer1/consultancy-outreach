"""Bulk pipeline: CSV of LinkedIn URLs → enrich → score → draft → JSONL.

The dashboard ingests the JSONL output; the markdown summary is for quick
eyeballing in a terminal.

Usage:

    cd backend
    uv run python -m scripts.run_pipeline leads.csv
    uv run python -m scripts.run_pipeline leads.csv --out runs/2026-05-14.jsonl
    uv run python -m scripts.run_pipeline leads.csv --min-fit 75 --limit 20
    uv run python -m scripts.run_pipeline leads.csv --skip-existing

CSV format:
    Any CSV with a column whose header contains "linkedin" or "url" (case
    insensitive). Examples that work out of the box: a Sales Navigator
    export, a hand-curated `leads.csv`, a partner-supplied list, etc.

`--skip-existing` deduplicates against any prior JSONL at the output path
so re-running with a longer list is cheap (only new URLs hit the APIs).
"""

from __future__ import annotations

import csv
import datetime
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Force UTF-8 on Windows consoles (cp1252 chokes on ≤ → ✓ etc.).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from campaigns_loader import Campaign, load_campaign
from workers import draft, enrich, score

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


def _detect_url_column(header: list[str]) -> str | None:
    """Find the column with LinkedIn URLs.

    Matches anything with 'linkedin' or 'url' in the name (case-insensitive),
    which covers Sales Nav exports ('Profile Url'), scraper dumps ('linkedinUrl'),
    hand-rolled CSVs ('url'), and Phantombuster outputs ('profileUrl').
    """
    for col in header:
        lower = col.lower().strip()
        if "linkedin" in lower or "url" in lower:
            return col
    return None


def _read_urls(csv_path: Path, url_column: str | None) -> list[str]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV {csv_path} has no header row")
        col = url_column or _detect_url_column(reader.fieldnames)
        if not col:
            raise ValueError(
                f"Couldn't auto-detect the LinkedIn URL column. "
                f"Pass --url-column. Available columns: {reader.fieldnames}"
            )
        urls = [(row.get(col) or "").strip() for row in reader]
    # Filter blanks and obvious non-URLs, dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not u or "linkedin.com/in/" not in u:
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _existing_urls(jsonl_path: Path) -> set[str]:
    if not jsonl_path.exists():
        return set()
    out: set[str] = set()
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                u = obj.get("linkedin_url")
                if u:
                    out.add(u)
            except json.JSONDecodeError:
                continue
    return out


VALID_TRIGGERS = {
    "list",
    "profile_view",
    "post_engagement",
    "funding_event",
    "new_role",
}


def _process_one(
    url: str,
    *,
    skip_score: bool,
    trigger: str = "list",
    campaign: Campaign | None = None,
) -> dict[str, Any]:
    """Run the full pipeline for one URL. Catches its own exceptions so
    one failed lead doesn't kill the whole run."""
    record: dict[str, Any] = {
        "linkedin_url": url,
        "processed_at": datetime.datetime.utcnow().isoformat() + "Z",
        "trigger": trigger,
        "campaign_slug": campaign.slug if campaign else None,
    }
    try:
        enrichment = enrich.enrich(url)
        record["enrichment"] = enrichment

        if not skip_score:
            record["score"] = score.score(enrichment, campaign=campaign)

        hooks = draft.extract_hooks(enrichment, campaign=campaign)
        record["hooks"] = [h.__dict__ for h in hooks]
        chosen = draft.pick_hook(hooks, "linkedin_dm")
        record["chosen_hook"] = chosen.__dict__ if chosen else None

        channels = (
            [c for c in campaign.channels if c in draft.CHANNEL_BUDGETS]
            if campaign and campaign.channels
            else ["linkedin_connect", "linkedin_dm", "email"]
        )
        record["drafts"] = {
            channel: draft.draft_for_channel(channel, enrichment, chosen, campaign=campaign)
            for channel in channels
        }
        record["status"] = "ok"
    except Exception as e:  # noqa: BLE001 — script-level catch is intentional
        record["status"] = "failed"
        record["error"] = f"{type(e).__name__}: {e}"
    return record


def _write_md_summary(records: list[dict[str, Any]], md_path: Path) -> None:
    """Compact markdown summary, one section per lead, sorted by fit_score desc."""
    def _fit(r: dict[str, Any]) -> int:
        s = r.get("score") or {}
        return int(s.get("fit_score") or 0)

    sorted_records = sorted(records, key=_fit, reverse=True)
    lines: list[str] = [
        f"# Pipeline run — {datetime.datetime.utcnow().isoformat()}Z",
        "",
        f"Total leads: **{len(records)}** · "
        f"ok: **{sum(1 for r in records if r.get('status') == 'ok')}** · "
        f"failed: **{sum(1 for r in records if r.get('status') == 'failed')}**",
        "",
    ]
    for r in sorted_records:
        if r.get("status") != "ok":
            lines.append(f"## ❌ {r['linkedin_url']}")
            lines.append(f"> {r.get('error', 'unknown error')}")
            lines.append("")
            continue
        profile = (r.get("enrichment") or {}).get("profile") or {}
        s = r.get("score") or {}
        drafts = r.get("drafts") or {}
        chosen = r.get("chosen_hook") or {}
        lines.append(
            f"## {s.get('fit_score', '?')} · {profile.get('full_name', '?')} — "
            f"{profile.get('headline', '')}"
        )
        lines.append(f"- {r['linkedin_url']}")
        if s.get("rationale"):
            lines.append(f"- rationale: _{s['rationale']}_")
        if chosen.get("reference"):
            lines.append(f"- hook: \"{chosen['reference']}\" ({chosen.get('signal_strength', '?')}/5)")
        lines.append("")
        for ch in ("linkedin_connect", "linkedin_dm", "email"):
            body = drafts.get(ch, "")
            if body:
                lines.append(f"### {ch} ({len(body)} chars)")
                lines.append("```")
                lines.append(body)
                lines.append("```")
                lines.append("")
        lines.append("---")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


@app.command()
def main(
    csv_path: Annotated[Path, typer.Argument(help="Path to a CSV with LinkedIn URLs.")],
    out: Annotated[
        Path,
        typer.Option(help="Output JSONL path. Defaults to runs/<date>.jsonl"),
    ] = None,  # type: ignore[assignment]
    url_column: Annotated[
        str | None,
        typer.Option(help="CSV column header for LinkedIn URLs. Auto-detected if omitted."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option(help="Cap on URLs processed this run (after dedup)."),
    ] = None,
    min_fit: Annotated[
        int,
        typer.Option(help="Drop records with fit_score below this (still written if --keep-all)."),
    ] = 0,
    keep_all: Annotated[
        bool,
        typer.Option("--keep-all", help="Write every processed record, even if below --min-fit."),
    ] = False,
    skip_existing: Annotated[
        bool,
        typer.Option(
            "--skip-existing",
            help="Don't re-process URLs already present in the output JSONL.",
        ),
    ] = False,
    skip_score: Annotated[
        bool,
        typer.Option("--skip-score", help="Skip the LLM ICP-fit scoring step."),
    ] = False,
    concurrency: Annotated[
        int,
        typer.Option(help="Parallel workers. Keep low (<= 4) to respect Unipile rate limits."),
    ] = 3,
    trigger: Annotated[
        str,
        typer.Option(
            help=(
                "Tag every record in this run with this trigger type. Use 'list' for cold "
                "sourcing (default), or a signal-mode value: profile_view | post_engagement "
                "| funding_event | new_role. Surfaces as a badge in the dashboard."
            ),
        ),
    ] = "list",
    campaign: Annotated[
        str | None,
        typer.Option(
            help=(
                "Campaign slug (or id) to target — selects the ICP + offer the whole run "
                "scores and drafts against. Omitted → the default campaign."
            ),
        ),
    ] = None,
) -> None:
    if trigger not in VALID_TRIGGERS:
        console.print(
            f"[red]Invalid --trigger '{trigger}'. Use one of: {sorted(VALID_TRIGGERS)}[/red]"
        )
        raise typer.Exit(2)
    if not csv_path.exists():
        console.print(f"[red]CSV not found:[/red] {csv_path}")
        raise typer.Exit(2)

    try:
        active_campaign = load_campaign(campaign)
    except (FileNotFoundError, RuntimeError) as e:
        console.print(f"[red]Couldn't load campaign '{campaign or 'default'}':[/red] {e}")
        raise typer.Exit(2) from e
    console.print(
        f"[dim]Campaign: [bold]{active_campaign.name}[/bold] ({active_campaign.slug})[/dim]"
    )

    out_path = out or Path("runs") / f"{datetime.date.today().isoformat()}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    urls = _read_urls(csv_path, url_column)
    if not urls:
        console.print("[yellow]No LinkedIn URLs found in CSV.[/yellow]")
        raise typer.Exit(1)
    console.print(f"[dim]Read {len(urls)} unique URLs from {csv_path}[/dim]")

    if skip_existing:
        already = _existing_urls(out_path)
        urls = [u for u in urls if u not in already]
        console.print(f"[dim]Skipping {len(already)} URLs already present in {out_path}[/dim]")

    if limit:
        urls = urls[:limit]
    console.print(f"[bold]Processing {len(urls)} URLs → {out_path}[/bold]")

    results: list[dict[str, Any]] = []
    with (
        out_path.open("a", encoding="utf-8") as out_file,
        Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
        ) as progress,
    ):
        task = progress.add_task("pipeline", total=len(urls))
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(
                    _process_one,
                    u,
                    skip_score=skip_score,
                    trigger=trigger,
                    campaign=active_campaign,
                ): u
                for u in urls
            }
            for fut in as_completed(futures):
                rec = fut.result()
                results.append(rec)
                fit = (rec.get("score") or {}).get("fit_score") or 0
                if keep_all or fit >= min_fit or rec.get("status") != "ok":
                    out_file.write(json.dumps(rec, default=str) + "\n")
                    out_file.flush()
                status = "ok" if rec.get("status") == "ok" else "[red]failed[/red]"
                progress.console.log(f"{status}  fit={fit:>3}  {futures[fut]}")
                progress.advance(task)

    md_path = out_path.with_suffix(".md")
    _write_md_summary(results, md_path)

    ok = sum(1 for r in results if r.get("status") == "ok")
    failed = len(results) - ok
    kept = sum(
        1
        for r in results
        if r.get("status") == "ok" and (r.get("score") or {}).get("fit_score", 0) >= min_fit
    )
    console.rule("[bold]Run summary")
    console.print(f"  processed:  {len(results)}")
    console.print(f"  succeeded:  {ok}")
    console.print(f"  failed:     {failed}")
    console.print(f"  ≥ min_fit:  {kept}")
    console.print(f"  jsonl:      {out_path}")
    console.print(f"  markdown:   {md_path}")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
