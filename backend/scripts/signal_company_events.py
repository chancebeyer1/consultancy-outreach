"""Signal-mode filter: scan a candidate list, keep only companies with fresh
company-level signals (funding, AI hiring, press), drop the rest.

Cheap way to convert a cold list into a warm one without LinkedIn scraping.
Hits Tavily for each unique company in the input CSV; keeps prospects whose
company has at least one fresh-looking signal hit.

Usage:

    cd backend

    # input.csv needs `linkedin_url` and `company` columns
    uv run python -m scripts.signal_company_events input.csv

    # write to a specific path
    uv run python -m scripts.signal_company_events input.csv \\
        --out runs/funded-2026-05.csv

    # only flag funding events (drop hiring + press)
    uv run python -m scripts.signal_company_events input.csv --signals funding

    # then ingest the filtered CSV with the right trigger tag:
    uv run python -m scripts.run_pipeline runs/funded-2026-05.csv \\
        --trigger funding_event

This script does NOT enrich profiles or generate drafts (it stays cheap so
you can scan thousands of companies a week). It's a pre-filter: feed the
output into run_pipeline.py for the expensive per-lead steps.
"""

from __future__ import annotations

import csv
import datetime
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from clients import tavily
from config import BACKEND_DIR

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

# Signal bucket → keywords we count as a "fresh" hit (excludes generic title hits).
FRESH_KEYWORDS = {
    "funding": [
        "raises ",
        "raised ",
        "seed round",
        "series a",
        "series b",
        "series c",
        "announces funding",
        "announces $",
        "secures $",
    ],
    "hiring": [
        "hiring ai",
        "hiring agent",
        "hiring engineer",
        "we're hiring",
        "we are hiring",
        "now hiring",
    ],
    "press": [
        "announces ",
        "launches ",
        "unveils ",
        "introduces ",
        "case study",
    ],
}

# Signal bucket → run_pipeline.py --trigger value to use downstream.
TRIGGER_HINT = {
    "funding": "funding_event",
    "hiring": "list",  # No dedicated enum; flag as a strong-signal cold list lead
    "press": "list",
}


def _detect_columns(header: list[str]) -> tuple[str | None, str | None]:
    """Find (linkedin_url, company) columns in arbitrary CSV exports."""
    url_col = next(
        (c for c in header if "linkedin" in c.lower() or c.lower() == "url"),
        None,
    )
    company_col = next(
        (c for c in header if "company" in c.lower() or "organization" in c.lower()),
        None,
    )
    return url_col, company_col


