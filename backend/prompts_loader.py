"""Loads prompt markdown files and assembles the cached system prefix.

Two kinds of prompt content:
  - **Generic mechanics** (score, insight_extraction, draft_*, reply_classify):
    campaign-agnostic, loaded by name via `load_prompt()`.
  - **Persona** (ICP + offer, optional style/voice): per-campaign, supplied by a
    `Campaign` and assembled into the cached system prefix via `system_prefix()`.

The system prefix is the big static block we mark for prompt-caching on every
Claude call. It's identical across all leads in a single campaign run, so it
caches within the ~5-min TTL; a different campaign keys to a different cache
entry (correct).
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from config import PROMPTS_DIR

if TYPE_CHECKING:
    from campaigns_loader import Campaign


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a prompt file by stem name. Cached for the process lifetime.

    Special case: `voice_corpus` falls back to `voice_corpus.example` if the
    user's filled-in copy isn't present. The filled-in copy is gitignored to
    keep real DMs out of public repos.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists() and name == "voice_corpus":
        path = PROMPTS_DIR / "voice_corpus.example.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=32)
def system_prefix(campaign: Campaign) -> str:
    """The big static prefix that gets prompt-cached on Anthropic, for one campaign.

    Assembles: the campaign's ICP + offer, plus style + voice corpus. Style and
    voice fall back to the global defaults (prompts/style.md, prompts/voice_corpus.md)
    when the campaign doesn't override them — they're personal, not audience-specific.

    Cached by campaign (frozen, hashable) so a multi-lead run reuses one identical
    string → byte-identical system block → Anthropic prompt-cache hits.
    """
    parts = [
        "# ICP\n\n" + campaign.icp_md,
        "# Style guide\n\n" + (campaign.style_md or load_prompt("style")),
        "# Offer / sales artifact\n\n" + campaign.offer_md,
        "# Voice corpus (few-shot examples — match this voice)\n\n"
        + (campaign.voice_md or load_prompt("voice_corpus")),
    ]
    return "\n\n---\n\n".join(parts)


def default_system_prefix() -> str:
    """System prefix for the default campaign — used when no campaign is threaded.

    Lazy import keeps prompts_loader free of a hard dependency on the DB layer.
    """
    from campaigns_loader import load_campaign

    return system_prefix(load_campaign())
