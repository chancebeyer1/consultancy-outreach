-- 0045 — productized AI assessment.
--
-- An assessment is a guided discovery interview run by an agent on the public site
-- (/assessment): visitor leaves contact info, answers ~8-12 adaptive questions about how the
-- business runs, and the synthesis step compiles a ranked process map (top automation
-- opportunities, factory-shaped). The preview (top 3) renders on the site; the full map is the
-- paid deliverable the operator walks through on a call. Completion notifies the operator and
-- opens a lead + deal (source='inbound').
create table if not exists assessments (
    id              uuid primary key default gen_random_uuid(),
    session_id      text unique,
    email           text,
    name            text,
    company         text,
    website         text,
    transcript      jsonb,       -- [{role, content}] full interview
    turns           int not null default 0,
    status          text not null default 'active',  -- active | compiling | synthesized | failed
    synthesis       jsonb,       -- {company_summary, processes:[...], quick_wins, preview:[top 3]}
    lead_id         uuid references leads(id),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    synthesized_at  timestamptz
);
create index if not exists assessments_session_idx on assessments(session_id);
alter table assessments enable row level security;  -- service-role only
