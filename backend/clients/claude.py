"""Anthropic Claude client with prompt caching on the static prefix.

The cached system prefix (a campaign's ICP + style + offer + voice corpus) is
sent on every call as a cacheable system block. Subsequent calls within the
cache TTL (~5 min) pay only for the variable user content. Callers pass the
prefix for the active campaign via `system_prefix=`; when omitted we fall back
to the default campaign so ad-hoc calls still work.
"""

from __future__ import annotations

import json
from typing import Any

from functools import lru_cache

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config, require
from prompts_loader import default_system_prefix


@lru_cache(maxsize=1)
def _client() -> Anthropic:
    """Lazy Anthropic client. Validates the API key on first call, not at import."""
    return Anthropic(api_key=require("ANTHROPIC_API_KEY"))


def _system_blocks(prefix: str, extra: str | None = None) -> list[dict[str, Any]]:
    """Build the system content array. The big prefix is marked for caching."""
    blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": prefix,
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
    system_prefix: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> str:
    """One Claude call with caching on the system prefix.

    `instruction` is the task-specific prompt (appended to system, not cached).
    `user_payload` is the per-call variable content (the enrichment JSON, etc.).
    `system_prefix` is the active campaign's cached persona prefix; when omitted
    we resolve the default campaign's prefix.
    """
    model = model or Config.claude_model_draft
    prefix = system_prefix if system_prefix is not None else default_system_prefix()
    # Newer Claude models deprecated `temperature` (they manage sampling internally)
    # and 400 if it's sent, so we don't forward it. The param stays in the signature
    # for caller back-compat; `_ =` marks it intentionally unused.
    _ = temperature
    response = _client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_system_blocks(prefix, extra=instruction),
        messages=[{"role": "user", "content": user_payload}],
    )
    if getattr(response, "stop_reason", None) == "max_tokens":
        # Truncated output. For JSON callers this guarantees a parse failure downstream — make the
        # real cause visible in logs instead of a cryptic "Expecting value: line 1 column 1".
        print(f"WARNING claude.call truncated at max_tokens={max_tokens} (model={model}) — raise the cap")
    return "".join(block.text for block in response.content if block.type == "text").strip()


def call_json(
    *,
    instruction: str,
    user_payload: str,
    system_prefix: str | None = None,
    model: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> Any:
    """Like `call` but parses JSON from the response. Strips fences if present."""
    raw = call(
        instruction=instruction,
        user_payload=user_payload,
        system_prefix=system_prefix,
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Some prompts lead the model to narrate its choice before the JSON ("Looking at the
        # candidates, the X story is sharpest... {json}"). Recover by decoding the first embedded
        # JSON value — raw_decode parses one value and ignores any surrounding prose.
        for i, ch in enumerate(text):
            if ch in "{[":
                try:
                    return json.JSONDecoder().raw_decode(text[i:])[0]
                except json.JSONDecodeError:
                    continue
        if text and not text.rstrip().endswith(("}", "]")):
            raise ValueError(
                f"model output looks TRUNCATED (doesn't end in }} or ]; max_tokens={max_tokens}) — "
                f"raise max_tokens for this call. Tail: …{text[-80:]!r}"
            )
        raise
