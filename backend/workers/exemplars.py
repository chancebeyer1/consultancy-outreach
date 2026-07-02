"""Viral-post corpus — fetch real high-engagement LinkedIn AI posts via Unipile, rank by
actual engagement, and keep the best as few-shot exemplars for the content generator.

Comments and reposts are weighted far above reactions (the algorithm rewards them, and they're
the signal of a post worth mimicking). Job posts, one-liners, and walls of text are filtered out.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import unipile
from config import require

# Queries that surface practitioner AI content (not enterprise PR / job posts).
_QUERIES = (
    "AI agents", "building with AI", "AI automation", "LLM", "AI startup",
    "shipping AI", "AI engineering", "prompt engineering", "AI product",
)
_AI_TERMS = ("ai", "llm", "gpt", "agent", "model", "prompt", "machine learning", "automation",
            "claude", "openai", "anthropic", "chatbot", "neural", "ml ")


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _score(p: dict) -> int:
    return p["reactions"] + p["comments"] * 4 + p["reposts"] * 8


def _ai_relevant(text: str) -> bool:
    t = f" {text.lower()} "
    return any(term in t for term in _AI_TERMS)


def refresh_exemplars(*, keep: int = 24) -> dict:
    """Search several AI queries, dedupe, rank by engagement, store the top `keep`."""
    collected: dict[str, dict] = {}
    for kw in _QUERIES:
        try:
            res = unipile.search_posts(kw)
        except Exception:  # noqa: BLE001
            continue
        for p in res.get("items", []):
            if p.get("is_job"):
                continue
            text = (p.get("text") or "").strip()
            # substantive, but not a wall of text; and genuinely about AI
            if not (220 <= len(text) <= 2200) or not _ai_relevant(text):
                continue
            sid = p.get("social_id")
            if sid:
                collected[sid] = p
    ranked = sorted(collected.values(), key=_score, reverse=True)[:keep]
    if ranked:
        with _connect() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                insert into post_exemplars
                    (social_id, text, reactions, comments, reposts, score, author_headline, url, fetched_at)
                values (%s,%s,%s,%s,%s,%s,%s,%s, now())
                on conflict (social_id) do update set
                    reactions=excluded.reactions, comments=excluded.comments,
                    reposts=excluded.reposts, score=excluded.score, fetched_at=now()
                """,
                [(p["social_id"], p["text"], p["reactions"], p["comments"], p["reposts"],
                  _score(p), p.get("author_headline"), p.get("url")) for p in ranked],
            )
            # keep the table tight: drop all but the freshest, highest-scoring 60
            cur.execute(
                "delete from post_exemplars where social_id not in "
                "(select social_id from post_exemplars order by score desc, fetched_at desc limit 60)"
            )
    return {"collected": len(collected), "kept": len(ranked),
            "top_score": _score(ranked[0]) if ranked else 0}


def top_exemplars(n: int = 4) -> list[dict]:
    """The highest-engagement exemplars, for few-shot prompting."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select text, reactions, comments, reposts, author_headline "
            "from post_exemplars order by score desc, fetched_at desc limit %s",
            (n,),
        )
        return [
            {"text": t, "reactions": r, "comments": c, "reposts": rp, "author_headline": h}
            for t, r, c, rp, h in cur.fetchall()
        ]
