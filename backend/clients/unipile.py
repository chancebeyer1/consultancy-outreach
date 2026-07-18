"""Unipile client — one unified API for LinkedIn + email.

Replaces three old clients:
  * heyreach.py   (LinkedIn invitations / DMs / inbox)
  * smartlead.py  (email sending)
  * proxycurl.py  (LinkedIn profile + post enrichment)

Connected-account model: you connect a LinkedIn account and a mailbox once in the
Unipile dashboard; each is assigned an `account_id`. We keep those in config and
pass them on every call. v1 assumes a single LinkedIn account + single mailbox.

Auth:  header `X-API-KEY: <access token>`
Base:  your dashboard DSN, e.g.  https://api1.unipile.com:13111/api/v1
Docs:  https://developer.unipile.com

Endpoint shapes were confirmed against the API reference, but Unipile evolves —
if a call 4xxs after an upstream change, check developer.unipile.com and adjust.
LinkedIn chat + email endpoints take multipart/form-data; invite takes JSON.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import require


# ---------------------------------------------------------------------------
# request plumbing
# ---------------------------------------------------------------------------

def _is_transient(exc: BaseException) -> bool:
    """Retry only transient failures. A 4xx (e.g. 422 `cannot_resend_yet` when the
    LinkedIn invite limit is hit, or 400 bad request) won't change on retry, so
    surface it to the caller immediately instead of burning 3 backoff attempts."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.TransportError))


# Retry transient errors only, and re-raise the ORIGINAL exception (not tenacity's
# RetryError) once attempts are exhausted, so callers can inspect `exc.response`.
_RETRY = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)


def _base() -> str:
    dsn = require("UNIPILE_DSN").rstrip("/")
    if not dsn.startswith("http"):
        dsn = f"https://{dsn}"
    return f"{dsn}/api/v1"


def _headers() -> dict[str, str]:
    return {"X-API-KEY": require("UNIPILE_API_KEY"), "accept": "application/json"}


def _li_account() -> str:
    return require("UNIPILE_LINKEDIN_ACCOUNT_ID")


# Connection-invite note limit. LinkedIn's standard cap is 300 chars; verified empirically on
# 2026-06-29 that this account accepts 225- and 265-char notes (the earlier 200 cap was an
# over-correction). Over-long notes get rejected with errors/too_many_characters, so we still
# truncate at a sentence/word boundary as a safety net.
INVITE_NOTE_LIMIT = 300


def _invite_note(msg: str | None, limit: int = INVITE_NOTE_LIMIT) -> str:
    msg = (msg or "").strip()
    if len(msg) <= limit:
        return msg
    cut = msg[:limit]
    for sep in (". ", "! ", "? "):
        i = cut.rfind(sep)
        if i >= limit * 0.55:
            return cut[: i + 1].strip()
    i = cut.rfind(" ")
    return (cut[:i] if i > limit * 0.55 else cut).strip()


def _email_account() -> str:
    return require("UNIPILE_EMAIL_ACCOUNT_ID")


def _form(fields: dict[str, Any]) -> dict[str, tuple[None, str]]:
    """Encode plain fields as multipart/form-data parts (no real files).

    Passing these via httpx `files=` forces multipart encoding, which the
    chat/email endpoints require. None values are dropped.
    """
    return {k: (None, str(v)) for k, v in fields.items() if v is not None}


def public_identifier(linkedin_url: str) -> str:
    """Extract the LinkedIn public id from a profile URL.

    https://www.linkedin.com/in/jane-doe-123/      -> jane-doe-123
    https://www.linkedin.com/sales/people/abc,NAME -> abc
    """
    path = urlparse(linkedin_url).path.strip("/")
    parts = [p for p in path.split("/") if p]
    if "in" in parts:
        i = parts.index("in")
        if i + 1 < len(parts):
            return parts[i + 1].split(",")[0]
    return (parts[-1].split(",")[0] if parts else linkedin_url)


# ---------------------------------------------------------------------------
# enrichment  (replaces proxycurl.fetch_profile / fetch_recent_posts)
# ---------------------------------------------------------------------------

