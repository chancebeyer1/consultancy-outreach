"""Config loader. Reads .env from project root.

Env vars are read lazily — `Config` exposes them as attributes, but missing
required keys are only flagged when a caller actually tries to use them.
This lets `--help` and offline tests run without a populated .env.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"

# override=True so the project's .env is authoritative. Without it, a stray var
# already in the shell (e.g. an empty ANTHROPIC_API_KEY) silently shadows .env.
load_dotenv(PROJECT_ROOT / ".env", override=True)


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def require(key: str) -> str:
    """Read a required env var. Raises with a helpful message if missing.

    Call this at the use site, not at module import, so CLIs can boot
    without a fully-populated .env.
    """
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Missing required env var: {key}. Copy .env.example to .env and fill it in."
        )
    return value


class Config:
    # LLM
    anthropic_api_key: str = _env("ANTHROPIC_API_KEY")
    claude_model_draft: str = _env("CLAUDE_MODEL_DRAFT", "claude-sonnet-4-6")
    claude_model_reason: str = _env("CLAUDE_MODEL_REASON", "claude-opus-4-7")

    # Enrichment
    tavily_api_key: str = _env("TAVILY_API_KEY")
    serper_api_key: str = _env("SERPER_API_KEY")

    # Unipile — one unified API for LinkedIn send/DM/invite + email + enrichment.
    # Connect a LinkedIn account and a mailbox once in the Unipile dashboard;
    # each gets an account_id we pass on every call. v1 = single LinkedIn + single mailbox.
    unipile_api_key: str = _env("UNIPILE_API_KEY")
    unipile_dsn: str = _env("UNIPILE_DSN")  # e.g. api1.unipile.com:13111
    unipile_linkedin_account_id: str = _env("UNIPILE_LINKEDIN_ACCOUNT_ID")
    unipile_email_account_id: str = _env("UNIPILE_EMAIL_ACCOUNT_ID")

    # DB
    database_url: str = _env("DATABASE_URL")

    # Outreach content
    landing_url: str = _env("LANDING_URL", "https://your-domain.com")
    calcom_url: str = _env("CALCOM_URL", "https://cal.com/your-handle")
