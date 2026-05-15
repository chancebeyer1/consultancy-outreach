"""Modal entrypoint — scheduled workers that keep the pipeline running
without operator intervention.

Functions
---------
- `pull_replies_cron`           every 15 min   poll Heyreach inbox, classify
                                               new replies, persist to Postgres.
- `pull_replies_now`            on-demand      same logic, one-shot. Trigger
                                               from CLI: `modal run modal_app.py::pull_replies_now`.
- `health`                      on-demand      sanity check that env + deps load.

Deploy
------
    cd backend
    uv sync --extra worker
    modal token new                      # one-time auth
    modal deploy modal_app.py            # ships the cron(s) to production
    modal logs consultancy-outreach      # tail

Local dev
---------
    modal run modal_app.py::pull_replies_now           # one-shot
    modal run modal_app.py::health                     # smoke test

Secrets
-------
This app reads env vars via `modal.Secret.from_name("outreach")`. Create it
once with all the keys from .env:

    modal secret create outreach \\
        --from-dotenv .env

Reads:
  ANTHROPIC_API_KEY, HEYREACH_API_KEY, DATABASE_URL, plus the optional
  CLAUDE_MODEL_* and LANDING_URL/CALCOM_URL strings used by the prompts.
"""

from __future__ import annotations

import modal

# ---------------------------------------------------------------------------
# Image: install deps from pyproject.toml, ship the backend/ source tree.
# ---------------------------------------------------------------------------

PYPROJECT = "pyproject.toml"

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "anthropic>=0.40.0",
        "httpx>=0.27.0",
        "python-dotenv>=1.0.1",
        "pydantic>=2.9.0",
        "tenacity>=9.0.0",
        "rich>=13.9.0",
        "typer>=0.13.0",
        # worker extras
        "psycopg[binary]>=3.2.0",
    )
    # Drop the backend/ tree into /root/backend so imports work the same as
    # local: `from workers.replies import ...`. The local source path is the
    # parent dir of this file (modal_app.py is at backend/modal_app.py).
    .add_local_python_source(
        "clients",
        "workers",
        "config",
        "prompts_loader",
    )
    # Prompts are referenced from prompts_loader → backend/prompts/*.md.
    # add_local_dir mirrors the directory at runtime.
    .add_local_dir("prompts", remote_path="/root/prompts")
)

app = modal.App("consultancy-outreach", image=image)

# All scheduled functions share one secret bundle.
secrets = [modal.Secret.from_name("outreach")]


# ---------------------------------------------------------------------------
# Scheduled work
# ---------------------------------------------------------------------------


@app.function(
    schedule=modal.Cron("*/15 * * * *"),  # every 15 minutes
    secrets=secrets,
    timeout=600,
    retries=2,
)
def pull_replies_cron() -> dict:
    """Poll Heyreach for new inbound replies, classify them, persist.

    Conservatively scoped per run (limit=100 conversations) so a single tick
    finishes well inside the 10-minute timeout even with classifier latency.
    """
    return _pull_replies_impl(limit=100, only_with_unread=True)


@app.function(secrets=secrets, timeout=600)
def pull_replies_now(limit: int = 100, include_read: bool = False) -> dict:
    """On-demand trigger of the same logic — for ad-hoc runs from CLI.

    Usage:
        modal run modal_app.py::pull_replies_now
        modal run modal_app.py::pull_replies_now --limit 50 --include-read
    """
    return _pull_replies_impl(limit=limit, only_with_unread=not include_read)


def _pull_replies_impl(*, limit: int, only_with_unread: bool) -> dict:
    """Shared body — runs inside the Modal container, so backend/* is on path."""
    from workers.replies import fetch_and_classify_new_replies
    from workers.replies_db import existing_external_ids, insert_replies

    seen = existing_external_ids(limit=5000)
    new_records = fetch_and_classify_new_replies(
        seen_message_ids=seen,
        limit=limit,
        only_with_unread=only_with_unread,
    )
    if not new_records:
        return {"new_records": 0, "inserted": 0}

    counts = insert_replies(new_records)
    return {"new_records": len(new_records), **counts}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.function(secrets=secrets, timeout=60)
def health() -> dict:
    """Verify env, deps, and DB connectivity. No external API calls."""
    import os

    from config import Config

    checks = {
        "anthropic_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "heyreach_api_key": bool(Config.heyreach_api_key),
        "database_url": bool(Config.database_url),
        "claude_model_draft": Config.claude_model_draft,
    }

    # Quick DB ping
    if Config.database_url:
        try:
            import psycopg

            with psycopg.connect(Config.database_url) as conn:
                with conn.cursor() as cur:
                    cur.execute("select count(*) from replies")
                    checks["replies_count"] = cur.fetchone()[0]
        except Exception as e:  # noqa: BLE001
            checks["db_error"] = str(e)

    return checks


# ---------------------------------------------------------------------------
# Webhook stubs — Phase 3 (Heyreach + Smartlead reply webhooks)
# ---------------------------------------------------------------------------
#
# When you want sub-15-minute reply latency, replace pull_replies_cron with
# webhook receivers. Heyreach sends a POST per inbound reply; Smartlead
# similar. Below is the shape — uncomment + verify the auth header against
# the relevant provider docs before deploying.
#
# @app.function(secrets=secrets)
# @modal.fastapi_endpoint(method="POST")
# def heyreach_webhook(payload: dict) -> dict:
#     from workers.replies import _classify_one, _find_last_outbound
#     from workers.replies_db import insert_replies
#     # ... parse payload, fetch full thread, classify, persist
#     return {"ok": True}
