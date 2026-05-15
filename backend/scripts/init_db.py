"""One-shot DB initializer — applies db/schema.sql against DATABASE_URL.

Usage:

    cd backend
    uv sync --extra worker
    uv run python -m scripts.init_db
    uv run python -m scripts.init_db --check    # show what tables exist; don't apply
    uv run python -m scripts.init_db --drop     # DESTRUCTIVE: drop all tables first

Reads DATABASE_URL from .env. For Supabase, use the "Connection string"
from Settings → Database (the pooler URL works fine here).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from config import BACKEND_DIR, require

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

SCHEMA_PATH = BACKEND_DIR / "db" / "schema.sql"
TABLES = ["leads", "enrichments", "scores", "drafts", "sends", "replies", "campaigns", "sequence_state"]


def _connect():
    try:
        import psycopg
    except ImportError as e:
        raise RuntimeError(
            "psycopg not installed. Run: uv sync --extra worker"
        ) from e
    return psycopg.connect(require("DATABASE_URL"), autocommit=False)


@app.command()
def main(
    check: Annotated[bool, typer.Option("--check", help="Show which tables exist; don't apply schema.")] = False,
    drop: Annotated[bool, typer.Option("--drop", help="DESTRUCTIVE: drop all tables before applying.")] = False,
) -> None:
    if not SCHEMA_PATH.exists():
        console.print(f"[red]Schema not found:[/red] {SCHEMA_PATH}")
        raise typer.Exit(2)

    if check:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' order by table_name"
            )
            found = {row[0] for row in cur.fetchall()}
        console.rule("[bold]Existing tables")
        for t in TABLES:
            mark = "✅" if t in found else "—"
            console.print(f"  {mark}  {t}")
        extras = sorted(found - set(TABLES))
        if extras:
            console.print(f"\n[dim]Other tables in schema: {', '.join(extras)}[/dim]")
        return

    if drop:
        confirm = typer.confirm(
            "This will DROP ALL pipeline tables. Are you sure?", default=False
        )
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(1)
        conn = _connect()
        with conn.cursor() as cur:
            for t in reversed(TABLES):
                cur.execute(f'drop table if exists "{t}" cascade')
        conn.commit()
        console.print("[red]Dropped pipeline tables.[/red]")

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    console.print(f"[green]✓ Applied {SCHEMA_PATH.name} to DATABASE_URL.[/green]")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
