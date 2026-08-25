-- 2026-08-24: pain mining — the discovery counterpart to `opportunities`.
--
-- Six rounds of niche-first desk research all converged on "already served", because desk
-- research can only find pain somebody already wrote down, and documented pain is by
-- definition pain a vendor already noticed. This table collects the raw material for the
-- other direction: operators describing their own work in occupational forums, scored and
-- bucketed by task so a recurring complaint across many posters becomes visible as a market
-- rather than as one person venting.
--
-- One row per source post. `theme_slug` is the clustering key — the scorer normalizes each
-- complaint to a task label, so `group by theme_slug` IS the cluster view; no second pass.
--
-- Deliberately no author column. See clients/reddit.py: this is a research corpus, never a
-- contact list, and nobody gets messaged because they complained somewhere.
create table if not exists pain_signals (
    id              uuid primary key default gen_random_uuid(),
    source          text not null,              -- 'reddit' | (future: 'hn', 'forum')
    external_id     text not null,              -- provider id, e.g. reddit fullname t3_xxxxx
    url             text,
    venue           text,                       -- 'r/hvac' — where it was said
    industry        text,                       -- venue's industry label, set by the sweep
    title           text,
    body            text,                       -- capped excerpt, not the full thread
    posted_at       timestamptz,
    upvotes         int,
    num_comments    int,

    -- LLM triage (see prompts/score_pain.md)
    pain_score      int,                        -- 0-100, the queue's sort key
    theme_slug      text,                       -- kebab-case task label = the cluster key
    buyer_role      text,                       -- who has this problem
    task            text,                       -- the specific operational task
    recurrence      text,                       -- per-job | daily | weekly | monthly | annual | one-off | unknown
    flags           jsonb,                      -- the boolean rubric (penalty, manual, multi-jurisdiction, kills)
    rationale       text,
    model           text,

    status          text not null default 'scored',   -- scored | shortlisted | dismissed
    created_at      timestamptz not null default now()
);

-- The dedup ledger: an ephemeral Modal container can't keep a local one, so re-seeing a post
-- across sweeps must be free. Matches the opportunities (source, external_id) convention.
create unique index if not exists pain_signals_source_ext_uidx on pain_signals(source, external_id);
create index if not exists pain_signals_theme_idx    on pain_signals(theme_slug) where theme_slug is not null;
create index if not exists pain_signals_score_idx    on pain_signals(pain_score desc);
create index if not exists pain_signals_industry_idx on pain_signals(industry);
create index if not exists pain_signals_status_idx   on pain_signals(status);

-- Same reasoning as 0050: the dashboard reads through the service-role client and workers
-- connect as the table owner, both of which bypass RLS. Enabling it with no policies blocks
-- the public Data API and changes nothing else. Without this the table ships publicly
-- readable and trips the Supabase Security Advisor.
alter table public.pain_signals enable row level security;
