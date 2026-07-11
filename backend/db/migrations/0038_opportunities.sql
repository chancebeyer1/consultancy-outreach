-- 0038 — bidding module: discover software / AI-agent work from contract & freelance
-- sources (SAM.gov, Upwork, RemoteOK, HN "who is hiring", LinkedIn jobs), fit-score each,
-- and draft a proposal for the high-fit ones. This is the outbound-BID counterpart to the
-- outbound-LEAD pipeline: opportunities ≈ leads, bids ≈ drafts. Kept in separate tables
-- (not overloaded onto leads/drafts) because an opportunity has no LinkedIn identity and a
-- bid is a proposal, not a message — different shape, same review-queue UX. Idempotent.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------
-- opportunities — one row per discovered piece of work
-- ---------------------------------------------------------------
create table if not exists opportunities (
    id            uuid primary key default gen_random_uuid(),
    source        text not null,          -- 'sam_gov' | 'upwork' | 'remoteok' | 'hn_hiring' | 'linkedin_jobs'
    external_id   text not null,          -- source's native id (notice id, job ciphertext, comment id…)
    title         text not null,
    org           text,                   -- contracting agency / Upwork client / company
    description   text,                   -- full text used for fit-scoring + bid drafting
    url           text,                   -- where to view / apply
    budget        text,                   -- freeform: '$50k–$100k', '$60/hr', 'contract value $250k'
    location      text,
    deadline      timestamptz,            -- response deadline / close date (gov) — null if none
    posted_at     timestamptz,            -- when the source published it
    naics         text,                   -- gov only — NAICS code
    psc           text,                   -- gov only — product/service (classification) code
    set_aside     text,                   -- gov only — e.g. 'Total Small Business', '8(a)'
    raw           jsonb,                  -- full normalized source payload (audit + re-score)
    fit_score     int,                    -- 0–100 LLM fit; null = not yet scored
    fit_rationale text,                   -- one-paragraph "why this fits / doesn't"
    fit_flags     jsonb,                  -- {is_software, is_ai_agent, eligible, reasons:[…]}
    status        text not null default 'new',
        -- new | scored | drafted | approved | submitted | passed | won | lost
    user_id       uuid references profiles(id),   -- owner (the bidder); stamped at ingest
    discovered_at timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (source, external_id)          -- dedup: never ingest the same posting twice
);
create index if not exists opportunities_status_idx    on opportunities(status);
create index if not exists opportunities_source_idx    on opportunities(source);
create index if not exists opportunities_fit_idx       on opportunities(fit_score);
create index if not exists opportunities_discovered_idx on opportunities(discovered_at);

-- ---------------------------------------------------------------
-- bids — one drafted proposal per opportunity (awaiting your review)
-- ---------------------------------------------------------------
create table if not exists bids (
    id              uuid primary key default gen_random_uuid(),
    opportunity_id  uuid not null references opportunities(id) on delete cascade,
    summary         text,                 -- one-line "why we win this"
    body            text not null,        -- the drafted proposal / cover letter
    edited_body     text,                 -- your edits before submitting
    est_price       text,                 -- suggested bid price / hourly rate
    status          text not null default 'draft',   -- draft | approved | rejected | submitted
    rejection_reason text,
    model           text,
    generated_at    timestamptz not null default now(),
    decided_at      timestamptz,
    submitted_at    timestamptz,          -- YOU set this after submitting on the portal
    unique (opportunity_id)               -- one bid per opportunity (regenerate overwrites)
);
create index if not exists bids_status_idx on bids(status);

-- ---------------------------------------------------------------
-- RLS — mirror the leads/drafts owner model (0032). Service-role workers bypass
-- RLS; these gate the anon/authenticated dashboard clients. Bids inherit the
-- owner of their opportunity.
-- ---------------------------------------------------------------
alter table opportunities enable row level security;
drop policy if exists opportunities_owner_all on opportunities;
create policy opportunities_owner_all on opportunities for all to authenticated
    using (is_admin() or user_id = auth.uid())
    with check (is_admin() or user_id = auth.uid());

alter table bids enable row level security;
drop policy if exists bids_owner_all on bids;
create policy bids_owner_all on bids for all to authenticated
    using (is_admin() or exists (
        select 1 from opportunities o where o.id = bids.opportunity_id
          and (is_admin() or o.user_id = auth.uid())))
    with check (is_admin() or exists (
        select 1 from opportunities o where o.id = bids.opportunity_id
          and (is_admin() or o.user_id = auth.uid())));

-- keep updated_at fresh on opportunities
create or replace function public.opportunities_touch_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end $$;
drop trigger if exists opportunities_touch on opportunities;
create trigger opportunities_touch before update on opportunities
    for each row execute function public.opportunities_touch_updated_at();