def _read_input(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise typer.BadParameter(f"CSV {path} has no header row")
        url_col, company_col = _detect_columns(reader.fieldnames)
        if not url_col:
            raise typer.BadParameter(
                f"CSV needs a linkedin/url column. Got: {reader.fieldnames}"
            )
        if not company_col:
            raise typer.BadParameter(
                f"CSV needs a company column. Got: {reader.fieldnames}"
            )
        rows: list[dict[str, str]] = []
        for row in reader:
            url = (row.get(url_col) or "").strip()
            company = (row.get(company_col) or "").strip()
            if url and company and "linkedin.com/in/" in url:
                rows.append({"linkedin_url": url, "company": company, **row})
        return rows


def _classify_company(company: str, signals: list[str]) -> dict[str, Any]:
    """Run Tavily for one company; classify into fresh signal buckets."""
    out = {"company": company, "hits": {}, "any_fresh": False, "strongest": None}
    try:
        result = tavily.company_signals(company)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        return out

    bucket_hits: dict[str, list[str]] = defaultdict(list)
    for bucket, entries in result.items():
        if bucket not in signals:
            continue
        for entry in entries:
            title = (entry.get("title") or "").lower()
            snippet = (entry.get("content") or "").lower()
            blob = f"{title} {snippet}"
            keywords = FRESH_KEYWORDS.get(bucket, [])
            if any(k in blob for k in keywords):
                bucket_hits[bucket].append(entry.get("title") or "")

    out["hits"] = dict(bucket_hits)
    out["any_fresh"] = any(bucket_hits.values())
    if bucket_hits:
        # Strongest: funding > hiring > press
        for b in ("funding", "hiring", "press"):
            if bucket_hits.get(b):
                out["strongest"] = b
                break
    return out


def _write_output_csv(
    matched_rows: list[dict[str, Any]],
    classifications: dict[str, dict[str, Any]],
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["linkedin_url", "company", "signal_type", "signal_summary"])
        for row in matched_rows:
            cls = classifications[row["company"]]
            summary_parts: list[str] = []
            for bucket, titles in cls["hits"].items():
                for t in titles[:2]:
                    summary_parts.append(f"[{bucket}] {t}")
            writer.writerow(
                [
                    row["linkedin_url"],
                    row["company"],
                    cls["strongest"] or "",
                    " | ".join(summary_parts),
                ]
            )


def _write_md_report(
    classifications: dict[str, dict[str, Any]],
    md_path: Path,
    total_input: int,
) -> None:
    fresh = [c for c in classifications.values() if c["any_fresh"]]
    md_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Signal scan — {datetime.datetime.utcnow().isoformat()}Z",
        "",
        f"Scanned: **{len(classifications)}** unique companies "
        f"({total_input} rows). Fresh signals: **{len(fresh)}**.",
        "",
    ]
    # Group by strongest bucket
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in fresh:
        by_bucket[c["strongest"] or "other"].append(c)
    for bucket in ("funding", "hiring", "press", "other"):
        items = by_bucket.get(bucket) or []
        if not items:
            continue
        lines.append(f"## {bucket} ({len(items)})")
        for c in items:
            lines.append(f"- **{c['company']}**")
            for b, titles in c["hits"].items():
                for t in titles[:2]:
                    lines.append(f"  - _{b}_ — {t}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


@app.command()
def main(
    csv_path: Annotated[Path, typer.Argument(help="Path to a CSV with linkedin_url + company columns.")],
    out: Annotated[
        Path | None,
        typer.Option(help="Output CSV path. Default: runs/signals-<date>.csv"),
    ] = None,
    signals: Annotated[
        str,
        typer.Option(
            help="Which buckets to scan, comma-separated: funding,hiring,press."
        ),
    ] = "funding,hiring,press",
    concurrency: Annotated[
        int,
        typer.Option(help="Parallel Tavily queries. Keep low; Tavily rate-limits."),
    ] = 5,
) -> None:
    if not csv_path.exists():
        console.print(f"[red]CSV not found:[/red] {csv_path}")
        raise typer.Exit(2)

    signal_buckets = {s.strip() for s in signals.split(",") if s.strip()}
    invalid = signal_buckets - set(FRESH_KEYWORDS.keys())
    if invalid:
        console.print(
            f"[red]Unknown signal bucket(s): {sorted(invalid)}. "
            f"Valid: {sorted(FRESH_KEYWORDS.keys())}[/red]"
        )
        raise typer.Exit(2)

    rows = _read_input(csv_path)
    if not rows:
        console.print("[yellow]No rows with valid linkedin + company found.[/yellow]")
        raise typer.Exit(1)

    unique_companies = sorted({r["company"] for r in rows})
    console.print(
        f"[dim]Input: {len(rows)} rows, {len(unique_companies)} unique companies. "
        f"Buckets: {sorted(signal_buckets)}[/dim]"
    )

    classifications: dict[str, dict[str, Any]] = {}
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("scanning", total=len(unique_companies))
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {
                pool.submit(_classify_company, c, signal_buckets): c
                for c in unique_companies
            }
            for fut in as_completed(futures):
                company = futures[fut]
                cls = fut.result()
                classifications[company] = cls
                marker = "🔥" if cls["any_fresh"] else "—"
                progress.console.log(f"{marker} {company} ({cls.get('strongest') or 'cold'})")
                progress.advance(task)

    matched = [r for r in rows if classifications[r["company"]]["any_fresh"]]
    out_path = out or BACKEND_DIR / "runs" / f"signals-{datetime.date.today().isoformat()}.csv"
    _write_output_csv(matched, classifications, out_path)
    md_path = out_path.with_suffix(".md")
    _write_md_report(classifications, md_path, total_input=len(rows))

    # Side car: raw classifications for debugging.
    debug_path = out_path.with_suffix(".debug.json")
    debug_path.write_text(
        json.dumps(classifications, default=str, indent=2), encoding="utf-8"
    )

    table = Table(title="Scan summary", show_lines=False)
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("input rows", str(len(rows)))
    table.add_row("unique companies", str(len(unique_companies)))
    table.add_row("fresh-signal companies", str(sum(1 for c in classifications.values() if c["any_fresh"])))
    table.add_row("rows kept", str(len(matched)))
    console.print(table)
    console.print(f"  csv:    {out_path}")
    console.print(f"  report: {md_path}")
    console.print(f"  debug:  {debug_path}")
    console.print(
        "\n[dim]Next: pipe the CSV into run_pipeline with the matching trigger.[/dim]"
    )
    console.print(
        f"  [bold]uv run python -m scripts.run_pipeline {out_path} --trigger funding_event[/bold]"
    )


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
