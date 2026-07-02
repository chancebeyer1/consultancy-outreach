-- 0022 — AI Opportunity Audit submissions (the public lead-magnet tool).
-- Each run captures the prospect's email + company + the generated report. We also spin up a
-- lead + an inbound deal so the audit lands in the CRM pipeline automatically.
create table if not exists audits (
    id         uuid primary key default gen_random_uuid(),
    email      text,
    name       text,
    company    text,
    website    text,
    domain     text,
    report     jsonb,
    lead_id    uuid references leads(id),
    deal_id    uuid references deals(id),
    ip         text,
    created_at timestamptz not null default now()
);
create index if not exists audits_created_idx on audits(created_at desc);
create index if not exists audits_domain_idx on audits(domain, created_at desc);
alter table audits enable row level security;  -- service-role only (PII: prospect emails)
