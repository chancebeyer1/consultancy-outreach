-- 0044 — meeting intelligence.
--
-- A meeting is a pasted call transcript attached to a deal. A worker extracts pains, budget
-- and timeline signals, process-automation candidates (in the agent-factory's CandidateProcess
-- shape), and drafts the follow-up email. factory_export holds evidence + candidates ready to
-- import into the process-agent-factory repo, so the call that closes the deal also seeds the
-- delivery engine's Process Map.
create table if not exists meetings (
    id             uuid primary key default gen_random_uuid(),
    deal_id        uuid references deals(id) on delete cascade,
    lead_id        uuid references leads(id),
    user_id        uuid,
    title          text,
    held_at        timestamptz,
    transcript     text not null,
    extraction     jsonb,       -- meeting_extract.md output (pains, signals, candidates, ...)
    follow_up_draft text,
    factory_export jsonb,       -- {evidence:[...], candidate_processes:[...]} for the factory
    status         text not null default 'new',   -- new | processed | failed
    error          text,
    created_at     timestamptz not null default now(),
    processed_at   timestamptz
);
create index if not exists meetings_deal_idx on meetings(deal_id, created_at desc);
alter table meetings enable row level security;  -- service-role only
