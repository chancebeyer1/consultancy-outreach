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

# libpq's default connect timeout is INFINITE — a stalled TCP connect to the Supabase pooler
# hangs the worker forever (the 2026-07 hourly_dispatcher 80-min hang). libpq reads this env
# var at connect time; setdefault so an explicit env override still wins.
os.environ.setdefault("PGCONNECT_TIMEOUT", "15")
# Likewise cap how long any single statement can sit on a lock/slow plan. Session-scoped via
# libpq startup options (verified the Supabase pooler passes it through) — affects only OUR
# processes, not the shared role. 120s >> any legitimate worker statement.
os.environ.setdefault("PGOPTIONS", "-c statement_timeout=120000")


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


# Free/personal email providers. We send cold outreach to CORPORATE mailboxes ONLY — Maildoso's
# strong recommendation, because personal-inbox sends from cold domains draw spam complaints and
# tank sender reputation. Used to gate both Apollo email reveal and the SMTP sender.
FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "rocketmail.com", "yahoo.co.uk",
    "hotmail.com", "hotmail.co.uk", "outlook.com", "outlook.co.uk", "live.com", "msn.com",
    "aol.com", "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com", "pm.me",
    "gmx.com", "gmx.net", "mail.com", "zoho.com", "yandex.com", "yandex.ru", "hey.com",
    "fastmail.com", "tutanota.com", "hushmail.com",
    "comcast.net", "verizon.net", "att.net", "sbcglobal.net", "cox.net", "charter.net",
    "bellsouth.net", "earthlink.net", "pacbell.net", "frontier.com", "roadrunner.com", "optonline.net",
})


def is_corporate_email(email: str | None) -> bool:
    """True only for a business/corporate address (not a free/personal provider)."""
    if not email or "@" not in email:
        return False
    return email.rsplit("@", 1)[1].strip().lower() not in FREE_EMAIL_DOMAINS


class Config:
    # LLM
    anthropic_api_key: str = _env("ANTHROPIC_API_KEY")
    claude_model_draft: str = _env("CLAUDE_MODEL_DRAFT", "claude-sonnet-4-6")
    claude_model_reason: str = _env("CLAUDE_MODEL_REASON", "claude-sonnet-4-6")

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

    # Email outbound (cold email system)
    millionverifier_api_key: str = _env("MILLIONVERIFIER_API_KEY")
    apollo_api_key: str = _env("APOLLO_API_KEY")  # email lead sourcing + work-email reveal
    resend_api_key: str = _env("RESEND_API_KEY")
    notify_email: str = _env("NOTIFY_EMAIL")

    # DB
    database_url: str = _env("DATABASE_URL")

    # Outreach content
    landing_url: str = _env("LANDING_URL", "https://your-domain.com")
    calcom_url: str = _env("CALCOM_URL", "https://cal.com/your-handle")
    sender_first_name: str = _env("SENDER_FIRST_NAME", "Chance")  # fills {{my_first_name}} in drafts

    # X / Twitter viral-post discovery (twitterapi.io) — finds high-engagement AI tweets to
    # react to in LinkedIn posts. Optional: if unset, the tweet-reaction generator is skipped.
    xsearch_api_key: str = _env("XSEARCH_API_KEY")

    # Newsletter ("The Agent Brief") — sent via Resend to opted-in subscribers (NOT cold boxes).
    # Set NEWSLETTER_FROM to a verified Resend sending domain, e.g. "The Agent Brief <brief@contentdrip.ai>".
    newsletter_from: str = _env("NEWSLETTER_FROM", "The Agent Brief <brief@contentdrip.ai>")
