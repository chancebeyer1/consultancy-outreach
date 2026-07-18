"""Accept-rate optimizer — Thompson-sampling allocation for LinkedIn connects.

The 9-14%% connect-accept rate is the funnel's #1 bottleneck (benchmark: ~28%%). Two allocation
decisions ride the same posterior machinery instead of fixed splits:

1. pick_connect_variant(campaign_ref, key) — which connect-note arm (a/b/c) a new lead gets.
   Replaces the fixed mod-3 split in workers.draft.connect_variant. DETERMINISTIC PER LEAD:
   the RNG is seeded by the lead URL, so every call site that computes a lead's variant during
   a replenish run agrees (the drafted body and the stored variant tag must never diverge —
   an empty body is only legitimate on arm 'c').

2. campaign_connect_weights() — how the daily connect budget tilts across campaigns by matured
   accept rate. Consumed by sequence_send's fairness gate. Floored at MIN_WEIGHT so no campaign
   ever starves: exploration never stops, a cold campaign keeps earning data.

Statistics:
- Matured window: only sends >= MATURE_DAYS old count (invites need days to resolve into
  accept/ignore); window capped at WINDOW_DAYS so ancient experiments stop steering today.
- Pool prior: per-campaign counts are tiny, so each arm's Beta prior carries the cross-campaign
  pool scaled to PRIOR_N pseudo-observations. Small campaigns hug the pool; big ones follow
  their own data.
- Fail-open: any DB problem falls back to the legacy deterministic split / even shares.
"""

from __future__ import annotations

import random
import time
from typing import Any

# 'd' added 2026-07-18 (double-down sprint): peer observation + question-first CTA. Matured data
# then showed b (peer statement) beating a (curiosity) in EVERY campaign (pooled 21.1% vs 11.5%),
# so d iterates on the winning peer angle. New arm cold-starts on a uniform Beta prior — Thompson
# explores it hard for the first ~week, then the data takes over.
VARIANTS = ("a", "b", "c", "d")
MATURE_DAYS = 7      # a connect younger than this is unresolved, not a miss
WINDOW_DAYS = 90     # ignore sends older than this
PRIOR_N = 20         # pool pseudo-observations behind each campaign's Beta prior
EXPLORE_EPS = 0.10   # per-lead chance of a uniform random arm, regardless of posterior
MIN_WEIGHT = 0.15    # no campaign's budget share may fall below this (then renormalized)
_CACHE_TTL_S = 3600  # posterior snapshot lifetime (also bounds intra-run consistency)

_cache: dict[str, Any] = {"at": 0.0, "matrix": None}


def _connect():
    import psycopg

    from config import require

    return psycopg.connect(require("DATABASE_URL"))


