"""Freelancer.com active-project search — the self-serve freelance-gig source.

Unlike Upwork (application + review gate), Freelancer.com issues credentials directly:
log in → https://accounts.freelancer.com/settings/create_app → create an app → mint a token
(read-only search needs only the `basic` scope). Live the moment FREELANCER_OAUTH_TOKEN is
set. Rates skew lower and more contested than Upwork, but it's real biddable contract work
with zero approval latency.

API: https://developers.freelancer.com — REST, `Freelancer-OAuth-V1: <token>` header (a bare
custom header, not Authorization: Bearer). Endpoint verified live 2026-07:
GET /api/projects/0.1/projects/active/   (active = open for bidding; result.projects[])

ToS notes: no published numeric rate limit (429 on abuse — tenacity backoff covers it);
cached data must be refreshed at least every 24h (our daily sweep satisfies this); personal
read-only search is squarely permitted. Bidding happens BY HAND on the site (consistent
with the module's never-auto-submit rule).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import Config

_BASE = "https://www.freelancer.com/api/projects/0.1/projects/active/"

# Skill ("job") IDs, verified against the live /jobs/ endpoint: ML=292, AI=913,
# Deep Learning=1601, Chatbot=2068, AI Chatbot Development=2916, Python=13,
# Software Development=613. The AI-specific tags carry the targeting; the fit-scorer
# does the fine filtering.
DEFAULT_JOB_IDS = (292, 913, 1601, 2068, 2916, 13, 613)

# Free-text side of the search; or_search_query=true ORs the terms.
DEFAULT_QUERY = "AI agent LLM chatbot automation"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _search(query: str, limit: int) -> dict[str, Any]:
    params: list[tuple[str, str]] = [
        ("query", query),
        ("or_search_query", "true"),      # OR the query terms instead of AND
        ("limit", str(limit)),
        ("full_description", "true"),     # full text for the fit-scorer
        ("job_details", "true"),          # skill names in results
        # newest first — time_submitted sorts DESCENDING by default; never set
        # reverse_sort=true (flips to oldest-first and surfaces stale entries).
        ("sort_field", "time_submitted"),
    ]
    params += [("jobs[]", str(j)) for j in DEFAULT_JOB_IDS]
    with httpx.Client(timeout=45.0) as c:
        r = c.get(
            _BASE,
            params=params,
            headers={"Freelancer-OAuth-V1": Config.freelancer_oauth_token},
        )
        r.raise_for_status()
        return r.json()


def _budget_str(p: dict[str, Any]) -> str | None:
    b = p.get("budget") or {}
    lo, hi = b.get("minimum"), b.get("maximum")
    cur_obj = p.get("currency") or {}
    cur = cur_obj.get("code") or "USD"
    rate = cur_obj.get("exchange_rate")  # multiplier to USD
    ptype = p.get("type")  # 'fixed' | 'hourly'
    if lo is None and hi is None:
        return None
    rng = f"{lo or '?'}–{hi or '?'} {cur}"
    # Show a USD equivalent for non-USD budgets so the fit-scorer judges real value — a big INR
    # number is often a tiny USD rate, and the scorer must not be fooled by the raw figure.
    usd = ""
    if isinstance(rate, (int, float)) and rate > 0 and cur != "USD":
        def _u(v: Any) -> str:
            return f"${round(v * rate)}" if isinstance(v, (int, float)) else "?"
        usd = f" (~{_u(lo)}–{_u(hi)} USD)"
    return f"{rng}{usd}/hr" if ptype == "hourly" else f"{rng}{usd} (fixed)"


def _normalize(p: dict[str, Any]) -> dict[str, Any] | None:
    pid = p.get("id")
    if not pid:
        return None
    seo = p.get("seo_url") or ""
    url = f"https://www.freelancer.com/projects/{seo}" if seo else None
    skills = [j.get("name") for j in (p.get("jobs") or []) if isinstance(j, dict) and j.get("name")]
    desc = p.get("description") or p.get("preview_description") or ""
    submitted = p.get("submitdate") or p.get("time_submitted")
    # epoch seconds → ISO so the worker's _ts validator accepts them. The bid window closes
    # at submitdate + bidperiod (integer DAYS) — store it as the deadline so _expire_stale
    # auto-clears gigs that are no longer open for bidding (NULL would never expire).
    posted_at = None
    deadline = None
    if isinstance(submitted, (int, float)) and submitted > 0:
        posted_at = datetime.fromtimestamp(int(submitted), tz=UTC).isoformat()
        bidperiod = p.get("bidperiod")
        if isinstance(bidperiod, int) and bidperiod > 0:
            deadline = datetime.fromtimestamp(int(submitted) + bidperiod * 86400, tz=UTC).isoformat()
    bid_stats = p.get("bid_stats") or {}
    return {
        "source": "freelancer",
        "external_id": str(pid),
        "title": p.get("title") or "(untitled project)",
        "org": f"Freelancer client ({bid_stats.get('bid_count', '?')} bids so far)",
        "description": desc[:8000] + ("\n\nSkills: " + ", ".join(skills) if skills else ""),
        "url": url,
        "budget": _budget_str(p),
        "location": "Remote",
        "deadline": deadline,
        "posted_at": posted_at,
        "naics": None,
        "psc": None,
        "set_aside": None,
        "raw": p,
    }


# ---------------------------------------------------------------------------
# Bid placement — officially supported by the Freelancer API (the official SDK ships
# place_project_bid). Only ever called from a human-initiated dashboard/CLI action; the
# sweep never submits anything.
# ---------------------------------------------------------------------------

_USERS_SELF = "https://www.freelancer.com/api/users/0.1/self/"
_BIDS = "https://www.freelancer.com/api/projects/0.1/bids/"


def my_user_id() -> int:
    """The token owner's Freelancer user id (required as bidder_id when placing a bid)."""
    with httpx.Client(timeout=30.0) as c:
        r = c.get(_USERS_SELF, headers={"Freelancer-OAuth-V1": Config.freelancer_oauth_token})
        r.raise_for_status()
        data = r.json()
    uid = (data.get("result") or {}).get("id")
    if not uid:
        raise RuntimeError(f"couldn't resolve own user id from /users/0.1/self/: {str(data)[:200]}")
    return int(uid)


