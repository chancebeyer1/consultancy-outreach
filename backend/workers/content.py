"""LinkedIn content engine — turn recent AI news into a valuable post, on review.

generate_post() pulls high-signal AI stories (Hacker News), drops anything already used, asks
Claude to pick the best one and write a no-slop post in the studio voice, stores it as a draft
for review, and emails an alert. publish_approved() takes posts the operator approved in the
dashboard and publishes them to LinkedIn via Unipile.

Human-in-the-loop by design: nothing is published until a person edits + approves it.
"""
from __future__ import annotations

import base64
import json
import re
import sys
import unicodedata
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg
from psycopg.types.json import Jsonb

from clients import claude, news, unipile
from config import Config, require
from prompts_loader import load_prompt
from workers.cards import render_image


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


# Strip the punctuation that screams "AI wrote this" — em/en dashes, curly quotes, the ellipsis
# glyph, exotic spaces — and convert dashes-as-punctuation to commas. Plain ASCII only.
_CHAR_FIXES = {
    "—": ", ", "–": ", ", "―": ", ",            # em / en / horizontal-bar dash
    "‘": "'", "’": "'", "‛": "'",                 # curly single quotes
    "“": '"', "”": '"',                                # curly double quotes
    "…": "...",                                             # ellipsis glyph
    " ": " ", " ": " ", " ": " ", "​": "",   # nbsp / narrow / thin / zero-width
}


def _sanitize(text: str) -> str:
    if not text:
        return text
    # NFKC folds growth-hacker math-bold/italic unicode (𝗣𝗮𝗶𝗱) and full-width glyphs back to ASCII.
    text = unicodedata.normalize("NFKC", text)
    for k, v in _CHAR_FIXES.items():
        text = text.replace(k, v)
    text = re.sub(r"\s*-{2,}\s*", ", ", text)          # "--" / "---" used as a dash
    text = text.replace(" - ", ", ")                  # spaced hyphen used as a dash
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)       # no space before punctuation
    text = re.sub(r",\s*,", ", ", text)                # collapse doubled commas
    text = re.sub(r"[^\S\n]{2,}", " ", text)           # collapse space runs (keep newlines)
    return text.strip()


def _image_from(result: Any) -> tuple[dict | None, str | None]:
    """Pull the image spec ({type, ...}) from the model output, sanitize its text, render a PNG."""
    spec = result.get("image") if isinstance(result, dict) else None
    if not isinstance(spec, dict):
        spec = result.get("card") if isinstance(result, dict) else None  # back-compat
    if not isinstance(spec, dict):
        return None, None
    clean: dict[str, Any] = {}
    for k, v in spec.items():
        if isinstance(v, str):
            clean[k] = _sanitize(v)
        elif isinstance(v, list):
            clean[k] = [_sanitize(str(x)) for x in v]
        else:
            clean[k] = v
    png = None
    try:
        png = render_image(clean)
    except Exception:  # noqa: BLE001 — image rendering is best-effort
        png = None
    return clean, (base64.b64encode(png).decode("ascii") if png else None)


POST_FORMATS = ("contrarian", "stat_hook", "before_after", "breakdown", "story", "listicle", "one_liner")


