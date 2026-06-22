"""Campaign persona loader — the runtime source of dynamic targeting.

A *campaign* is a persona bundle: its own audience (ICP) and offer (pitch/proof),
with optional per-campaign style/voice overrides and sales-asset URLs. Swapping
the campaign swaps *who* we target and *what* we pitch, while the generic
mechanics prompts (score, draft, reply_classify) stay global.

Two sources, one shape:
  - **DB** (`campaigns` table) is the runtime source of truth when DATABASE_URL
    is set. The dashboard writes here; this is what production reads.
  - **Files** (`backend/campaigns/<slug>/`) are the versioned seed/backup. When
    DATABASE_URL is unset (offline / file mode / tests), we read straight from
    disk so the pipeline keeps working without a database.

`scripts.sync_campaigns` is the file→DB bridge (upsert by slug).

Style and voice are *personal* (how you write), not audience-specific, so a
campaign usually leaves them null and falls back to the global defaults in
backend/prompts/{style,voice_corpus}.md (resolved in prompts_loader.system_prefix).
"""

from __future__ import annotations

import tomllib
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from config import BACKEND_DIR, Config, require

CAMPAIGNS_DIR = BACKEND_DIR / "campaigns"


@dataclass(frozen=True)
class Campaign:
    """One resolved persona bundle. Frozen so it's safe to lru_cache and thread."""

    slug: str
    name: str
    icp_md: str
    offer_md: str
    landing_url: str
    calcom_url: str
    is_default: bool = False
    style_md: str | None = None  # null → global default (prompts/style.md)
    voice_md: str | None = None  # null → global default (prompts/voice_corpus.md)
    status: str = "active"
    id: str | None = None  # DB uuid; None in file-seed mode
    search_url: str | None = None  # saved LinkedIn/Sales-Nav people search for sourcing
    channels: tuple[str, ...] | None = None  # initial draft channels; None → all (connect/dm/email)


# ---------------------------------------------------------------------------
# File-seed source (offline / no DATABASE_URL)
# ---------------------------------------------------------------------------


def _read_optional(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


def _default_slug_from_files() -> str:
    """Find the folder whose campaign.toml sets is_default; fall back to '_default'."""
    if CAMPAIGNS_DIR.is_dir():
        for folder in sorted(CAMPAIGNS_DIR.iterdir()):
            toml_path = folder / "campaign.toml"
            if folder.is_dir() and toml_path.exists():
                try:
                    meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
                except tomllib.TOMLDecodeError:
                    continue
                if meta.get("is_default"):
                    return meta.get("slug") or folder.name
    return "_default"


def _load_from_files(slug: str | None) -> Campaign:
    slug = slug or _default_slug_from_files()
    folder = CAMPAIGNS_DIR / slug
    if not folder.is_dir():
        raise FileNotFoundError(
            f"Campaign '{slug}' not found at {folder}. "
            f"Create backend/campaigns/{slug}/ (icp.md, offer.md, campaign.toml)."
        )

    meta: dict = {}
    toml_path = folder / "campaign.toml"
    if toml_path.exists():
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    icp = _read_optional(folder / "icp.md")
    offer = _read_optional(folder / "offer.md")
    if icp is None or offer is None:
        raise FileNotFoundError(f"Campaign '{slug}' is missing icp.md or offer.md in {folder}.")

    return Campaign(
        slug=meta.get("slug") or slug,
        name=meta.get("name") or slug,
        icp_md=icp,
        offer_md=offer,
        style_md=_read_optional(folder / "style.md"),
        voice_md=_read_optional(folder / "voice.md") or _read_optional(folder / "voice_corpus.md"),
        landing_url=meta.get("landing_url") or Config.landing_url,
        calcom_url=meta.get("calcom_url") or Config.calcom_url,
        is_default=bool(meta.get("is_default", False)),
        status=meta.get("status") or "active",
        id=None,
        search_url=meta.get("search_url"),
        channels=tuple(meta["channels"]) if meta.get("channels") else None,
    )


# ---------------------------------------------------------------------------
# DB source (runtime source of truth)
# ---------------------------------------------------------------------------

_COLUMNS = (
    "id, slug, name, icp_md, offer_md, style_md, voice_md, "
    "landing_url, calcom_url, is_default, status, search_url, channels"
)


def _row_to_campaign(row: tuple) -> Campaign:
    (cid, slug, name, icp_md, offer_md, style_md, voice_md,
     landing_url, calcom_url, is_default, status, search_url, channels) = row
    return Campaign(
        slug=slug,
        name=name,
        icp_md=icp_md or "",
        offer_md=offer_md or "",
        style_md=style_md,
        voice_md=voice_md,
        landing_url=landing_url or Config.landing_url,
        calcom_url=calcom_url or Config.calcom_url,
        is_default=bool(is_default),
        status=status or "active",
        id=str(cid),
        search_url=search_url,
        channels=tuple(channels) if channels else None,
    )


def _load_from_db(slug_or_id: str | None) -> Campaign | None:
    """Read one campaign from Postgres. Returns None if not found (caller falls back)."""
    try:
        import psycopg
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("psycopg not installed. Run: uv sync --extra worker") from e

    if slug_or_id is None:
        where, params = "where is_default", ()
    elif _is_uuid(slug_or_id):
        where, params = "where id = %s", (slug_or_id,)
    else:
        where, params = "where slug = %s", (slug_or_id,)

    with psycopg.connect(require("DATABASE_URL")) as conn:
        with conn.cursor() as cur:
            cur.execute(f"select {_COLUMNS} from campaigns {where} limit 1", params)
            row = cur.fetchone()
    return _row_to_campaign(row) if row else None


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def load_campaign(slug_or_id: str | None = None) -> Campaign:
    """Load a campaign by slug or id; None → the default campaign.

    DB-first when DATABASE_URL is set, falling back to the file seed when the
    row is absent (e.g. sync not yet run) or the DB is unconfigured. Cached per
    process — one pipeline run resolves the campaign once.
    """
    if Config.database_url:
        campaign = _load_from_db(slug_or_id)
        if campaign is not None:
            return campaign
        # DB configured but no matching row → fall back to the versioned seed.
    return _load_from_files(slug_or_id)
