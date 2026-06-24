"""Import sending mailboxes from a provider CSV into the `mailboxes` table.

Reads credentials from the CSV FILE (never the command line) and upserts by email, so
re-running refreshes hosts/passwords without disturbing warmup progress (status /
daily_cap / ramp_started_at are preserved on conflict). Supports Maildoso / Instantly
-style exports (email, imap_*, smtp_* columns).

Usage:
    cd backend
    uv run python -m scripts.import_mailboxes --csv "C:/path/accounts.csv" --provider maildoso
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import require

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


def _col(row: dict, *names: str) -> str | None:
    for n in names:
        v = (row.get(n) or "").strip()
        if v:
            return v
    return None


@app.command()
def main(
    csv_path: Annotated[Path, typer.Option("--csv", help="Path to the provider CSV export.")],
    provider: Annotated[str, typer.Option(help="Provider tag stored on each box.")] = "maildoso",
    start_cap: Annotated[int, typer.Option(help="Initial per-day cold-send cap (warmup).")] = 5,
    from_name: Annotated[str | None, typer.Option(help="Override the From display name.")] = None,
) -> None:
    if not csv_path.exists():
        console.print(f"[red]CSV not found:[/red] {csv_path}")
        raise typer.Exit(2)

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    if not rows:
        console.print("[yellow]No rows in CSV.[/yellow]")
        raise typer.Exit(1)

    import psycopg

    inserted = updated = 0
    conn = psycopg.connect(require("DATABASE_URL"))
    table = Table(title="mailboxes imported")
    table.add_column("email")
    table.add_column("domain")
    table.add_column("smtp")
    table.add_column("imap")
    try:
        with conn:
            with conn.cursor() as cur:
                for r in rows:
                    email = _col(r, "email", "smtp_username", "imap_username")
                    if not email:
                        continue
                    fn = from_name or " ".join(
                        x for x in (_col(r, "first_name"), _col(r, "last_name")) if x
                    ) or None
                    domain = email.split("@")[-1]
                    cur.execute("select id from mailboxes where email = %s", (email,))
                    exists = cur.fetchone() is not None
                    cur.execute(
                        """
                        insert into mailboxes
                            (email, provider, from_name, domain, smtp_host, smtp_port,
                             imap_host, imap_port, username, app_password,
                             status, daily_cap, ramp_started_at)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'warming',%s, current_date)
                        on conflict (email) do update set
                            provider     = excluded.provider,
                            from_name    = excluded.from_name,
                            domain       = excluded.domain,
                            smtp_host    = excluded.smtp_host,
                            smtp_port    = excluded.smtp_port,
                            imap_host    = excluded.imap_host,
                            imap_port    = excluded.imap_port,
                            username     = excluded.username,
                            app_password = excluded.app_password,
                            updated_at   = now()
                        """,
                        (
                            email, provider, fn, domain,
                            _col(r, "smtp_host"), int(_col(r, "smtp_port") or 587),
                            _col(r, "imap_host"), int(_col(r, "imap_port") or 993),
                            _col(r, "smtp_username", "email"),
                            _col(r, "smtp_password", "imap_password"),
                            start_cap,
                        ),
                    )
                    updated += exists
                    inserted += not exists
                    table.add_row(email, domain, _col(r, "smtp_host") or "", _col(r, "imap_host") or "")
    finally:
        conn.close()

    console.print(table)
    console.print(f"[green]Done[/green] — {inserted} inserted, {updated} updated.")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
