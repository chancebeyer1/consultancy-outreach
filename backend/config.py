"""Config loader. Reads .env from project root."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"

load_dotenv(PROJECT_ROOT / ".env")


def _required(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Missing required env var: {key}. Copy .env.example to .env and fill it in."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class Config:
    # LLM
    anthropic_api_key: str = _required("ANTHROPIC_API_KEY")
    claude_model_draft: str = _optional("CLAUDE_MODEL_DRAFT", "claude-sonnet-4-6")
    claude_model_reason: str = _optional("CLAUDE_MODEL_REASON", "claude-opus-4-7")

    # Enrichment
    proxycurl_api_key: str = _optional("PROXYCURL_API_KEY")
    tavily_api_key: str = _optional("TAVILY_API_KEY")
    serper_api_key: str = _optional("SERPER_API_KEY")
    github_token: str = _optional("GITHUB_TOKEN")

    # Senders (Phase 2+)
    heyreach_api_key: str = _optional("HEYREACH_API_KEY")
    smartlead_api_key: str = _optional("SMARTLEAD_API_KEY")

    # DB
    database_url: str = _optional("DATABASE_URL")

    # Outreach content
    landing_url: str = _optional("LANDING_URL", "https://your-domain.com")
    calcom_url: str = _optional("CALCOM_URL", "https://cal.com/your-handle")