def generate_post(*, dry_run: bool = False, fmt: str | None = None) -> dict[str, Any]:
    """Draft one LinkedIn post from the freshest high-signal AI story.

    `fmt` (one of POST_FORMATS) forces the post's format/angle; None lets the model pick the
    format that best fits the chosen story (avoiding recently-used ones)."""
    try:
        stories = news.fetch_all_sources()
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": f"news fetch failed: {e}"}
    if not stories:
        return {"generated": False, "reason": "no AI stories in window"}

    def _key(s: dict) -> str:
        return f"{s['source_kind']}:{s['id']}"

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select source_key from content_seen")
        seen = {r[0] for r in cur.fetchall()}
        cur.execute(
            "select format, card->>'type' from content_posts "
            "where created_at > now() - interval '14 days' order by created_at desc limit 5"
        )
        recent = cur.fetchall()
    recent_formats = [r[0] for r in recent if r[0]]
    recent_types = [r[1] for r in recent if r[1]]
    fresh = [s for s in stories if _key(s) not in seen]
    if not fresh:
        return {"generated": False, "reason": "all candidate stories already used"}

    candidates = [
        {k: s.get(k) for k in ("id", "source_kind", "title", "url", "summary", "points", "num_comments")}
        for s in fresh[:12]
    ]
    try:
        from workers.exemplars import top_exemplars

        exemplars = top_exemplars(3)
    except Exception:  # noqa: BLE001
        exemplars = []
    payload = {"candidates": candidates, "exemplars": exemplars,
               "avoid_formats": recent_formats, "avoid_image_types": recent_types}
    if fmt and fmt in POST_FORMATS:
        payload["force_format"] = fmt  # operator picked this angle in the dashboard
    try:
        result = claude.call_json(
            instruction=load_prompt("draft_linkedin_post") + "\n\n" + load_prompt("linkedin_playbook"),
            user_payload=json.dumps(payload, indent=2),
            model=Config.claude_model_draft,
            max_tokens=1500,
        )
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": f"generation failed: {e}"}

    post = _sanitize(result.get("post") or "")
    image_idea = _sanitize(result.get("image_idea") or "")
    image_spec, card_b64 = _image_from(result)
    fmt = (result.get("format") or "").strip()[:40] or None
    chosen_id = str(result.get("chosen_id") or "")
    item = next((s for s in fresh if s["id"] == chosen_id), fresh[0])
    if not post:
        return {"generated": False, "reason": "model returned an empty post"}

    if dry_run:
        return {"generated": True, "dry_run": True, "source": item["title"],
                "source_url": item.get("url") or item["discussion_url"],
                "post": post, "format": fmt, "image_type": (image_spec or {}).get("type"),
                "image_idea": image_idea, "card_rendered": bool(card_b64)}

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into content_posts
                    (source_kind, source_title, source_url, discussion_url, body, format,
                     image_idea, card, card_image, status)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft')
                returning id
                """,
                (item["source_kind"], item["title"], item.get("url"), item.get("discussion_url"),
                 post, fmt, image_idea or None, Jsonb(image_spec) if image_spec else None, card_b64),
            )
            post_id = str(cur.fetchone()[0])
            cur.execute(
                "insert into content_seen (source_key, title) values (%s,%s) "
                "on conflict (source_key) do nothing",
                (f"{item['source_kind']}:{item['id']}", item["title"]),
            )

    _notify_draft(item, post)
    return {"generated": True, "id": post_id, "source": item["title"]}


def _notify_draft(item: dict, post: str) -> None:
    try:
        from workers.email_sender import notify

        body = (
            f"New LinkedIn post draft ready for review.\n\n"
            f"Built from: {item['title']}\n"
            f"Source: {item.get('url') or item.get('discussion_url')}\n\n"
            f"--- draft ---\n{post[:1200]}\n\n"
            f"Review, edit, and approve it in the dashboard (Content tab)."
        )
        notify(subject="New LinkedIn post draft ready", body=body)
    except Exception:  # noqa: BLE001
        pass


def _do_publish(post_id: str, body: str, account_id: str | None, card_b64: str | None = None) -> tuple[bool, str | None]:
    """Publish one post via Unipile (with its stat card, if any) and update its row."""
    image = None
    if card_b64:
        try:
            image = base64.b64decode(card_b64)
        except Exception:  # noqa: BLE001
            image = None
    try:
        resp = unipile.create_post(body, account_id=account_id, image=image)
        external_id = None
        if isinstance(resp, dict):
            external_id = resp.get("post_id") or resp.get("id") or resp.get("share_id")
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "update content_posts set status='posted', external_id=%s, "
                "posted_at=now(), error=null where id=%s",
                (str(external_id) if external_id else None, post_id),
            )
        try:
            from activity import log as _alog

            _alog("post_published", source="worker", channel="linkedin",
                  summary="Published a LinkedIn post", entity_type="content_post", entity_id=post_id)
        except Exception:  # noqa: BLE001
            pass
        # Golden-hour alert: the first 60-90 min engagement test (~7% of network) decides whether
        # the post gets extended distribution — the operator's replies/comments in that window are
        # the highest-leverage minutes of the day. This nudge is what makes auto-publish safe.
        try:
            from workers.email_sender import notify

            notify(
                subject="🚀 LinkedIn post is LIVE — golden hour starts now",
                body=(
                    "Your post just published. The next 60–90 minutes decide its reach "
                    "(LinkedIn tests it on ~7% of your network first).\n\n"
                    "Do these now for max distribution:\n"
                    "1. Reply to EVERY comment as it lands (comments count ~2x likes).\n"
                    "2. Spend 10–15 min leaving thoughtful comments on big accounts in your niche.\n"
                    "3. Don't edit the post in the first hour.\n\n"
                    f"--- your post ---\n{(body or '')[:600]}"
                ),
            )
        except Exception:  # noqa: BLE001
            pass
        return True, None
    except Exception as e:  # noqa: BLE001
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("update content_posts set status='failed', error=%s where id=%s",
                        (str(e)[:300], post_id))
        return False, str(e)[:200]


def _pace_ok(cur) -> tuple[bool, str]:
    """Algorithm-safe posting cadence (van der Blom 2025/26): the feed deduplicates same-creator
    posts and 8+/week degrades reach, so max ONE post per ~24h, weekday mornings PT only. Approved
    posts simply wait for the next window — nothing is dropped."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    if now.weekday() >= 5:
        return False, "weekend — next window is Monday morning"
    if not (13 <= now.hour < 19):  # 6am–noon PT
        return False, "outside the 6am–noon PT posting window"
    cur.execute("select max(posted_at) from content_posts where status = 'posted'")
    row = cur.fetchone()
    last = row[0] if row else None
    if last is not None and (now - last) < timedelta(hours=20):
        return False, "already posted in the last 20h (1/day cap)"
    return True, ""


