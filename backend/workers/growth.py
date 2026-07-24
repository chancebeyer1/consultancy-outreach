"""LinkedIn growth engine — daily comment-target queue.

The research-backed way to grow a small account: leave thoughtful comments on LARGE in-niche posts
(strategic commenting shapes the algorithm's topic fingerprint for your account AND puts you in
front of big audiences; comments weigh ~2x likes). LinkedIn visibility-limits comments it detects
as automated (Aug 2025 policy), so we never bulk-post: this worker finds today's best posts, drafts
an in-voice comment for each, and QUEUES them for one-click approval (comment_queue). The operator
approves in the dashboard (/comments); a pacer (workers/comment_pacer.py) then posts the approved
comments one at a time, spread across weekday business hours with random holds — a human cadence,
not a bot burst.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg

from clients import claude, unipile
from config import Config, require
from operator_profile import operator_bio
from prompts_loader import load_prompt

# Rotate the niche query by weekday so the digest doesn't tunnel on one phrase.
KEYWORDS = [
    "AI agents",
    "AI automation business",
    "building AI agents",
    "AI agents production",
    "LLM automation",
]

MIN_REACTIONS = 5    # floor — search surfaces RECENT posts, and commenting early on a rising post
                     # beats being comment #400 on an old viral one (early engagement window)
MAX_TARGETS = 6      # a 15-minute daily habit, not a chore
SEARCH_PAGES = 4     # ~10 results/page; pool a few pages before ranking


def _connect():
    return psycopg.connect(require("DATABASE_URL"))


def _humanize(text: str | None) -> str:
    """Strip the punctuation that screams 'AI wrote this'. The em/en dash is the biggest tell, so
    replace a dash (and any spaces around it) with a comma, then tidy up. Belt-and-suspenders with
    the prompt ban — guarantees no dash reaches the queue even if the model slips."""
    t = re.sub(r"\s*[—–]\s*", ", ", text or "")
    t = re.sub(r",\s*,", ", ", t)              # collapse any doubled comma
    t = re.sub(r",\s*([.!?;:])", r"\1", t)     # ", ." -> "."
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


# Recruitment / job-ad posts pollute the growth queue: a technical comment on a hiring post is
# off-key and wins no visibility. LinkedIn's is_job flag only catches FORMAL job postings, not a
# recruiter posting a req as plain text, so we also sniff the post text + the author's headline.
_RECRUIT_TEXT = re.compile(
    r"\b(hiring|now hiring|we[’']?re hiring|we are hiring|actively hiring|urgently hiring|"
    r"open role|open roles|open position|open positions|job opening|openings|vacanc|"
    r"apply (now|here|via|at|through|below)|send (your |me your )?(resume|cv)|"
    r"share your (resume|cv)|dm your (resume|cv)|drop your (resume|cv)|"
    r"yrs of exp|years of exp|notice period|immediate joiner|c2c|corp to corp|w2 contract|"
    r"job description|talent acquisition|client is looking for|urgent requirement)\b",
    re.I,
)
_RECRUIT_HEADLINE = re.compile(
    r"\b(recruit|recruitment|recruiter|talent acquisition|staffing|sourcer)\b", re.I
)


def _is_recruitment(p: dict) -> bool:
    """True if a post is a hiring/recruitment ad — skip it (a growth comment there is off-key)."""
    if _RECRUIT_HEADLINE.search(p.get("author_headline") or ""):
        return True
    return bool(_RECRUIT_TEXT.search(p.get("text") or ""))


def comment_digest(*, dry_run: bool = False) -> dict[str, Any]:
    """Find today's best in-niche posts, draft a comment for each, email the digest."""
    kw = KEYWORDS[datetime.now(UTC).date().toordinal() % len(KEYWORDS)]
    items: list[dict[str, Any]] = []
    cursor = None
    for _ in range(SEARCH_PAGES):
        try:
            res = unipile.search_posts(kw, cursor=cursor)
        except Exception as e:  # noqa: BLE001
            if not items:
                return {"sent": False, "error": f"search failed: {str(e)[:160]}"}
            break
        page = res.get("items", []) if isinstance(res, dict) else []
        items.extend(page)
        cursor = res.get("cursor") if isinstance(res, dict) else None
        if not cursor or not page:
            break

    # Filter: real posts (not jobs) with enough text to say something specific about, and at
    # least a pulse of engagement.
    cands = [
        p for p in items
        if not p.get("is_job")
        and not _is_recruitment(p)
        and len(p.get("text") or "") > 120
        and (p.get("reactions") or 0) + (p.get("comments") or 0) >= MIN_REACTIONS
    ]
    if not cands:
        return {"sent": False, "reason": f"no posts with traction for '{kw}' ({len(items)} scanned)"}

    # Skip posts already queued (any status) or suggested by the legacy digest ledger.
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("select social_id from comment_queue")
        seen = {r[0] for r in cur.fetchall()}
        cur.execute("select source_key from content_seen where source_key like 'cmt:%'")
        seen |= {r[0].split(":", 1)[1] for r in cur.fetchall()}  # 'cmt:<social_id>' → social_id
    fresh = [p for p in cands if p.get("social_id") not in seen]
    if not fresh:
        return {"queued": 0, "reason": "all candidates already queued"}

    # Rank by engagement (comments weigh double — they mark conversation posts) and take the top.
    fresh.sort(key=lambda p: (p.get("reactions") or 0) + 2 * (p.get("comments") or 0), reverse=True)
    targets = fresh[:MAX_TARGETS]

    # Draft all comments in one call, grounded in the operator's real background.
    payload = json.dumps(
        {
            "operator_background": operator_bio(),
            "posts": [
                {"social_id": p.get("social_id"), "author": p.get("author_name"),
                 "author_headline": (p.get("author_headline") or "")[:120],
                 "text": (p.get("text") or "")[:900]}
                for p in targets
            ],
        },
        default=str, indent=2,
    )
    try:
        drafted = claude.call_json(
            instruction=load_prompt("draft_growth_comments"),
            user_payload=payload,
            model=Config.claude_model_draft,
            temperature=0.6,
            max_tokens=1500,
        )
    except Exception as e:  # noqa: BLE001
        return {"sent": False, "error": f"drafting failed: {str(e)[:160]}"}
    by_id = {d.get("social_id"): _humanize(d.get("comment")) for d in drafted if isinstance(d, dict)} \
        if isinstance(drafted, list) else {}

    # Build a compact review list for the heads-up email (full review happens in the dashboard).
    lines: list[str] = []
    for i, p in enumerate(targets, 1):
        cmt = by_id.get(p.get("social_id"))
        if not cmt:
            continue
        lines += [
            f"#{i} — {p.get('author_name')} · {p.get('reactions', 0)} reactions, "
            f"{p.get('comments', 0)} comments",
            f"   {p.get('url') or '(open LinkedIn)'}",
            f"   → {cmt}",
            "",
        ]
    preview = "\n".join(lines)

    if dry_run:
        return {"queued": 0, "dry_run": True, "keyword": kw, "targets": len(targets),
                "preview": preview[:600]}

    # Queue each drafted comment pre-approved; the pacer (workers/comment_pacer.py) drips them
    # out across the day, and /comments stays the place to reject one before it posts.
    queued = 0
    with _connect() as conn, conn.cursor() as cur:
        for p in targets:
            sid, cmt = p.get("social_id"), by_id.get(p.get("social_id"))
            if not sid or not cmt:
                continue
            cur.execute(
                # status='approved' on insert (2026-07-23, operator-requested auto-approve): the
                # recruitment-post gate + em-dash humanize already ran upstream, and the pacer's
                # 1/hr weekday drip leaves a review window in /comments to reject before it posts.
                "insert into comment_queue (social_id, post_url, author_name, author_headline, "
                "post_excerpt, reactions, comments, keyword, body, status, approved_at) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved',now()) on conflict (social_id) do nothing",
                (sid, p.get("url"), p.get("author_name"), (p.get("author_headline") or "")[:200],
                 (p.get("text") or "")[:280], int(p.get("reactions") or 0),
                 int(p.get("comments") or 0), kw, cmt),
            )
            queued += cur.rowcount
        conn.commit()

    if not queued:
        return {"queued": 0, "keyword": kw, "reason": "drafted posts were all already queued"}

    from workers.email_sender import notify

    dash = "https://linkedin-outreach-dun-eta.vercel.app/comments"
    body = (
        f"{queued} LinkedIn comment{'s' if queued != 1 else ''} drafted — posts pulling engagement "
        f"in \"{kw}\" right now.\n\n"
        f"Review + approve (one click each, or approve all):\n{dash}\n\n"
        "Approved comments post automatically, spaced across the day at good times — never all at "
        "once — so the activity reads as human.\n\n"
        f"{preview}"
    )
    r = notify(subject=f"{queued} LinkedIn comments to approve", body=body)
    return {"queued": queued, "keyword": kw, "sent": bool(r.get("sent"))}
