"""Sync campaign persona files → the `campaigns` DB table (the file→DB bridge).

`backend/campaigns/<slug>/` (icp.md, offer.md, optional style.md / voice.md, and
campaign.toml) is the *versioned seed*; this script upserts each folder into
Postgres by `slug`, which is the *runtime source of truth* the pipeline and
dashboard read. Run it after editing campaign files; the dashboard writes
straight to the DB, so files are the seed/backup you re-sync from.

Omitted optional fields are written as NULL so they fall back to the global
defaults at read time:
  - style_md / voice_md  → prompts/style.md, prompts/voice_corpus.md
  - landing_url / calcom_url → LANDING_URL / CALCOM_URL in .env

Usage:

    cd backend
    uv run python -m scripts.sync_campaigns            # upsert all folders
    uv run python -m scripts.sync_campaigns --dry-run  # show plan, write nothing
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from campaigns_loader import CAMPAIGNS_DIR
from config import require

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()

# Columns written on every upsert (is_default handled separately to honor the
# single-default unique index).
_WRITE_COLS = [
    "name",
    "icp_md",
    "offer_md",
    "style_md",
    "voice_md",
    "landing_url",
    "calcom_url",
    "search_url",
    "search_params",
    "apollo_params",
    "channels",
    "auto_send",
    "inmail_min_fit",
    "status",
]


def _read_optional(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def _read_campaign_dir(folder: Path) -> dict | None:
    """Read one campaign folder into a raw column dict (None for omitted fields).

    Returns None (skips the folder) if it lacks campaign.toml or the required
    icp.md / offer.md.
    """
    toml_path = folder / "campaign.toml"
    icp = _read_optional(folder / "icp.md")
    offer = _read_optional(folder / "offer.md")
    if not toml_path.exists() or icp is None or offer is None:
        return None

    meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    slug = meta.get("slug") or folder.name
    # Optional structured search filters (Sales-Navigator). A sidecar JSON file keeps the
    # nested filter object readable/versioned; the replenish worker prefers it over search_url.
    search_json = folder / "search.json"
    search_params = (
        json.loads(search_json.read_text(encoding="utf-8")) if search_json.exists() else None
    )
    apollo_json = folder / "apollo.json"  # Apollo email-sourcing filters (title/seniority/size)
    apollo_params = (
        json.loads(apollo_json.read_text(encoding="utf-8")) if apollo_json.exists() else None
    )
    return {
        "slug": slug,
        "name": meta.get("name") or slug,
        "icp_md": icp,
        "offer_md": offer,
        "style_md": _read_optional(folder / "style.md"),
        "voice_md": _read_optional(folder / "voice.md")
        or _read_optional(folder / "voice_corpus.md"),
        "landing_url": meta.get("landing_url"),  # None → falls back to .env at read time
        "calcom_url": meta.get("calcom_url"),
        "search_url": meta.get("search_url"),
        "search_params": search_params,  # dict | None → Postgres jsonb
        "apollo_params": apollo_params,  # dict | None → Postgres jsonb
        "channels": meta.get("channels"),  # list[str] | None → Postgres text[]
        "auto_send": bool(meta.get("auto_send", False)),
        "inmail_min_fit": meta.get("inmail_min_fit"),
        "is_default": bool(meta.get("is_default", False)),
        "status": meta.get("status") or "active",
    }


def _discover() -> list[dict]:
    if not CAMPAIGNS_DIR.is_dir():
        return []
    out: list[dict] = []
    for folder in sorted(CAMPAIGNS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        rec = _read_campaign_dir(folder)
        if rec:
            out.append(rec)
    return out


@app.command()
def main(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would change; write nothing."),
    ] = False,
) -> None:
    campaigns = _discover()
    if not campaigns:
        console.print(f"[yellow]No campaign folders found under {CAMPAIGNS_DIR}.[/yellow]")
        raise typer.Exit(1)

    defaults = [c["slug"] for c in campaigns if c["is_default"]]
    if len(defaults) > 1:
        console.print(
            f"[yellow]Multiple campaigns marked is_default ({defaults}); "
            f"using '{defaults[0]}'.[/yellow]"
        )
    default_slug = defaults[0] if defaults else None

    table = Table(title="campaigns → DB")
    table.add_column("slug", style="bold")
    table.add_column("name")
    table.add_column("default", justify="center")
    table.add_column("overrides")
    table.add_column("landing_url")
    for c in campaigns:
        overrides = ", ".join(k for k in ("style", "voice") if c[f"{k}_md"]) or "—"
        table.add_row(
            c["slug"],
            c["name"],
            "★" if c["slug"] == default_slug else "",
            overrides,
            c["landing_url"] or "[dim](.env)[/dim]",
        )
    console.print(table)

    if dry_run:
        console.print("[dim]--dry-run: no DB writes.[/dim]")
        return

    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e

    def vals(c: dict) -> list:
        # search_params is jsonb — wrap the dict so psycopg adapts it; everything else passes through.
        return [
            Jsonb(c[col]) if col in ("search_params", "apollo_params") and c[col] is not None else c[col]
            for col in _WRITE_COLS
        ]

    inserted = updated = 0
    conn = psycopg.connect(require("DATABASE_URL"))
    try:
        with conn:  # one transaction: commit on success, rollback on error
            with conn.cursor() as cur:
                for c in campaigns:
                    cur.execute("select id from campaigns where slug = %s", (c["slug"],))
                    if cur.fetchone():
                        sets = ", ".join(f"{col} = %s" for col in _WRITE_COLS)
                        cur.execute(
                            f"update campaigns set {sets} where slug = %s",
                            (*vals(c), c["slug"]),
                        )
                        updated += 1
                    else:
                        cols = ["slug", *_WRITE_COLS, "is_default"]
                        placeholders = ", ".join(["%s"] * len(cols))
                        cur.execute(
                            f"insert into campaigns ({', '.join(cols)}) values ({placeholders})",
                            (c["slug"], *vals(c), False),
                        )
                        inserted += 1

                # Enforce exactly one default (partial unique index). Clear first,
                # then set — two statements so the index never sees two trues.
                if default_slug:
                    cur.execute("update campaigns set is_default = false where is_default")
                    cur.execute(
                        "update campaigns set is_default = true where slug = %s",
                        (default_slug,),
                    )
    finally:
        conn.close()

    console.print(f"[green]Synced[/green] — {inserted} inserted, {updated} updated.")
    if default_slug:
        console.print(f"[green]Default campaign:[/green] {default_slug}")
    else:
        console.print("[yellow]No is_default campaign in files — left DB default unchanged.[/yellow]")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