def place_bid(
    *,
    project_id: int,
    amount: float,
    period_days: int,
    description: str,
    milestone_percentage: int = 100,
) -> dict[str, Any]:
    """Place one bid on an open project. Raises with the API's own error message on failure
    (e.g. insufficient token scope, bid limit reached, already bid) so the caller can show it.
    Returns the created bid object (contains `id` — the provider bid id)."""
    body = {
        "project_id": int(project_id),
        "bidder_id": my_user_id(),
        "amount": float(amount),
        "period": int(period_days),
        "milestone_percentage": int(milestone_percentage),
        "description": description,
    }
    with httpx.Client(timeout=45.0) as c:
        r = c.post(_BIDS, headers={"Freelancer-OAuth-V1": Config.freelancer_oauth_token}, json=body)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code >= 400 or data.get("status") == "error":
            msg = data.get("message") or data.get("error_code") or r.text[:200]
            raise RuntimeError(f"Freelancer bid failed (HTTP {r.status_code}): {msg}")
    result = data.get("result") or {}
    if not result.get("id"):
        raise RuntimeError(f"Freelancer bid response missing id: {str(data)[:200]}")
    return result


def get_my_bids(*, bid_ids: list[int] | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Fetch the token owner's bids (optionally narrowed to specific bid ids — we store the
    id of every bid we place). Used by the tracker to poll award status. Each bid carries
    `award_status` (pending | awarded | rejected | revoked | canceled) plus project_id.
    Raises on HTTP errors so the tracker can log-and-retry next tick."""
    params: list[tuple[str, str]] = [
        ("bidders[]", str(my_user_id())),
        ("limit", str(limit)),
    ]
    for b in bid_ids or []:
        params.append(("bids[]", str(b)))
    with httpx.Client(timeout=45.0) as c:
        r = c.get(_BIDS, params=params, headers={"Freelancer-OAuth-V1": Config.freelancer_oauth_token})
        r.raise_for_status()
        data = r.json()
    return ((data.get("result") or {}).get("bids")) or []


_THREADS = "https://www.freelancer.com/api/messages/0.1/threads/"


def get_message_threads(*, project_ids: list[int] | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Message threads the token owner is in (optionally scoped to specific project ids — the
    threads that open once a client engages a bid). Each thread carries a `context` (project)
    and a `message` (latest). Used to surface client replies on bids. [] on error."""
    params: list[tuple[str, str]] = [("limit", str(limit))]
    for pid in project_ids or []:
        params.append(("contexts[]", str(pid)))
        params.append(("context_type", "project"))
    try:
        with httpx.Client(timeout=45.0) as c:
            r = c.get(_THREADS, params=params, headers={"Freelancer-OAuth-V1": Config.freelancer_oauth_token})
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"WARNING freelancer threads fetch failed: {e}")
        return []
    return ((data.get("result") or {}).get("threads")) or []


def fetch_opportunities(*, query: str = DEFAULT_QUERY, limit: int = 50) -> list[dict[str, Any]]:
    """Recent AI/software Freelancer projects open for bidding. [] if no token / on error."""
    if not Config.freelancer_oauth_token:
        return []
    try:
        data = _search(query, limit)
    except Exception as e:  # noqa: BLE001
        print(f"WARNING freelancer fetch failed: {e}")
        return []
    projects = ((data.get("result") or {}).get("projects")) or []
    out: list[dict[str, Any]] = []
    for p in projects:
        if not isinstance(p, dict):
            continue
        norm = _normalize(p)
        if norm:
            out.append(norm)
    return out
