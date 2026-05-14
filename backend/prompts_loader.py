"""Loads prompt markdown files from backend/prompts/."""

from __future__ import annotations

from functools import lru_cache

from config import PROMPTS_DIR


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
