"""Loads prompt markdown files from backend/prompts/."""

from __future__ import annotations

from functools import lru_cache

from backend.config import PROMPTS_DIR


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Load a prompt file by stem name. Cached for the process lifetime."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def cached_system_prefix() -> str:
    """The big static prefix that gets prompt-cached on Anthropic.

    Includes: ICP definition, style guide, proof artifact, voice corpus.
    Anything that's stable across all calls in a session.
    """
    parts = [
        "# ICP\n\n" + load_prompt("icp"),
        "# Style guide\n\n" + load_prompt("style"),
        "# Proof / sales artifact\n\n" + load_prompt("proof"),
        "# Voice corpus (few-shot examples — match this voice)\n\n" + load_prompt("voice_corpus"),
    ]
    return "\n\n---\n\n".join(parts)
