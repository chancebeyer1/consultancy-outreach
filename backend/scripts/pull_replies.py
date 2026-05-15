"""Phase 2 reply puller.

Polls Heyreach's inbox, finds new inbound messages, classifies each via
prompts/reply_classify.md, and appends a structured record to
`runs/replies.jsonl` for the dashboard's /replies page to read.

Idempotent: every classified reply is keyed by its Heyreach message id
(or a hash if Heyreach omits one). A ledger at `runs/replies-seen.jsonl`
records what we've already processed so re-runs are cheap.

Usage:

    cd backend

    # one-time: dry-run shows what would be classified
    uv run python -m scripts.pull_replies --dry-run

    # poll inbox, classify new replies
    uv run python -m scripts.pull_replies

    # cap how many conversations to scan in one pass
    uv run python -m scripts.pull_replies --limit 50

    # restrict to one campaign
    uv run python -m scripts.pull_replies --campaign-id 12345

You probably want to run this on a cron (every 15 min). For now, run it
manually from your laptop after each batch of sends.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from clients import heyreach
from config import BACKEND_DIR
from workers import reply_triage

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


def _message_id(msg: dict[str, Any]) -> str:
    """Stable id per message. Falls back to a content+timestamp hash if
    Heyreach doesn't return one."""
    mid = msg.get("id") or msg.get("messageId")
    if mid:
        return str(mid)
    blob = f"{msg.get('sentAt')}|{msg.get('body', '')[:200]}".encode()
    return hashlib.sha1(blob).hexdigest()[:16]


def _find_last_outbound(messages: list[dict[str, Any]], before_idx: int) -> str | None:
    """Walk backward from a reply to find the most recent outbound we sent.

    Used as the `original_message` context for the classifier prompt.
    """
    for i in range(before_idx - 1, -1, -1):
        m = messages[i]
        if (m.get("direction") or "").lower() == "outbound":
            return m.get("body")
    return None


def _process_conversation(
    convo: dict[str, Any],
    seen_ids: set[str],
) -> list[dict[str, Any]]:
    """Fetch messages for one conversation, classify any new inbound replies.

    Returns the list of new reply records (each ready to write to JSONL).
    """
    convo_id = str(convo.get("id") or convo.get("conversationId") or "")
    if not convo_id:
        return []

    messages = heyreach.list_conversation_messages(convo_id)
    new_records: list[dict[str, Any]] = []

    for idx, msg in enumerate(messages):
        if (msg.get("direction") or "").lower() != "inbound":
            continue
        mid = _message_id(msg)
        if mid in seen_ids:
            continue

        reply_body = msg.get("body") or ""
        original = _find_last_outbound(messages, idx)

        try:
            classification = reply_triage.classify_reply(
                reply_body=reply_body,
                original_message=original,
                lead_name=convo.get("firstName")
                or (convo.get("leadName") if "leadName" in convo else None),
                lead_role=convo.get("role"),
                lead_company=convo.get("companyName") or convo.get("company"),
            )
        except Exception as e:  # noqa: BLE001
            console.print(f"[yellow]classifier failed on {mid}: {e}[/yellow]")
            continue

        new_records.append(
            {
                "message_id": mid,
                "conversation_id": convo_id,
                "linkedin_url": convo.get("leadLinkedinUrl") or convo.get("linkedinUrl"),
                "lead_name": convo.get("firstName"),
                "lead_company": convo.get("companyName") or convo.get("company"),
                "campaign_id": convo.get("campaignId"),
                "channel": "linkedin_dm",  # Heyreach inbox is LinkedIn DM today
                "body": reply_body,
                "original_message": original,
                "received_at": msg.get("sentAt") or datetime.now(UTC).isoformat(),
                "classified_at": datetime.now(UTC).isoformat(),
                "intent": classification.get("intent"),
                "sentiment": classification.get("sentiment"),
                "summary": classification.get("summary"),
                "suggested_reply": classification.get("suggested_reply"),
                "next_action": classification.get("next_action"),
            }
        )

    return new_records


@app.command()
def main(
    limit: Annotated[
        int,
        typer.Option(help="Max conversations to scan per run."),
    ] = 100,
    campaign_id: Annotated[
        str | None,
        typer.Option(help="Restrict to one Heyreach campaign."),
    ] = None,
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

    payload = heyreach.list_inbox_conversations(
        limit=limit,
        only_with_unread=not include_read,
        campaign_ids=[campaign_id] if campaign_id else None,
    )
    conversations = payload.get("items") or payload.get("conversations") or []

    if not conversations:
        console.print("[green]Inbox quiet — nothing to triage.[/green]")
        return

    console.print(f"[dim]Scanning {len(conversations)} conversation(s)…[/dim]")

    all_new: list[dict[str, Any]] = []
    for convo in conversations:
        new_records = _process_conversation(convo, seen_ids)
        for r in new_records:
            seen_ids.add(r["message_id"])
        all_new.extend(new_records)

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