def publish_approved(*, dry_run: bool = False, limit: int | None = None) -> dict[str, Any]:
    """Publish posts the operator approved in the dashboard, via Unipile (cron path).

    Paced: at most one post per run, inside the weekday-morning window, >=20h since the last —
    which lands at the researched optimum of ~4-5 posts/week without feed-dedup suppression.
    """
    with _connect() as conn, conn.cursor() as cur:
        if not dry_run:
            ok, why = _pace_ok(cur)
            if not ok:
                cur.execute("select count(*) from content_posts where status = 'approved'")
                queued = int(cur.fetchone()[0])
                return {"posted": 0, "failed": 0, "queued": queued, "paced": why}
        cur.execute(
            """
            select c.id, c.body, p.unipile_account_id, c.card_image
            from content_posts c
            left join profiles p on p.id = c.user_id
            where c.status = 'approved'
            order by c.created_at asc
            """
        )
        rows = cur.fetchall()
    if not dry_run:
        rows = rows[:1]  # one per day — the pace gate above enforces the 20h spacing
    if limit is not None:
        rows = rows[:limit]

    posted: list[str] = []
    failed: list[dict] = []
    for post_id, body, account_id, card_image in rows:
        if dry_run:
            posted.append(str(post_id))
            continue
        ok, err = _do_publish(str(post_id), body, account_id, card_image)
        (posted if ok else failed).append({"id": str(post_id), "error": err} if not ok else str(post_id))
    return {"published": len(posted), "failed": len(failed),
            "details": {"posted": posted, "failed": failed}, "dry_run": dry_run}


def publish_one(post_id: str | None) -> dict[str, Any]:
    """Publish a single post immediately (the dashboard's instant-publish path)."""
    if not post_id:
        return {"ok": False, "error": "missing post_id"}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select c.id, c.body, p.unipile_account_id, c.card_image from content_posts c "
            "left join profiles p on p.id = c.user_id where c.id = %s",
            (str(post_id),),
        )
        row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "post not found"}
    ok, err = _do_publish(str(row[0]), row[1], row[2], row[3])
    return {"ok": ok, "error": err}


def generate_build_post(text: str) -> dict[str, Any]:
    """Turn a description of something shipped into a build-in-public post draft."""
    text = (text or "").strip()
    if not text:
        return {"generated": False, "reason": "empty input"}
    try:
        result = claude.call_json(
            instruction=load_prompt("draft_build_post") + "\n\n" + load_prompt("linkedin_playbook"),
            user_payload=json.dumps({"shipped": text}),
            model=Config.claude_model_draft,
            max_tokens=900,
        )
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": str(e)[:200]}
    post = _sanitize((result or {}).get("post") or "")
    image_idea = _sanitize((result or {}).get("image_idea") or "")
    image_spec, card_b64 = _image_from(result)
    fmt = ((result or {}).get("format") or "").strip()[:40] or None
    if not post:
        return {"generated": False, "reason": "model returned an empty post"}
    title = text.splitlines()[0][:120] if text.splitlines() else "Build-in-public"
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into content_posts (source_kind, source_title, body, format, image_idea, card, card_image, status) "
            "values ('build', %s, %s, %s, %s, %s, %s, 'draft') returning id",
            (title, post, fmt, image_idea or None, Jsonb(image_spec) if image_spec else None, card_b64),
        )
        post_id = str(cur.fetchone()[0])
    return {"generated": True, "id": post_id}


