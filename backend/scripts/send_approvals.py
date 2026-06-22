"""Phase 1.5 sender: read approved decisions, send directly via Unipile.

Closes the loop the dashboard opens:

    dashboard /drafts review  →  /api/decisions  →  runs/decisions.jsonl
                                                          │
                                                          ▼
                                                  send_approvals.py
                                                          │
                                                          ▼
                                                     Unipile API

Unipile is a direct-messaging API (not a campaign queue), so we send the final
personalized `body` straight to the prospect — no template interpolation:

  * linkedin_connect              → users/invite  (connection request + note)
  * linkedin_dm / *_followup_*    → chats         (DM, starting/reusing the chat)
  * email / email_followup_*      → emails        (subject parsed from the draft)

Idempotency: every successful send is appended to runs/sent.jsonl. On every run
we skip draft_ids already present there. Safe to re-run.

Usage:

    cd backend

    # dry run — show what would be sent, no API calls
    uv run python -m scripts.send_approvals --dry-run

    # send approved linkedin_connect decisions
    uv run python -m scripts.send_approvals --channel linkedin_connect

    # cap how many to send in one run (still bounded by the rolling-window quota)
    uv run python -m scripts.send_approvals --channel linkedin_connect --limit 15
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

import sender_limits
from clients import unipile
from config import BACKEND_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

RUNS_DIR = BACKEND_DIR / "runs"
DECISIONS_PATH = RUNS_DIR / "decisions.jsonl"
SENT_PATH = RUNS_DIR / "sent.jsonl"

# Channels grouped by the Unipile call that delivers them.
LINKEDIN_CHANNELS = {"linkedin_connect", "linkedin_dm", "linkedin_followup_1", "linkedin_followup_2"}
EMAIL_CHANNELS = {"email", "email_followup_1", "email_followup_2"}
ALL_CHANNELS = LINKEDIN_CHANNELS | EMAIL_CHANNELS

# Send-rate caps + rolling-window enforcement live in sender_limits, shared with
# workers/sequence_send.py so both send paths honor one combined budget. Unipile
# does NOT enforce LinkedIn's limits — pacing is entirely on us.


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


def _parse_email_body(body: str) -> tuple[str, str]:
    """Split the email draft (which is `Subject: ...\\n\\n<body>`) into
    (subject, body). Falls back to ("", body) if no subject line is present."""
    if body.lower().startswith("subject:"):
        first, _, rest = body.partition("\n")
        return first.split(":", 1)[1].strip(), rest.lstrip("\n")
    return "", body


def _external_id(resp: Any) -> str | None:
    """Best-effort extraction of Unipile's message/invite id for sends.external_id."""
    if not isinstance(resp, dict):
        return None
    for key in ("message_id", "invitation_id", "id", "chat_id", "tracking_id", "provider_id"):
        val = resp.get(key)
        if val:
            return str(val)
    return None


def _send_one(decision: dict[str, Any]) -> dict[str, Any]:
    """Deliver one approved decision via the right Unipile call.

    Returns the raw Unipile response dict. Raises on transport/API failure
    (caught by the caller, which records the decision as failed).
    """
    channel = decision["channel"]
    body = decision.get("body") or ""

    if channel in EMAIL_CHANNELS:
        subject, email_body = _parse_email_body(body)
        return unipile.send_email(
            decision["email"],
            subject or "Quick question",
            email_body,
            display_name=decision.get("full_name") or None,
        )

    # LinkedIn: resolve the provider-internal id from the profile URL, then either
    # invite (with a note) or DM (starting/reusing the chat).
    provider_id = unipile.resolve_provider_id(decision["linkedin_url"])
    if channel == "linkedin_connect":
        return unipile.send_linkedin_invitation(
            provider_id, body, user_email=decision.get("email") or None
        )
    return unipile.send_linkedin_message(provider_id, body)


@app.command()
def main(
    channel: Annotated[
        str,
        typer.Option(
            "--channel",
            help="Which channel to send. e.g. linkedin_connect, linkedin_dm, email.",
        ),
    ] = "linkedin_connect",
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Max leads to send this run (defaults to remaining rolling-window quota)."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be sent. No API calls."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Bypass the rolling-window safety cap."),
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
    if channel not in ALL_CHANNELS:
        console.print(f"[red]Unsupported channel: {channel}[/red]")
        console.print(f"[dim]Supported: {sorted(ALL_CHANNELS)}[/dim]")
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

    # Apply the rolling-window safety cap (trailing 24h + 7d, counted across both
    # send paths and de-duplicated by draft_id) unless --force. See sender_limits.
    q = sender_limits.quota(channel)
    console.print(
        f"[dim]quota {channel}: {q.describe()} → {q.allowed} left ({q.binding} cap)[/dim]"
    )
    if force:
        effective_limit = limit if limit is not None else len(queue)
    elif q.allowed <= 0:
        console.print(
            f"[yellow]{channel}: quota exhausted — wait for the rolling window to "
            "free up, or use --force.[/yellow]"
        )
        return
    elif limit is not None and limit > q.allowed:
        console.print(
            f"[red]{channel}: requested {limit} but only {q.allowed} left "
            f"({q.binding} cap). Use --force to override.[/red]"
        )
        raise typer.Exit(2)
    else:
        effective_limit = min(limit, q.allowed) if limit is not None else q.allowed
    queue = queue[: max(0, effective_limit)]

    is_email = channel in EMAIL_CHANNELS

    # For email, every queued decision needs an email field. Drop those that
    # don't and warn the operator to run enrich_emails first.
    if is_email:
        missing_emails = [d for d in queue if not d.get("email")]
        queue = [d for d in queue if d.get("email")]
        if missing_emails:
            console.print(
                f"[yellow]Skipping {len(missing_emails)} email decisions without an `email` field. "
                "Run: uv run python -m scripts.enrich_emails[/yellow]"
            )
        if not queue:
            console.print("[yellow]Nothing left to send after email check.[/yellow]")
            return

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

    # Send one at a time — Unipile is per-message, not a batch campaign push.
    pushed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    paused = False
    for d in queue:
        try:
            resp = _send_one(d)
            now = datetime.now(UTC).isoformat()
            pushed.append(
                {
                    "draft_id": d["draft_id"],
                    "lead_id": d.get("lead_id"),
                    "linkedin_url": d.get("linkedin_url"),
                    "email": d.get("email"),
                    "channel": channel,
                    "provider": "unipile",
                    "external_id": _external_id(resp),
                    "sent_at": now,
                }
            )
            console.print(f"[green]✓[/green] sent {channel} → {d.get('full_name') or d.get('linkedin_url')}")
        except Exception as e:  # noqa: BLE001 — script-level catch
            if sender_limits.is_invite_limit_error(e):
                console.print(
                    "[bold red]LinkedIn invite limit hit (422 cannot_resend_yet). "
                    "Pausing — unsent leads stay queued for the next run.[/bold red]"
                )
                paused = True
                break
            console.print(f"[red]✗ {d.get('full_name') or d.get('linkedin_url')}: {e}[/red]")
            failed.append(d)

    if pushed:
        _append_jsonl(sent_path, pushed)

    console.rule("[bold]Send summary")
    console.print(f"  queued:  {len(queue)}")
    console.print(f"  sent:    [green]{len(pushed)}[/green]")
    console.print(f"  failed:  [red]{len(failed)}[/red]")
    if paused:
        console.print("  status:  [bold yellow]paused (LinkedIn invite limit)[/bold yellow]")
    console.print(f"  ledger:  {sent_path}")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