@_RETRY
def fetch_profile(
    linkedin_url: str, *, notify: bool = False, account_id: str | None = None
) -> dict[str, Any]:
    """Retrieve a LinkedIn profile.  GET /users/{identifier}?account_id=…

    `notify=False` avoids leaving a "viewed your profile" footprint during
    enrichment. The response is Unipile's profile shape — normalize downstream.
    `account_id` defaults to the global connected account (multi-user: pass the
    lead-owner's account so the lookup runs from their session).
    """
    ident = public_identifier(linkedin_url)
    params = {"account_id": account_id or _li_account(), "notify": str(notify).lower()}
    # follow_redirects: Unipile 301s /users/{id} -> /users/{id}/ when the identifier contains
    # percent-encoded UTF-8 (e.g. 'isahi-pe%C3%B1a-…'); httpx surfaces that as an error by
    # default, which failed real connect sends. Safe here — GET only.
    with httpx.Client(timeout=60.0, follow_redirects=True) as c:
        r = c.get(f"{_base()}/users/{ident}", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


@_RETRY
def fetch_recent_posts(
    linkedin_url: str, count: int = 10, *, account_id: str | None = None
) -> list[dict[str, Any]]:
    """Recent posts/activity.  GET /users/{identifier}/posts?account_id=…

    Returns [] on 404 (profile has no surfaced activity). `account_id` defaults to
    the global connected account (multi-user passes the lead owner's).
    """
    ident = public_identifier(linkedin_url)
    params = {"account_id": account_id or _li_account(), "limit": count}
    # follow_redirects: same non-ASCII-identifier 301 as fetch_profile (GET only, safe).
    with httpx.Client(timeout=60.0, follow_redirects=True) as c:
        r = c.get(f"{_base()}/users/{ident}/posts", headers=_headers(), params=params)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
        return data.get("items", data) if isinstance(data, dict) else data


def provider_id_from_profile(profile: dict[str, Any] | None) -> str | None:
    """Extract the LinkedIn member id (ACoAA… urn) from a stored profile — no network
    call. Returns None if absent. Excludes public_identifier (the /in/ slug), which is
    NOT the member id that inbound replies are keyed by.
    """
    if not isinstance(profile, dict):
        return None
    for key in ("provider_id", "id", "member_id", "entity_urn"):
        val = profile.get(key)
        if val:
            return str(val)
    return None


def resolve_provider_id(
    linkedin_url: str, *, profile: dict[str, Any] | None = None, account_id: str | None = None
) -> str:
    """The provider-internal id required to invite / message a user.

    Pulled from a profile payload (fetched if not supplied). `account_id` selects which
    connected account performs the lookup (defaults to the global account).
    """
    p = profile if profile is not None else fetch_profile(linkedin_url, account_id=account_id)
    for key in ("provider_id", "id", "member_id", "entity_urn", "public_identifier"):
        val = p.get(key)
        if val:
            return str(val)
    raise RuntimeError(f"No provider_id found in Unipile profile for {linkedin_url}")


# ---------------------------------------------------------------------------
# search / sourcing  (LinkedIn + Sales Navigator people search)
# ---------------------------------------------------------------------------

def _normalize_search_item(it: dict[str, Any]) -> dict[str, Any] | None:
    """Map one Unipile people-search result onto the lead shape run_pipeline reads.

    Unipile result fields can drift; this is the single choke point. Observed keys:
    public_identifier, profile_url, name / first_name / last_name, headline,
    location, current_positions: [{company, role, tenure_at_company}].
    """
    if not isinstance(it, dict):
        return None
    pub = it.get("public_identifier") or it.get("public_id")
    # Prefer the canonical /in/<slug> URL so enrichment + dedup stay consistent
    # across classic (returns /in/) and Sales Navigator (returns /sales/) results.
    url = (
        (f"https://www.linkedin.com/in/{pub}" if pub else None)
        or it.get("public_profile_url")
        or it.get("profile_url")
    )
    if not url:
        return None
    name = it.get("name") or " ".join(
        p for p in (it.get("first_name"), it.get("last_name")) if p
    ) or None
    company = role = None
    positions = it.get("current_positions") or it.get("positions")
    if isinstance(positions, list) and positions and isinstance(positions[0], dict):
        company = positions[0].get("company") or positions[0].get("company_name")
        role = positions[0].get("role") or positions[0].get("title")
    return {
        "linkedin_url": url,
        "name": name,
        "headline": it.get("headline"),
        "company": company,
        "role": role or it.get("headline"),
        "location": it.get("location"),
    }


@_RETRY
def search_people(
    *,
    search_url: str | None = None,
    params: dict[str, Any] | None = None,
    account_id: str | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """One page of a LinkedIn / Sales-Navigator people search.

    POST /linkedin/search?account_id=…  — pass EITHER a saved search `search_url`
    copied from the browser (classic OR Sales Navigator; the URL overrides the body)
    OR a structured `params` dict. Sales-Navigator searches require a Sales Navigator
    seat on the connected account.

    Returns {"items": [normalized leads], "cursor": <next cursor or None>}. Paginate
    by passing the returned cursor back in as `cursor`.
    """
    if not search_url and not params:
        raise ValueError("search_people needs either search_url or params")
    q: dict[str, Any] = {"account_id": account_id or _li_account()}
    if cursor:
        q["cursor"] = cursor
    body: dict[str, Any] = {"url": search_url} if search_url else dict(params)
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/linkedin/search", headers=_headers(), params=q, json=body)
        r.raise_for_status()
        data = r.json()
    raw = data.get("items", []) if isinstance(data, dict) else (data or [])
    items = [x for x in (_normalize_search_item(i) for i in raw) if x]
    next_cursor = data.get("cursor") if isinstance(data, dict) else None
    return {"items": items, "cursor": next_cursor}


@_RETRY
def search_posts(keywords: str, *, account_id: str | None = None, cursor: str | None = None) -> dict[str, Any]:
    """Search LinkedIn posts by keyword.  POST /linkedin/search (category=posts).

    Returns {"items": [{social_id, text, reactions, comments, reposts, impressions,
    author_name, author_headline, url, date, is_job}], "cursor"}. Engagement counts let us
    rank for what actually went viral.
    """
    q: dict[str, Any] = {"account_id": account_id or _li_account()}
    if cursor:
        q["cursor"] = cursor
    body = {"api": "classic", "category": "posts", "keywords": keywords}
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/linkedin/search", headers=_headers(), params=q, json=body)
        r.raise_for_status()
        data = r.json()
    raw = data.get("items", []) if isinstance(data, dict) else (data or [])
    items: list[dict[str, Any]] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        author = p.get("author") or {}
        items.append({
            "social_id": p.get("social_id") or p.get("id"),
            "text": p.get("text") or "",
            "reactions": int(p.get("reaction_counter") or 0),
            "comments": int(p.get("comment_counter") or 0),
            "reposts": int(p.get("repost_counter") or 0),
            "impressions": int(p.get("impressions_counter") or 0),
            "author_name": author.get("name"),
            "author_headline": author.get("headline"),
            "url": p.get("share_url"),
            "date": p.get("parsed_datetime") or p.get("date"),
            "is_job": bool(p.get("job_posting")),
        })
    return {"items": items, "cursor": data.get("cursor") if isinstance(data, dict) else None}


@_RETRY
def search_parameters(
    param_type: str, keywords: str, *, limit: int = 10, account_id: str | None = None
) -> list[dict[str, Any]]:
    """Resolve Sales-Navigator filter IDs by keyword.  GET /linkedin/search/parameters

    `param_type` is the filter to resolve — e.g. "INDUSTRY", "LOCATION", "COMPANY",
    "SCHOOL". Returns [{"id", "title"}, …]. Used to turn human names ("Insurance",
    "United States") into the numeric ids the structured people-search body needs
    for its `industry` / `location` filters. `account_id` defaults to the global account.
    """
    q = {"account_id": account_id or _li_account(), "type": param_type, "keywords": keywords, "limit": limit}
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{_base()}/linkedin/search/parameters", headers=_headers(), params=q)
        r.raise_for_status()
        data = r.json()
    return data.get("items", []) if isinstance(data, dict) else (data or [])


@_RETRY
def list_relations(
    *, cursor: str | None = None, limit: int = 100, account_id: str | None = None
) -> dict[str, Any]:
    """One page of the account's 1st-degree connections.  GET /users/relations

    `member_id` is the LinkedIn member urn (ACoAA…) we match leads on for
    connection-acceptance detection. Returns {"items": [{provider_id,
    public_identifier, name}], "cursor": <next or None>} — relations come back
    most-recent-first, so newly-accepted connections are on the first pages.
    `account_id` selects whose connections to page (defaults to the global account).
    """
    params: dict[str, Any] = {"account_id": account_id or _li_account(), "limit": limit}
    if cursor:
        params["cursor"] = cursor
    with httpx.Client(timeout=60.0) as c:
        r = c.get(f"{_base()}/users/relations", headers=_headers(), params=params)
        r.raise_for_status()
        data = r.json()
    raw = data.get("items", []) if isinstance(data, dict) else (data or [])
    items: list[dict[str, Any]] = []
    for it in raw:
        pid = it.get("member_id") or it.get("provider_id")
        if not pid:
            continue
        name = " ".join(p for p in (it.get("first_name"), it.get("last_name")) if p) or None
        items.append(
            {"provider_id": str(pid), "public_identifier": it.get("public_identifier"), "name": name}
        )
    return {"items": items, "cursor": data.get("cursor") if isinstance(data, dict) else None}


def list_sent_invitations(
    *, account_id: str | None = None, max_pages: int = 40, budget_s: float | None = None
) -> list[dict[str, Any]]:
    """All OUTSTANDING (pending/unaccepted) sent invitations.  GET /users/invite/sent

    LinkedIn throttles new invites once too many are left pending (422
    cannot_resend_yet / "temporary provider limit"), and that ceiling counts the
    operator's own old manual invites too — which our send-rate quota can't see.
    This is the input to the pending-invite guard and the stale-invite withdrawal.

    Returns a list of {id, sent_at, name, public_id, member_id, text}, newest first.
    """
    acct = account_id or _li_account()
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    # `budget_s` caps the WALL CLOCK of the whole pagination walk: 40 pages x 60s timeout each
    # is unbounded-in-practice when Unipile is slow/502ing, and callers on a watchdog (the
    # send-run pending-invite guard) hung on exactly that. Hitting the budget returns a
    # PARTIAL list — callers that need an exact count must pass budget_s=None.
    deadline = (time.monotonic() + budget_s) if budget_s else None
    with httpx.Client(timeout=60.0) as c:
        for _ in range(max_pages):
            if deadline is not None and time.monotonic() > deadline:
                break
            params: dict[str, Any] = {"account_id": acct, "limit": 100}
            if cursor:
                params["cursor"] = cursor
            r = c.get(f"{_base()}/users/invite/sent", headers=_headers(), params=params)
            r.raise_for_status()
            data = r.json()
            items = data.get("items", []) if isinstance(data, dict) else (data or [])
            if not items:
                break
            for it in items:
                inv_id = it.get("id")
                if not inv_id:
                    continue
                out.append(
                    {
                        "id": str(inv_id),
                        "sent_at": it.get("parsed_datetime"),  # ISO8601 or None
                        "name": it.get("invited_user"),
                        "public_id": it.get("invited_user_public_id"),
                        "member_id": it.get("invited_user_id"),
                        "text": it.get("invitation_text"),
                    }
                )
            cursor = data.get("cursor") if isinstance(data, dict) else None
            if not cursor:
                break
    return out


@_RETRY
def cancel_invitation(invitation_id: str, *, account_id: str | None = None) -> dict[str, Any]:
    """Withdraw a pending sent invitation.  DELETE /users/invite/sent/{id}?account_id=

    Frees headroom under LinkedIn's pending-invite ceiling (a pile of old unaccepted invites
    blocks new ones). NOTE: LinkedIn imposes a ~3-week lockout before you can re-invite the same
    person, so only withdraw invites old enough to be effectively dead. 200 = withdrawn; a 404
    means it's already gone (accepted or expired) — the caller treats that as success.
    """
    q = {"account_id": account_id or _li_account()}
    with httpx.Client(timeout=30.0) as c:
        r = c.delete(f"{_base()}/users/invite/sent/{invitation_id}", headers=_headers(), params=q)
        if r.status_code == 404:
            return {"ok": True, "already_gone": True}
        r.raise_for_status()
        return r.json() if r.content else {"ok": True}


# ---------------------------------------------------------------------------
# sending  (replaces heyreach.add_leads_to_campaign + smartlead.add_leads_to_campaign)
# ---------------------------------------------------------------------------

@_RETRY
def send_linkedin_invitation(
    provider_id: str, message: str, *, user_email: str | None = None, account_id: str | None = None
) -> dict[str, Any]:
    """Send a connection request, with or without a note.  POST /users/invite (JSON).

    `message` is truncated to LinkedIn's 300-char invite-note limit. An EMPTY message sends a
    no-note invite (the field is omitted entirely — variant "c" of the connect A/B; benchmarks
    show no-note invites accept slightly HIGHER). `account_id` is the sending account (defaults
    to the global account; multi-user passes the lead owner's).
    """
    body: dict[str, Any] = {
        "account_id": account_id or _li_account(),
        "provider_id": provider_id,
    }
    note = _invite_note(message)
    if note:
        body["message"] = note
    if user_email:
        body["user_email"] = user_email
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/users/invite", headers=_headers(), json=body)
        if r.is_error:  # surface Unipile's real reason (e.g. too_many_characters), not a generic 400
            raise httpx.HTTPStatusError(
                f"invite {r.status_code}: {r.text[:300]}", request=r.request, response=r
            )
        return r.json()


@_RETRY
def withdraw_invitation(invitation_id: str, *, account_id: str | None = None) -> dict[str, Any]:
    """Withdraw a pending sent invitation.  DELETE /users/invite/sent/{id}

    Used to clear stale/never-accepted invites that count against LinkedIn's
    pending-invitation ceiling. `invitation_id` is the `id` from
    list_sent_invitations(). Note: LinkedIn enforces a ~3-week cooldown before
    you can re-invite someone whose invite you withdrew.
    """
    acct = account_id or _li_account()
    with httpx.Client(timeout=60.0) as c:
        r = c.request(
            "DELETE",
            f"{_base()}/users/invite/sent/{invitation_id}",
            headers=_headers(),
            params={"account_id": acct},
        )
        if r.is_error:
            raise httpx.HTTPStatusError(
                f"withdraw {r.status_code}: {r.text[:300]}", request=r.request, response=r
            )
        return r.json() if r.text.strip() else {"ok": True}


@_RETRY
def send_linkedin_message(
    provider_id: str, text: str, *, account_id: str | None = None
) -> dict[str, Any]:
    """DM a connection by starting (or reusing) a chat.  POST /chats (multipart).

    Returns at least {chat_id, message_id}. `account_id` defaults to the global account.
    """
    fields = _form({"account_id": account_id or _li_account(), "attendees_ids": provider_id, "text": text})
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/chats", headers=_headers(), files=fields)
        r.raise_for_status()
        return r.json()


@_RETRY
def send_linkedin_inmail(
    provider_id: str, text: str, *, account_id: str | None = None
) -> dict[str, Any]:
    """Send a LinkedIn InMail to a NON-connection.  POST /chats (multipart).

    Reaches a prospect directly without a connection request, skipping the
    accept-wait. Requires Sales Navigator / Recruiter InMail credits on the
    connected account (`linkedin[inmail]=true`, `linkedin[api]=sales_navigator`).
    Each send consumes one credit; check inmail_balance() before a batch.
    `account_id` defaults to the global account (multi-user passes the owner's).
    """
    fields = _form(
        {
            "account_id": account_id or _li_account(),
            "attendees_ids": provider_id,
            "text": text,
            "linkedin[api]": "sales_navigator",
            "linkedin[inmail]": "true",
        }
    )
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/chats", headers=_headers(), files=fields)
        r.raise_for_status()
        return r.json()


@_RETRY
def inmail_balance(*, account_id: str | None = None) -> dict[str, Any]:
    """Remaining InMail credits per tier.  GET /linkedin/inmail_balance

    Returns {premium, recruiter, sales_navigator} — credit counts or null when
    that tier isn't active on the account. `account_id` defaults to the global account.
    """
    params = {"account_id": account_id or _li_account()}
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{_base()}/linkedin/inmail_balance", headers=_headers(), params=params)
        r.raise_for_status()
        return r.json()


@_RETRY
def send_chat_message(
    chat_id: str, text: str, *, account_id: str | None = None
) -> dict[str, Any]:
    """Reply in an existing chat.  POST /chats/{chat_id}/messages (multipart).

    `account_id` must be the account the chat lives on (defaults to the global
    account; multi-user passes the lead owner's).
    """
    fields = _form({"account_id": account_id or _li_account(), "text": text})
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/chats/{chat_id}/messages", headers=_headers(), files=fields)
        r.raise_for_status()
        return r.json()


@_RETRY
def create_post(
    text: str, *, account_id: str | None = None, external_link: str | None = None,
    image: bytes | None = None, image_name: str = "card.png",
) -> dict[str, Any]:
    """Publish a post to the connected account's feed (LinkedIn share).  POST /posts (multipart).

    `account_id` defaults to the global account (multi-user passes the author's). `external_link`
    adds a preview card. `image` (PNG bytes) attaches a visual. Returns the created post payload
    (post / share id). 201 = published.
    """
    fields: dict[str, Any] = {"account_id": account_id or _li_account(), "text": text}
    if external_link:
        fields["external_link"] = external_link
    files = _form(fields)
    if image:
        files["attachments"] = (image_name, image, "image/png")
    with httpx.Client(timeout=90.0) as c:
        r = c.post(f"{_base()}/posts", headers=_headers(), files=files)
        r.raise_for_status()
        return r.json()


@_RETRY
def comment_on_post(
    social_id: str, text: str, *, account_id: str | None = None,
) -> dict[str, Any]:
    """Comment on a LinkedIn post.  POST /posts/{social_id}/comments (JSON).

    `social_id` MUST be the post's `social_id` (the urn:li:activity:… form that `search_posts`
    returns) — LinkedIn exposes several ids for one post and only the social_id is reliable across
    action endpoints. Returns the created-comment payload. Used by the growth comment pacer, which
    posts operator-approved comments one at a time across the day (never in a bulk burst — LinkedIn
    visibility-limits comments it detects as automated).
    """
    body = {"account_id": account_id or _li_account(), "text": text}
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/posts/{social_id}/comments", headers=_headers(), json=body)
        r.raise_for_status()
        return r.json() if r.content else {"ok": True}


@_RETRY
def send_email(
    to_email: str, subject: str, body: str, *, display_name: str | None = None,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Send an email from the connected mailbox.  POST /emails (multipart).

    Returns at least {tracking_id, provider_id}. `account_id` defaults to the global
    email account (multi-user passes the sender's connected mailbox account).
    """
    recipient: dict[str, str] = {"identifier": to_email}
    if display_name:
        recipient["display_name"] = display_name
    fields = _form(
        {
            "account_id": account_id or _email_account(),
            "to": json.dumps([recipient]),
            "subject": subject,
            "body": body,
        }
    )
    with httpx.Client(timeout=60.0) as c:
        r = c.post(f"{_base()}/emails", headers=_headers(), files=fields)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# inbox / replies  (replaces heyreach.list_inbox_conversations / list_conversation_messages)
# ---------------------------------------------------------------------------

@_RETRY
def list_chats(
    *, unread_only: bool = True, limit: int = 100, account_id: str | None = None
) -> list[dict[str, Any]]:
    """LinkedIn chats.  GET /chats?account_id=&account_type=LINKEDIN&unread=

    Each chat: {id, account_id, account_type, provider_id, name, timestamp,
    unread_count, …}. `account_id` selects whose inbox to list (defaults to the
    global account).
    """
    params: dict[str, Any] = {
        "account_id": account_id or _li_account(),
        "account_type": "LINKEDIN",
        "limit": limit,
    }
    if unread_only:
        params["unread"] = "true"
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{_base()}/chats", headers=_headers(), params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("items", data) if isinstance(data, dict) else data


@_RETRY
def list_chat_messages(chat_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    """GET /chats/{chat_id}/messages

    Each message: {id, text, timestamp, is_sender (0|1), sender_id, …}.
    is_sender==0 marks an inbound (prospect) message.
    """
    params = {"limit": limit}
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{_base()}/chats/{chat_id}/messages", headers=_headers(), params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("items", data) if isinstance(data, dict) else data


@_RETRY
def list_emails(
    *, role: str = "inbox", limit: int = 100, account_id: str | None = None
) -> list[dict[str, Any]]:
    """GET /emails?account_id=&role=inbox

    Each email: {id, from_attendee:{identifier,display_name}, subject, body,
    body_plain, date, read_date (null ⇒ unread), …}. `account_id` selects which
    connected mailbox to list (defaults to the global email account).
    """
    params = {"account_id": account_id or _email_account(), "role": role, "limit": limit}
    with httpx.Client(timeout=30.0) as c:
        r = c.get(f"{_base()}/emails", headers=_headers(), params=params)
        r.raise_for_status()
        data = r.json()
        return data.get("items", data) if isinstance(data, dict) else data


def health() -> dict[str, Any]:
    """Connectivity check — lists connected accounts.  GET /accounts"""
    with httpx.Client(timeout=15.0) as c:
        r = c.get(f"{_base()}/accounts", headers=_headers())
        r.raise_for_status()
        return r.json()
