"""Phase 1.5 sender: read approved decisions, push to Heyreach.

Closes the loop the dashboard opens:

    dashboard /drafts review  →  /api/decisions  →  runs/decisions.jsonl
                                                          │
                                                          ▼
                                                  send_approvals.py
                                                          │
                                                          ▼
                                                    Heyreach API

For each approved LinkedIn decision, this script pushes the lead into the
campaign configured by env var (or --campaign-id flag) with the personalized
body delivered as a Heyreach custom field. Your Heyreach campaign template
should reference that field, e.g. `{{custom_body}}` in the message editor.

Idempotency: every successful push is appended to runs/sent.jsonl. On every
run we skip draft_ids already present there. Safe to re-run.

Usage:

    cd backend

    # one-time dry run — show what would be sent, no API calls
    uv run python -m scripts.send_approvals --dry-run

    # push linkedin_connect decisions to the default Heyreach campaign
    uv run python -m scripts.send_approvals --channel linkedin_connect

    # override campaign per channel
    uv run python -m scripts.send_approvals --channel linkedin_connect \\
        --campaign-id 12345

    # cap how many to push in one run (respect daily caps)
    uv run python -m scripts.send_approvals --channel linkedin_connect --limit 15
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from clients import heyreach
from config import BACKEND_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

RUNS_DIR = BACKEND_DIR / "runs"
DECISIONS_PATH = RUNS_DIR / "decisions.jsonl"
SENT_PATH = RUNS_DIR / "sent.jsonl"

# Heyreach LinkedIn channels we can push from this script.
LINKEDIN_CHANNELS = {"linkedin_connect", "linkedin_dm", "linkedin_followup_1", "linkedin_followup_2"}

# Daily safety caps (calibrated against Valley's published per-seat numbers).
# These are upper bounds for a single account on a single day; the script
# refuses to push more than this without --force.
DAILY_CAPS = {
    "linkedin_connect": 20,
    "linkedin_dm": 30,
    "linkedin_followup_1": 30,
    "linkedin_followup_2": 30,
}


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


def _append_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")


def _campaign_id_for(channel: str, override: str | None) -> str:
    if override:
        return override
    # Channel-specific env var wins, else the default.
    env_key = f"HEYREACH_CAMPAIGN_{channel.upper()}"
    return os.environ.get(env_key) or os.environ.get("HEYREACH_CAMPAIGN_DEFAULT") or ""


def _to_heyreach_lead(decision: dict[str, Any]) -> dict[str, Any]:
    """Map a decision record → Heyreach lead payload."""
    return {
        "linkedin_url": decision["linkedin_url"],
        "first_name": decision.get("first_name") or "",
        "last_name": decision.get("last_name") or "",
        "company_name": decision.get("company") or "",
        "custom_fields": {
            # Reference these in your Heyreach campaign message template:
            #   `{{custom_body}}` for the personalized message
            #   `{{custom_hook}}` for the anchor reference (optional)
            "custom_body": decision["body"],
            "custom_hook": decision.get("hook_reference") or "",
        },
    }


@app.command()
def main(
    channel: Annotated[
        str,
        typer.Option(
            "--channel",
            help="Which channel to send. e.g. linkedin_connect, linkedin_dm.",
        ),
    ] = "linkedin_connect",
    campaign_id: Annotated[
        str | None,
        typer.Option("--campaign-id", help="Heyreach campaign id override (else from env)."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Max leads to push this run (caps default to daily safety limit)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be sent. No API calls."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Allow exceeding the daily safety cap."),
    ] = False,
    decisions_path: Annotated[
        Path,
        typer.Option(help="Path to decisions JSONL."),
    ] = DECISIONS_PATH,
    sent_path: Annotated[
        Path,
        typer.Option(help="Path to sent JSONL (idempotency ledger)."),
    ] = SENT_PATH,
) -> None:
    if channel not in LINKEDIN_CHANNELS:
        console.print(
            f"[red]send_approvals.py only supports LinkedIn channels for now. Got: {channel}[/red]"
        )
        console.print(f"[dim]Supported: {sorted(LINKEDIN_CHANNELS)}[/dim]")
        raise typer.Exit(2)

    decisions = _read_jsonl(decisions_path)
    if not decisions:
        console.print(f"[yellow]No decisions found at {decisions_path}.[/yellow]")
        raise typer.Exit(1)

    sent_ledger = _read_jsonl(sent_path)
    sent_ids = {r.get("draft_id") for r in sent_ledger if r.get("draft_id")}

    # Filter: this channel, approved, not yet sent.
    queue = [
        d
        for d in decisions
        if d.get("channel") == channel
        and d.get("action") == "approve"
        and d.get("draft_id") not in sent_ids
    ]

    if not queue:
        console.print(f"[green]Nothing new to send for channel={channel}.[/green]")
        return

    # Apply safety cap unless --force.
    cap = DAILY_CAPS.get(channel, 50)
    effective_limit = limit if limit is not None else cap
    if not force and effective_limit > cap:
        console.print(
            f"[red]Limit {effective_limit} exceeds daily cap of {cap} for {channel}. "
            "Use --force to override.[/red]"
        )
        raise typer.Exit(2)
    queue = queue[:effective_limit]

    # Preview table
    table = Table(title=f"send_approvals · channel={channel} · {len(queue)} leads")
    table.add_column("#", style="dim", width=3)
    table.add_column("Lead")
    table.add_column("Company")
    table.add_column("Body preview", overflow="fold", max_width=60)
    for i, d in enumerate(queue, 1):
        body = d.get("body", "")
        table.add_row(
            str(i),
            d.get("full_name") or "?",
            d.get("company") or "?",
            (body[:80] + "…") if len(body) > 80 else body,
        )
    console.print(table)

    if dry_run:
        console.print("[bold yellow]Dry run — nothing sent.[/bold yellow]")
        return

    cid = _campaign_id_for(channel, campaign_id)
    if not cid:
        console.print(
            f"[red]No Heyreach campaign id configured. Set HEYREACH_CAMPAIGN_{channel.upper()} "
            "or HEYREACH_CAMPAIGN_DEFAULT, or pass --campaign-id.[/red]"
        )
        raise typer.Exit(2)

    # Push in batches of 50 (Heyreach's recommended max per request).
    BATCH = 50
    pushed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for start in range(0, len(queue), BATCH):
        batch = queue[start : start + BATCH]
        payload = [_to_heyreach_lead(d) for d in batch]
        try:
            response = heyreach.add_leads_to_campaign(cid, payload)
            console.print(
                f"[green]✓[/green] pushed {len(batch)} leads (Heyreach response: {response})"
            )
            now = datetime.now(UTC).isoformat()
            pushed.extend(
                {
                    "draft_id": d["draft_id"],
                    "lead_id": d.get("lead_id"),
                    "linkedin_url": d["linkedin_url"],
                    "channel": channel,
                    "campaign_id": cid,
                    "sent_at": now,
                }
                for d in batch
            )
        except Exception as e:  # noqa: BLE001 — script-level catch
            console.print(f"[red]✗ batch {start // BATCH + 1} failed: {e}[/red]")
            failed.extend(batch)

    if pushed:
        _append_jsonl(sent_path, pushed)

    console.rule("[bold]Send summary")
    console.print(f"  queued:  {len(queue)}")
    console.print(f"  sent:    [green]{len(pushed)}[/green]")
    console.print(f"  failed:  [red]{len(failed)}[/red]")
    console.print(f"  ledger:  {sent_path}")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
