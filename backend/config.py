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

load_dotenv(PROJECT_ROOT / ".env")


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
    proxycurl_api_key: str = _env("PROXYCURL_API_KEY")
    tavily_api_key: str = _env("TAVILY_API_KEY")
    serper_api_key: str = _env("SERPER_API_KEY")
    github_token: str = _env("GITHUB_TOKEN")

    # Senders (Phase 2+)
    heyreach_api_key: str = _env("HEYREACH_API_KEY")
    smartlead_api_key: str = _env("SMARTLEAD_API_KEY")

    # DB
    database_url: str = _env("DATABASE_URL")

    # Outreach content
    landing_url: str = _env("LANDING_URL", "https://your-domain.com")
    calcom_url: str = _env("CALCOM_URL", "https://cal.com/your-handle")