# The free tools we own + can promote. A "tool_promo" post leads with genuine value and introduces
# one of these as the natural next step — free distribution pointed at our own funnel.
TOOL_PROMOS: dict[str, dict[str, str]] = {
    "audit": {
        "name": "AI Opportunity Audit",
        "url": "https://agentry.contentdrip.ai/audit",
        "what": "you drop your website and an agent returns the 3 highest-impact AI automations for "
        "your business, each with an honest time-savings estimate. about 30 seconds, no sales call.",
    },
    "roi": {
        "name": "AI Agent ROI Calculator",
        "url": "https://agentry.contentdrip.ai/roi-calculator",
        "what": "a few honest inputs (team size, hours on manual work, how much an agent can take "
        "over) return the hours and dollars AI agents could give your team back in a year. instant.",
    },
    "roast": {
        "name": "Roast My Cold Outreach",
        "url": "https://agentry.contentdrip.ai/roast",
        "what": "paste a cold email or LinkedIn message and get a brutally honest teardown of what is "
        "killing replies, plus a sharper rewrite. about 20 seconds.",
    },
}


def generate_tool_post(tool: str) -> dict[str, Any]:
    """Draft a value-first LinkedIn post that promotes one of our free tools (audit/roi/roast)."""
    spec = TOOL_PROMOS.get((tool or "").strip().lower())
    if not spec:
        return {"generated": False, "reason": f"unknown tool '{tool}'"}
    try:
        result = claude.call_json(
            instruction=load_prompt("draft_tool_post") + "\n\n" + load_prompt("linkedin_playbook"),
            user_payload=json.dumps({"tool": spec}, indent=2),
            model=Config.claude_model_draft,
            max_tokens=900,
        )
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": str(e)[:200]}
    post = _sanitize((result or {}).get("post") or "")
    image_idea = _sanitize((result or {}).get("image_idea") or "")
    image_spec, card_b64 = _image_from(result)
    fmt = ((result or {}).get("format") or "").strip()[:40] or None
    if not post:
        return {"generated": False, "reason": "model returned an empty post"}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into content_posts (source_kind, source_title, source_url, body, format, "
            "image_idea, card, card_image, status) "
            "values ('tool_promo', %s, %s, %s, %s, %s, %s, %s, 'draft') returning id",
            (spec["name"], spec["url"], post, fmt, image_idea or None,
             Jsonb(image_spec) if image_spec else None, card_b64),
        )
        post_id = str(cur.fetchone()[0])
    return {"generated": True, "id": post_id}


# Practitioner AI topics for viral-tweet discovery (X search operators are added in the client).
_TWEET_QUERIES = (
    "AI agents", "LLM", "AI coding", "prompt engineering", "building with AI",
    "AI automation", "AI startup", "Claude AI", "GPT",
)

# Engagement-farmed giveaways, course ads, and growth-hack tweets get huge likes but carry no
# insight worth reacting to. High-precision markers (curated to avoid common-word false positives
# like "of course") + the math-bold-unicode tell, a near-certain spam signal.
_SPAM_MARKERS = (
    # giveaways / engagement bait
    "free for first", "for first 4", "for first 1000", "100% free", "bookmark it now",
    "bookmark this", "rt + comment", "rt and comment", "like + rt", "dm me", "tag a friend",
    "tag someone", "link in bio", "link in comments", "giveaway", "follow me and",
    "comment below and", "drop a comment", "comment 'ai'", "reply 'ai'", "want the link",
    "i'll dm", "i will dm", "steal my", "for the next 24 hours", "follow for more",
    # course / info-product ads
    "ai course", "full course", "free course", "crash course", "my course", "this course",
    "paid course", "masterclass", "cohort", "webinar", "enroll", "sign up", "join my",
    "i teach", "newsletter", "subscribe", "step by step", "cheat sheet", "free template",
    "free guide", "free ebook", "use code", "promo code", "limited time", "spots left",
    "early access", "waitlist", "in 1 hour", "in one hour", "in 24 hours",
    # get-rich-quick
    "make money", "passive income", "side hustle", "6 figures", "7 figures",
)


def _looks_like_spam(text: str) -> bool:
    if any(0x1D400 <= ord(ch) <= 0x1D7FF for ch in text):  # math-bold/italic unicode = slop
        return True
    low = text.lower()
    return any(m in low for m in _SPAM_MARKERS)


