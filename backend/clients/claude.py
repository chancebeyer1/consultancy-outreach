"""Anthropic Claude client with prompt caching on the static prefix.

The cached system prefix (ICP + style + proof + voice corpus) is sent on every
call as a cacheable system block. Subsequent calls within the cache TTL (~5 min)
pay only for the variable user content.
"""

from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import Config
from backend.prompts_loader import cached_system_prefix

_client = Anthropic(api_key=Config.anthropic_api_key)


def _system_blocks(extra: str | None = None) -> list[dict[str, Any]]:
    """Build the system content array. The big prefix is marked for caching."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": cached_system_prefix(),
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if extra:
        blocks.append({"type": "text", "text": extra})
    return blocks


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def call(
    *,
    instruction: str,
    user_payload: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """One Claude call with caching on the system prefix.

    `instruction` is the task-specific prompt (appended to system, not cached).
    `user_payload` is the per-call variable content (the enrichment JSON, etc.).
    """
    model = model or Config.claude_model_draft
    response = _client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=_system_blocks(extra=instruction),
        messages=[{"role": "user", "content": user_payload}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def call_json(
    *,
    instruction: str,
    user_payload: str,
    model: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> Any:
    """Like `call` but parses JSON from the response. Strips fences if present."""
    raw = call(
        instruction=instruction,
        user_payload=user_payload,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    return json.loads(text)
