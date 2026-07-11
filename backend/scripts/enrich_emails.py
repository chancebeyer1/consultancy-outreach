"""Email enrichment pass — PARKED in the Unipile re-architecture.

This step used to pull personal/work emails from ProxyCurl for approved
email-channel decisions. ProxyCurl was dropped to consolidate onto Unipile,
and Unipile is send/receive only — it does not discover email addresses.

So there is no email-finder wired up right now. The email *channel* still works:
`send_approvals.py --channel email` sends any decision that already carries an
`email` field (e.g. supplied in your source CSV, or added by hand). Decisions
without an email are skipped there, as before.

To re-enable automatic discovery, plug a dedicated finder (Apollo, Hunter,
Dropcontact, …) into this script: read the approved email-channel decisions,
look up an address per `linkedin_url`/name+company, and write an augmented
decisions file with `email` populated — the same shape send_approvals expects.

Usage (until a finder is added) just prints this notice.
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


@app.command()
def main() -> None:
    console.print(
        "[yellow]enrich_emails is parked.[/yellow] ProxyCurl was removed in the "
        "Unipile re-architecture and no email-finder is configured.\n\n"
        "The email channel still sends decisions that already have an [bold]email[/bold] "
        "field:\n  [bold]uv run python -m scripts.send_approvals --channel email[/bold]\n\n"
        "To restore automatic lookup, wire a finder (Apollo/Hunter/Dropcontact) into "
        "this file — see the module docstring."
    )
    raise typer.Exit(0)


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