def _matrix() -> dict[str, dict[str, tuple[int, int]]]:
    """{campaign_id: {variant: (accepts, misses)}} over the matured window, cached ~1h.
    Key '' holds the cross-campaign pool."""
    now = time.monotonic()
    if _cache["matrix"] is not None and now - _cache["at"] < _CACHE_TTL_S:
        return _cache["matrix"]
    matrix: dict[str, dict[str, tuple[int, int]]] = {"": {}}
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select coalesce(l.campaign_id::text, ''), coalesce(d.variant, 'a'),
                   count(l.accepted_at) as accepts,
                   count(*) - count(l.accepted_at) as misses
            from sends s
            join drafts d on d.id = s.draft_id
            join leads l on l.id = d.lead_id
            where d.channel = 'linkedin_connect'
              and s.sent_at < now() - make_interval(days => %s)
              and s.sent_at > now() - make_interval(days => %s)
            group by 1, 2
            """,
            (MATURE_DAYS, WINDOW_DAYS),
        )
        pool: dict[str, list[int]] = {}
        for cid, variant, accepts, misses in cur.fetchall():
            v = variant if variant in VARIANTS else "a"
            camp = matrix.setdefault(cid, {})
            prev = camp.get(v, (0, 0))
            camp[v] = (prev[0] + int(accepts), prev[1] + int(misses))
            agg = pool.setdefault(v, [0, 0])
            agg[0] += int(accepts)
            agg[1] += int(misses)
        matrix[""] = {v: (a, m) for v, (a, m) in pool.items()}
    _cache["matrix"] = matrix
    _cache["at"] = now
    return matrix


def _resolve_campaign_id(campaign_ref: str | None) -> str | None:
    """Accept a campaign id OR slug (call sites have one or the other). Cached via _matrix keys
    when possible; falls back to a lookup."""
    if not campaign_ref:
        return None
    ref = str(campaign_ref)
    matrix = _matrix()
    if ref in matrix:
        return ref
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select id::text from campaigns where slug = %s or id::text = %s", (ref, ref))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:  # noqa: BLE001
        return None


def _arm_prior(pool: dict[str, tuple[int, int]], v: str) -> tuple[float, float]:
    a_p, m_p = pool.get(v, (0, 0))
    n = a_p + m_p
    if n <= 0:
        return (1.0, 1.0)
    rate = a_p / n
    return (1.0 + PRIOR_N * rate, 1.0 + PRIOR_N * (1.0 - rate))


def pick_connect_variant(campaign_ref: str | None, key: str | None) -> str:
    """Thompson-sampled connect-note arm for one lead. Seeded by the lead URL so repeated calls
    (draft time, ingest time) return the same arm within a posterior snapshot; records also
    thread the picked value through, so this determinism is belt-and-braces. Falls back to the
    legacy mod-3 split on any failure."""
    try:
        matrix = _matrix()
        pool = matrix.get("", {})
        cid = _resolve_campaign_id(campaign_ref)
        camp = matrix.get(cid or "###none###", {})
        rng = random.Random(f"cv:{key or ''}")
        if rng.random() < EXPLORE_EPS:
            return rng.choice(list(VARIANTS))
        best, best_s = "a", -1.0
        for v in VARIANTS:
            alpha0, beta0 = _arm_prior(pool, v)
            a_c, m_c = camp.get(v, (0, 0))
            s = rng.betavariate(alpha0 + a_c, beta0 + m_c)
            if s > best_s:
                best, best_s = v, s
        return best
    except Exception:  # noqa: BLE001 — fail open to the legacy deterministic split
        from workers.draft import connect_variant

        return connect_variant(key)


def campaign_connect_weights() -> dict[str, float]:
    """{campaign_id: share} of the daily connect budget, Thompson-sampled from each campaign's
    matured accept posterior (pool prior). Seeded per UTC day: the tilt is stable within a day
    and re-rolls tomorrow. Floored at MIN_WEIGHT and renormalized. {} on any failure (callers
    fall back to even shares)."""
    try:
        from datetime import UTC, datetime

        matrix = _matrix()
        pool = matrix.get("", {})
        pool_a = sum(a for a, _ in pool.values())
        pool_m = sum(m for _, m in pool.values())
        pool_n = pool_a + pool_m
        if pool_n <= 0:
            return {}
        prior_rate = pool_a / pool_n
        alpha0 = 1.0 + PRIOR_N * prior_rate
        beta0 = 1.0 + PRIOR_N * (1.0 - prior_rate)

        rng = random.Random(f"cw:{datetime.now(UTC).date().isoformat()}")
        samples: dict[str, float] = {}
        for cid, arms in matrix.items():
            if not cid:
                continue
            a_c = sum(a for a, _ in arms.values())
            m_c = sum(m for _, m in arms.values())
            samples[cid] = rng.betavariate(alpha0 + a_c, beta0 + m_c)
        if not samples:
            return {}
        total = sum(samples.values())
        weights = {cid: s / total for cid, s in samples.items()}
        floored = {cid: max(w, MIN_WEIGHT) for cid, w in weights.items()}
        norm = sum(floored.values())
        return {cid: w / norm for cid, w in floored.items()}
    except Exception:  # noqa: BLE001
        return {}


def allocator_report() -> dict[str, Any]:
    """Observability rows for the weekly report: matured per-campaign and per-variant stats plus
    today's sampled budget weights. Read-only; safe to call from the report's defensive helpers."""
    matrix = _matrix()
    weights = campaign_connect_weights()
    names: dict[str, str] = {}
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("select id::text, coalesce(name, slug) from campaigns")
            names = dict(cur.fetchall())
    except Exception:  # noqa: BLE001
        pass
    campaigns = []
    for cid, arms in matrix.items():
        if not cid:
            continue
        a = sum(x for x, _ in arms.values())
        m = sum(x for _, x in arms.values())
        campaigns.append(
            {
                "campaign": names.get(cid, cid[:8]),
                "sends": a + m,
                "accepts": a,
                "rate": round(a / (a + m) * 100, 1) if (a + m) else None,
                "weight": round(weights.get(cid, 0.0) * 100) if weights else None,
            }
        )
    campaigns.sort(key=lambda r: -(r["sends"] or 0))
    pool = matrix.get("", {})
    variants = [
        {
            "variant": v,
            "sends": (pool.get(v, (0, 0))[0] + pool.get(v, (0, 0))[1]),
            "accepts": pool.get(v, (0, 0))[0],
            "rate": (
                round(pool[v][0] / (pool[v][0] + pool[v][1]) * 100, 1)
                if v in pool and sum(pool[v]) else None
            ),
        }
        for v in VARIANTS
    ]
    return {"campaigns": campaigns, "variants": variants}


if __name__ == "__main__":
    import json

    print(json.dumps(allocator_report(), indent=2, default=str))
