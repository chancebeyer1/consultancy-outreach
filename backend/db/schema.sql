-- Consultancy Outreach DB schema
-- Target: Postgres 15+ (Supabase-compatible)
-- Run: psql $DATABASE_URL -f schema.sql

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------
-- leads — one row per prospect
-- ---------------------------------------------------------------
create table if not exists leads (
    id              uuid primary key default gen_random_uuid(),
    linkedin_url    text not null unique,
    name            text,
    headline        text,
    company         text,
    company_domain  text,
    role            text,
    location        text,
    -- ICP segment: ai_native_consultancy | traditional_consultancy_pivot | product_company
    segment         text,
    source          text,           -- e.g. 'sales_nav:cto-aiconsultancy-na'
    trigger         text,           -- 'list' | 'profile_view' | 'post_engagement' | 'funding_event' | 'new_role'
    status          text not null default 'new',
                                    -- new | enriched | scored | drafted | approved | sending | sent | replied | closed | rejected
    notes           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index if not exists leads_status_idx     on leads(status);
create index if not exists leads_segment_idx    on leads(segment);
create index if not exists leads_trigger_idx    on leads(trigger);

-- ---------------------------------------------------------------
-- enrichments — raw research payloads
-- ---------------------------------------------------------------
create table if not exists enrichments (
    id                  uuid primary key default gen_random_uuid(),
    lead_id             uuid not null references leads(id) on delete cascade,
    proxycurl_json      jsonb,
    company_signals_json jsonb,    -- Tavily/Serper company search results
    github_json         jsonb,
    recent_posts_json   jsonb,     -- their last ~10 LinkedIn posts
    hooks_json          jsonb,     -- output of insight_extraction prompt
    enriched_at         timestamptz not null default now(),
    unique (lead_id)
);

-- ---------------------------------------------------------------
-- scores — LLM ICP-fit score
-- ---------------------------------------------------------------
create table if not exists scores (
    id          uuid primary key default gen_random_uuid(),
    lead_id     uuid not null references leads(id) on delete cascade,
    fit_score   int not null check (fit_score between 0 and 100),
    rationale   text,
    model       text,
    scored_at   timestamptz not null default now(),
    unique (lead_id)
);
create index if not exists scores_fit_idx on scores(fit_score);

-- ---------------------------------------------------------------
-- drafts — one row per message variant per channel per step
-- ---------------------------------------------------------------
create table if not exists drafts (
    id              uuid primary key default gen_random_uuid(),
    lead_id         uuid not null references leads(id) on delete cascade,
    channel         text not null,
        -- 'linkedin_connect' | 'linkedin_dm' | 'linkedin_followup_1' | 'linkedin_followup_2'
        -- | 'email' | 'email_followup_1' | 'email_followup_2'
    step_index      int not null default 0,
    hook            jsonb,      -- {type, reference, why, signal_strength}
    body            text not null,
    edited_body     text,
    status          text not null default 'draft',
        -- 'draft' | 'approved' | 'rejected' | 'sent' | 'failed'
    rejection_reason text,
    variant         text,       -- A/B testing tag
    generated_at    timestamptz not null default now(),
    decided_at      timestamptz,
    unique (lead_id, channel, step_index, variant)
);
create index if not exists drafts_lead_idx   on drafts(lead_id);
create index if not exists drafts_status_idx on drafts(status);

-- ---------------------------------------------------------------
-- sends — records of actual deliveries
-- ---------------------------------------------------------------
create table if not exists sends (
    id          uuid primary key default gen_random_uuid(),
    draft_id    uuid not null references drafts(id) on delete cascade,
    provider    text not null,   -- 'heyreach' | 'smartlead' | 'manual'
    external_id text,             -- provider's message/campaign id
    sent_at     timestamptz not null default now(),
    status      text not null default 'queued', -- queued | sent | delivered | bounced | failed
    error       text
);
create index if not exists sends_draft_idx on sends(draft_id);

-- ---------------------------------------------------------------
-- replies — inbound responses + LLM classification
-- ---------------------------------------------------------------
create table if not exists replies (
    id              uuid primary key default gen_random_uuid(),
    lead_id         uuid not null references leads(id) on delete cascade,
    channel         text not null,
    body            text not null,
    sentiment       text,        -- positive | neutral | negative
    intent          text,        -- interested | objection | not_now | referral | unsubscribe | oof | other
    suggested_reply text,        -- LLM-drafted response, awaiting your approval
    handled_at      timestamptz,
    received_at     timestamptz not null default now()
);
create index if not exists replies_lead_idx   on replies(lead_id);
create index if not exists replies_intent_idx on replies(intent);

-- ---------------------------------------------------------------
-- campaigns — for A/B testing and segment-level analytics
-- ---------------------------------------------------------------
create table if not exists campaigns (
    id          uuid primary key default gen_random_uuid(),
    name        text not null,
    segment     text,
    icp_query   text,
    status      text not null default 'active',
    started_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------
-- sequences — which step each lead is currently on (Phase 3)
-- ---------------------------------------------------------------
create table if not exists sequence_state (
    lead_id         uuid primary key references leads(id) on delete cascade,
    current_channel text,
    current_step    int not null default 0,
    next_action_at  timestamptz,
    paused          bool not null default false,
    updated_at      timestamptz not null default now()
);
create index if not exists sequence_next_idx on sequence_state(next_action_at) where paused = false;
