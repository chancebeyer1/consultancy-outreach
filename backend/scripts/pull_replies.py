"""Local reply puller (fallback to the Modal webhook/cron).

Polls Unipile (LinkedIn chats + email), finds new inbound messages, classifies
each via prompts/reply_classify.md, and appends a structured record to
`runs/replies.jsonl` for the dashboard's /replies page to read.

Idempotent: every classified reply is keyed by its Unipile message id
(or a content hash if Unipile omits one). A ledger at `runs/replies-seen.jsonl`
records what we've already processed so re-runs are cheap.

Usage:

    cd backend

    # one-time: dry-run shows what would be classified
    uv run python -m scripts.pull_replies --dry-run

    # poll inbox, classify new replies
    uv run python -m scripts.pull_replies

    # cap how many conversations to scan in one pass
    uv run python -m scripts.pull_replies --limit 50

In production the Modal `unipile_webhook` (near-real-time) + hourly
`pull_replies_cron` cover this; run it here manually for ad-hoc local checks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from config import BACKEND_DIR
from workers.replies import fetch_and_classify_new_replies

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

RUNS_DIR = BACKEND_DIR / "runs"
REPLIES_PATH = RUNS_DIR / "replies.jsonl"
SEEN_PATH = RUNS_DIR / "replies-seen.jsonl"


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


def _append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")


@app.command()
def main(
    limit: Annotated[
        int,
        typer.Option(help="Max conversations to scan per run."),
    ] = 100,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Fetch + classify but don't write to disk."),
    ] = False,
    include_read: Annotated[
        bool,
        typer.Option("--include-read", help="Also scan conversations with no unread count."),
    ] = False,
) -> None:
    # Load idempotency ledger
    seen_records = _read_jsonl(SEEN_PATH)
    seen_ids = {r.get("message_id") for r in seen_records if r.get("message_id")}

    all_new = fetch_and_classify_new_replies(
        seen_message_ids=seen_ids,
        limit=limit,
        only_with_unread=not include_read,
    )

    if not all_new:
        console.print("[green]No new replies since last run.[/green]")
        return

    # Preview
    table = Table(title=f"New replies · {len(all_new)}")
    table.add_column("intent", style="bold")
    table.add_column("lead")
    table.add_column("body", overflow="fold", max_width=60)
    table.add_column("suggested", overflow="fold", max_width=40)
    for r in all_new:
        intent = r.get("intent") or "?"
        color = {
            "interested": "[green]",
            "objection": "[yellow]",
            "unsubscribe": "[red]",
            "oof": "[dim]",
        }.get(intent, "")
        table.add_row(
            f"{color}{intent}",
            r.get("lead_name") or "?",
            r.get("body") or "",
            (r.get("suggested_reply") or "")[:120],
        )
    console.print(table)

    if dry_run:
        console.print("[bold yellow]Dry run — nothing written.[/bold yellow]")
        return

    _append_jsonl(REPLIES_PATH, all_new)
    _append_jsonl(SEEN_PATH, [{"message_id": r["message_id"]} for r in all_new])

    console.rule("[bold]Triage summary")
    intents: dict[str, int] = {}
    for r in all_new:
        intents[r.get("intent") or "?"] = intents.get(r.get("intent") or "?", 0) + 1
    for k, v in sorted(intents.items(), key=lambda kv: -kv[1]):
        console.print(f"  {k:<14} {v}")
    console.print(f"\n  replies.jsonl: {REPLIES_PATH}")
    console.print(f"  ledger:        {SEEN_PATH}")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
