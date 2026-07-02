"""Daily AI SEO blog generator.

Pulls recent AI news, writes a full ~800-word SEO article grounded in the freshest unused story,
and stores it in `blog_posts` for the public site to render at /blog/<slug>. Each article teaches
something real, links the single most-relevant free tool, and closes with a booking CTA — so every
post is an indexable page that funnels to the tools + a consult. Deduped against content_seen.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg
from psycopg.types.json import Jsonb

from clients import claude, news
from config import Config, require
from prompts_loader import load_prompt

# The free tools + booking link the article can promote (URLs mirror website/lib/site.ts).
TOOLS = [
    {"name": "AI Opportunity Audit", "url": "https://agentry.contentdrip.ai/audit",
     "what": "finds your 3 highest-impact automations from just your website"},
    {"name": "AI Agent ROI Calculator", "url": "https://agentry.contentdrip.ai/roi-calculator",
     "what": "estimates the hours and dollars agents could give your team back"},
    {"name": "Roast My Cold Outreach", "url": "https://agentry.contentdrip.ai/roast",
     "what": "tears down a cold email and rewrites it"},
]
BOOK_URL = "https://calendly.com/hello-contentdrip/chance-beyer-intro"


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    return (s[:70].strip("-")) or "ai-update"


def generate_blog_post(*, dry_run: bool = False) -> dict[str, Any]:
    """Write one SEO article from the freshest unused AI story. Returns {generated, id, slug, ...}."""
    try:
        stories = news.fetch_all_sources()
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": f"news fetch failed: {e}"}
    if not stories:
        return {"generated": False, "reason": "no AI stories in window"}

    def _key(s: dict) -> str:
        return f"blog:{s.get('source_kind')}:{s.get('id')}"

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select source_key from content_seen where source_key like 'blog:%'")
        seen = {r[0] for r in cur.fetchall()}
    fresh = [s for s in stories if _key(s) not in seen]
    if not fresh:
        return {"generated": False, "reason": "all candidate stories already used"}
    story = fresh[0]

    payload = {
        "story": {"title": story.get("title"), "url": story.get("url"), "summary": story.get("summary")},
        "tools": TOOLS,
        "book_url": BOOK_URL,
    }
    try:
        # 4000 tokens: the output grew when linkedin_post was added to this call (article 700-1000
        # words + 1000-1600 char post) — at 2600 the JSON was getting truncated mid-string and
        # failing to parse ("Expecting value: line 1 column 1").
        result = claude.call_json(
            instruction=load_prompt("draft_blog_post"),
            user_payload=json.dumps(payload, indent=2),
            model=Config.claude_model_draft,
            max_tokens=4000,
        )
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": f"generation failed: {e}"}

    title = (result.get("title") or "").strip()
    body = (result.get("body_md") or "").strip()
    meta = (result.get("meta_description") or "").strip()[:160]
    tags = result.get("tags") if isinstance(result.get("tags"), list) else []
    if not title or len(body) < 300:
        return {"generated": False, "reason": "model returned an empty or too-short article"}

    slug = _slugify(title)
    if dry_run:
        return {"generated": True, "dry_run": True, "title": title, "slug": slug,
                "words": len(body.split()), "source": story.get("title")}

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select 1 from blog_posts where slug = %s", (slug,))
        if cur.fetchone():
            slug = f"{slug}-{str(story.get('id'))[:6]}"  # de-collide on a repeated title
        cur.execute(
            "insert into blog_posts (slug, title, meta_description, body_md, tags, source_title, "
            "source_url, status) values (%s,%s,%s,%s,%s,%s,%s,'published') returning id",
            (slug, title, meta, body, Jsonb(tags), story.get("title"), story.get("url")),
        )
        post_id = str(cur.fetchone()[0])
        cur.execute(
            "insert into content_seen (source_key, title) values (%s,%s) on conflict (source_key) do nothing",
            (_key(story), (story.get("title") or "")[:200]),
        )
        # Queue a LinkedIn post promoting the article — a DRAFT for review (status='draft'); it shows
        # in the Content "Needs review" queue and never auto-posts, per the operator's preference.
        li = (result.get("linkedin_post") or "").strip()
        li_queued = False
        if li:
            blog_url = f"https://agentry.contentdrip.ai/blog/{slug}"  # slug is final (post de-collision)
            li_body = f"{li}\n\nfull breakdown: {blog_url}"
            cur.execute(
                "insert into content_posts (source_kind, source_title, source_url, body, status) "
                "values ('blog', %s, %s, %s, 'draft')",
                (title, blog_url, li_body),
            )
            li_queued = True
    return {"generated": True, "id": post_id, "slug": slug, "title": title, "linkedin_draft": li_queued}


def list_published(limit: int = 100) -> list[dict[str, Any]]:
    """Published posts, newest first — for the /blog index + sitemap."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select slug, title, meta_description, tags, published_at from blog_posts "
            "where status = 'published' order by published_at desc limit %s",
            (limit,),
        )
        return [
            {"slug": r[0], "title": r[1], "meta_description": r[2], "tags": r[3] or [],
             "published_at": r[4].isoformat() if r[4] else None}
            for r in cur.fetchall()
        ]


def get_by_slug(slug: str) -> dict[str, Any] | None:
    """One published post by slug — for the article page."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select slug, title, meta_description, body_md, tags, source_title, source_url, published_at "
            "from blog_posts where slug = %s and status = 'published'",
            (slug,),
        )
        r = cur.fetchone()
    if not r:
        return None
    return {"slug": r[0], "title": r[1], "meta_description": r[2], "body_md": r[3],
            "tags": r[4] or [], "source_title": r[5], "source_url": r[6],
            "published_at": r[7].isoformat() if r[7] else None}
