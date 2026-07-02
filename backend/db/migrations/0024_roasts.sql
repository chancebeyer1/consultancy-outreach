-- 0024 — "Roast my cold outreach" submissions (the second public lead-magnet tool).
-- Someone pastes a cold email/DM, an agent critiques + rewrites it. Like audits, each run
-- captures the prospect as an inbound deal in the pipeline.
create table if not exists roasts (
    id         uuid primary key default gen_random_uuid(),
    email      text,
    name       text,
    input_text text,
    roast      jsonb,
    deal_id    uuid references deals(id),
    ip         text,
    created_at timestamptz not null default now()
);
create index if not exists roasts_created_idx on roasts(created_at desc);
alter table roasts enable row level security;  -- service-role only (PII: prospect emails)