def generate_tweet_reaction(*, dry_run: bool = False) -> dict[str, Any]:
    """Find a viral AI tweet, render it faithfully, and draft a LinkedIn post reacting to it.

    The rendered tweet (real text, author, like/retweet counts) becomes the post image; the
    drafted commentary adds the practitioner value that earns the follow. Needs XSEARCH_API_KEY.
    """
    from clients import xsearch

    if not xsearch.configured():
        return {"generated": False, "reason": "XSEARCH_API_KEY not set"}
    try:
        # "Top" viral tweets from the last ~3 months — recent enough to stay topical (AI moves fast),
        # wide enough to have real supply. content_seen dedupe (below) never repeats a tweet.
        tweets = xsearch.search_viral(_TWEET_QUERIES, min_likes=250, since_days=90)
    except Exception as e:  # noqa: BLE001
        return {"generated": False, "error": f"x search failed: {e}"}
    if not tweets:
        return {"generated": False, "reason": "no viral AI tweets found"}

    from workers.exemplars import _ai_relevant, top_exemplars

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select source_key from content_seen where source_key like 'tweet:%'")
        seen = {r[0] for r in cur.fetchall()}
        cur.execute(
            "select format from content_posts where created_at > now() - interval '14 days' "
            "order by created_at desc limit 5"
        )
        recent_formats = [r[0] for r in cur.fetchall() if r[0]]

    fresh = [
        t for t in tweets
        if f"tweet:{t['id']}" not in seen
        and 60 <= len(t["text"]) <= 600
        and _ai_relevant(t["text"])
        and t["author_handle"]
        and not _looks_like_spam(t["text"])
    ]
    if not fresh:
        return {"generated": False, "reason": "no fresh substantive AI tweets"}

    try:
        exemplars = top_exemplars(3)
    except Exception:  # noqa: BLE001
        exemplars = []

    chosen: dict | None = None
    post, fmt = "", None
    for t in fresh[:5]:  # try the top few until one yields a genuinely sharp take
        try:
            result = claude.call_json(
                instruction=load_prompt("draft_tweet_reaction") + "\n\n" + load_prompt("linkedin_playbook"),
                user_payload=json.dumps(
                    # Don't hand the model the like/retweet counts — it started citing them and
                    # dunking on low-number tweets. It reacts to the idea, not the metrics.
                    {"tweet": {k: t[k] for k in ("text", "author_name", "author_handle")},
                     "exemplars": exemplars, "avoid_formats": recent_formats},
                    indent=2,
                ),
                model=Config.claude_model_draft,
                max_tokens=1200,
            )
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(result, dict) or result.get("skip"):
            continue
        p = _sanitize(result.get("post") or "")
        if p:
            chosen, post = t, p
            fmt = (result.get("format") or "").strip()[:40] or None
            break

    if not chosen or not post:
        return {"generated": False, "reason": "no sharp reaction produced"}

    tweet_text = re.sub(r"\s*https?://t\.co/\S+", "", chosen["text"]).strip()  # drop ugly shortlinks
    tweet_spec = {
        "type": "tweet", "text": _sanitize(tweet_text),
        "name": chosen["author_name"] or chosen["author_handle"],
        "handle": chosen["author_handle"], "likes": chosen["likes"],
        "reposts": chosen["retweets"], "views": chosen.get("views"), "verified": chosen["verified"],
        # The original tweet's own photo(s), baked into the card below the text so the reaction
        # reproduces what people actually saw — the "Their build:" screenshot, not just the words.
        "media": chosen.get("media") or [],
    }
    try:
        png = render_image(tweet_spec)
        card_b64 = base64.b64encode(png).decode("ascii") if png else None
    except Exception:  # noqa: BLE001
        card_b64 = None

    title = f"Reacting to @{chosen['author_handle']}: {chosen['text'][:80]}"
    if dry_run:
        return {"generated": True, "dry_run": True, "source": title, "source_url": chosen["url"],
                "post": post, "format": fmt, "tweet_likes": chosen["likes"],
                "tweet_retweets": chosen["retweets"], "card_rendered": bool(card_b64)}

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into content_posts (source_kind, source_title, source_url, body, format, card, card_image, status) "
            "values ('tweet', %s, %s, %s, %s, %s, %s, 'draft') returning id",
            (title[:300], chosen["url"] or None, post, fmt, Jsonb(tweet_spec), card_b64),
        )
        post_id = str(cur.fetchone()[0])
        cur.execute(
            "insert into content_seen (source_key, title) values (%s,%s) on conflict (source_key) do nothing",
            (f"tweet:{chosen['id']}", chosen["text"][:200]),
        )

    _notify_draft({"title": title, "url": chosen["url"]}, post)
    return {"generated": True, "id": post_id, "source": title,
            "tweet_likes": chosen["likes"], "tweet_retweets": chosen["retweets"]}
