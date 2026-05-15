"""Email enrichment pass for approved email decisions.

The default enrich step (run_pipeline.py) skips personal_email to keep
per-lead cost down. Once you've approved an email draft in the dashboard
and need to actually send it, this script pulls personal_email for those
specific LinkedIn URLs and produces an augmented decisions file with
`email` populated, ready for send_approvals.py to push to Smartlead.

Usage:

    cd backend

    # default in/out paths
    uv run python -m scripts.enrich_emails

    # explicit
    uv run python -m scripts.enrich_emails \\
        --decisions runs/decisions.jsonl \\
        --out runs/decisions-with-emails.jsonl

The output file is decisions.jsonl-shaped — same records, with an `email`
field added to every approved email-channel row. Rows without a discoverable
email get `email: null`; send_approvals.py will skip those.
"""

from __future__ import annotations

import json
import sys
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from clients import proxycurl
from config import BACKEND_DIR

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

EMAIL_CHANNELS = {"email", "email_followup_1", "email_followup_2"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")


def _best_email(profile: dict[str, Any]) -> str | None:
    """ProxyCurl returns personal_emails + work_emails arrays when included.
    Prefer work email; fall back to personal."""
    for key in ("work_email", "extra"):
        v = profile.get(key)
        if isinstance(v, str) and "@" in v:
            return v
        if isinstance(v, dict) and v.get("work_email"):
            return v["work_email"]
    work_emails = profile.get("work_emails") or (profile.get("extra") or {}).get("work_emails")
    if work_emails:
        return work_emails[0]
    personal = profile.get("personal_emails") or (profile.get("extra") or {}).get("personal_emails")
    if personal:
        return personal[0]
    return None


@app.command()
def main(
    decisions: Annotated[
        Path,
        typer.Option(help="Path to decisions JSONL."),
    ] = BACKEND_DIR / "runs" / "decisions.jsonl",
    out: Annotated[
        Path,
        typer.Option(help="Output path for enriched decisions."),
    ] = BACKEND_DIR / "runs" / "decisions-with-emails.jsonl",
) -> None:
    records = _read_jsonl(decisions)
    if not records:
        console.print(f"[yellow]No decisions found at {decisions}.[/yellow]")
        raise typer.Exit(1)

    # Group: rows we need to enrich vs rows we pass through.
    to_enrich_urls: dict[str, list[int]] = {}  # linkedin_url -> indices
    for i, r in enumerate(records):
        if (
            r.get("action") == "approve"
            and r.get("channel") in EMAIL_CHANNELS
            and r.get("linkedin_url")
            and not r.get("email")
        ):
            to_enrich_urls.setdefault(r["linkedin_url"], []).append(i)

    if not to_enrich_urls:
        console.print("[green]Nothing to enrich — every approved email row already has an email.[/green]")
        _write_jsonl(out, records)
        console.print(f"  copied to: {out}")
        return

    console.rule(f"[bold cyan]Enrich · {len(to_enrich_urls)} unique URL(s)")
    enriched_emails: dict[str, str | None] = {}
    failed: list[str] = []

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("enriching", total=len(to_enrich_urls))
        for url in to_enrich_urls:
            try:
                profile = proxycurl.fetch_profile(url, with_email=True)
                email = _best_email(profile)
                enriched_emails[url] = email
                marker = "✓" if email else "—"
                progress.console.log(f"{marker} {url} → {email or '(no email)'}")
            except Exception as e:  # noqa: BLE001
                failed.append(url)
                progress.console.log(f"[red]✗ {url} — {e}[/red]")
            progress.advance(task)

    # Write augmented records
    for url, indices in to_enrich_urls.items():
        email = enriched_emails.get(url)
        for i in indices:
            records[i]["email"] = email
    _write_jsonl(out, records)

    found = sum(1 for v in enriched_emails.values() if v)
    console.rule("[bold]Done")
    console.print(f"  URLs scanned:    {len(to_enrich_urls)}")
    console.print(f"  emails found:    [green]{found}[/green]")
    console.print(f"  no email:        [yellow]{len(to_enrich_urls) - found - len(failed)}[/yellow]")
    console.print(f"  failed:          [red]{len(failed)}[/red]")
    console.print(f"  output:          {out}")
    console.print(
        f"\n[dim]Next:[/dim] [bold]uv run python -m scripts.send_approvals "
        f"--channel email --decisions-path {out}[/bold]"
    )


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
