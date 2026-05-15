"""Load a run_pipeline JSONL into Postgres (leads + enrichments + scores + drafts).

Idempotent on `linkedin_url`: re-running the same JSONL updates rows in
place rather than duplicating. Pre-existing drafts that are 'sent' or
'rejected' are NOT overwritten.

Usage:

    cd backend
    uv sync --extra worker
    uv run python -m scripts.ingest_run runs/2026-05-14.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from config import require

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


CHANNELS = ["linkedin_connect", "linkedin_dm", "email"]


def _connect():
    try:
        import psycopg
        from psycopg.types.json import Jsonb
    except ImportError as e:
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e
    return psycopg.connect(require("DATABASE_URL")), Jsonb


def _profile_summary(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not profile:
        return {}
    experiences = profile.get("experiences") or []
    return {
        "name": profile.get("full_name"),
        "headline": profile.get("headline"),
        "role": (experiences[0].get("title") if experiences else None) or profile.get("occupation"),
        "company": (experiences[0].get("company") if experiences else None),
        "location": (profile.get("city") or "")
        + (f", {profile.get('country_full_name')}" if profile.get("country_full_name") else ""),
    }


@app.command()
def main(
    jsonl: Annotated[Path, typer.Argument(help="Path to run_pipeline JSONL.")],
    source: Annotated[
        str,
        typer.Option(help="Tag stored in leads.source for provenance."),
    ] = "run_pipeline",
) -> None:
    if not jsonl.exists():
        console.print(f"[red]File not found:[/red] {jsonl}")
        raise typer.Exit(2)

    conn, Jsonb = _connect()
    inserted_leads = 0
    inserted_drafts = 0
    skipped_failed = 0

    with conn:
        with conn.cursor() as cur, jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("status") != "ok":
                    skipped_failed += 1
                    continue

                url = rec.get("linkedin_url")
                if not url:
                    continue

                summary = _profile_summary((rec.get("enrichment") or {}).get("profile"))
                score = rec.get("score") or {}

                # 1. UPSERT lead
                cur.execute(
                    """
                    insert into leads
                        (linkedin_url, name, headline, company, role, location,
                         segment, source, trigger, status, updated_at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'drafted', now())
                    on conflict (linkedin_url) do update
                      set name = excluded.name,
                          headline = excluded.headline,
                          company = excluded.company,
                          role = excluded.role,
                          location = excluded.location,
                          segment = coalesce(excluded.segment, leads.segment),
                          updated_at = now()
                    returning id
                    """,
                    (
                        url,
                        summary.get("name"),
                        summary.get("headline"),
                        summary.get("company"),
                        summary.get("role"),
                        summary.get("location"),
                        score.get("segment"),
                        source,
                        rec.get("trigger") or "list",
                    ),
                )
                lead_id = cur.fetchone()[0]
                inserted_leads += 1

                # 2. UPSERT enrichment
                enrichment = rec.get("enrichment") or {}
                cur.execute(
                    """
                    insert into enrichments
                        (lead_id, proxycurl_json, company_signals_json, github_json,
                         recent_posts_json, hooks_json, enriched_at)
                    values (%s, %s, %s, %s, %s, %s, now())
                    on conflict (lead_id) do update
                      set proxycurl_json = excluded.proxycurl_json,
                          company_signals_json = excluded.company_signals_json,
                          github_json = excluded.github_json,
                          recent_posts_json = excluded.recent_posts_json,
                          hooks_json = excluded.hooks_json,
                          enriched_at = now()
                    """,
                    (
                        lead_id,
                        Jsonb(enrichment.get("profile")),
                        Jsonb(enrichment.get("company_signals") or {}),
                        Jsonb(enrichment.get("github") or {}),
                        Jsonb(enrichment.get("recent_posts") or []),
                        Jsonb(rec.get("hooks") or []),
                    ),
                )

                # 3. UPSERT score
                if score:
                    cur.execute(
                        """
                        insert into scores (lead_id, fit_score, rationale, model, scored_at)
                        values (%s, %s, %s, %s, now())
                        on conflict (lead_id) do update
                          set fit_score = excluded.fit_score,
                              rationale = excluded.rationale,
                              scored_at = now()
                        """,
                        (
                            lead_id,
                            int(score.get("fit_score") or 0),
                            score.get("rationale"),
                            "claude",
                        ),
                    )

                # 4. INSERT drafts (skip channels that already have sent/rejected entries)
                drafts = rec.get("drafts") or {}
                chosen_hook = rec.get("chosen_hook")
                for step_index, channel in enumerate(CHANNELS):
                    body = drafts.get(channel)
                    if not body:
                        continue
                    cur.execute(
                        """
                        insert into drafts
                            (lead_id, channel, step_index, hook, body, status, generated_at)
                        values (%s, %s, %s, %s, %s, 'draft', now())
                        on conflict (lead_id, channel, step_index, variant) do update
                          set body = excluded.body,
                              hook = excluded.hook,
                              generated_at = now()
                          where drafts.status in ('draft', 'rejected')
                        """,
                        (
                            lead_id,
                            channel,
                            step_index,
                            Jsonb(chosen_hook),
                            body,
                        ),
                    )
                    inserted_drafts += 1

    console.rule("[bold]Ingest complete")
    console.print(f"  leads upserted:    {inserted_leads}")
    console.print(f"  drafts written:    {inserted_drafts}")
    console.print(f"  skipped (failed):  {skipped_failed}")


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
