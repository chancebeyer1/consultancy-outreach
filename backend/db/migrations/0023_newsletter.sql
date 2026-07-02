-- 0023 — "The Agent Brief" newsletter: agent-curated weekly issues + an owned subscriber list.
-- Issues are drafted by an agent, approved by the operator, then sent to opted-in subscribers
-- via Resend (NOT the cold-email boxes). The subscriber list is the durable owned-audience asset.
create table if not exists newsletter_issues (
    id         uuid primary key default gen_random_uuid(),
    subject    text,
    body       text,                                  -- the issue the operator edits + approves
    status     text not null default 'draft',         -- draft | approved | sent
    sent_at    timestamptz,
    recipients int,
    error      text,
    created_at timestamptz not null default now()
);
create index if not exists newsletter_issues_created_idx on newsletter_issues(created_at desc);

create table if not exists subscribers (
    id              uuid primary key default gen_random_uuid(),
    email           text unique,
    name            text,
    source          text,                             -- 'site' | 'audit' | 'manual'
    unsubscribed_at timestamptz,
    created_at      timestamptz not null default now()
);
create index if not exists subscribers_active_idx on subscribers(created_at desc) where unsubscribed_at is null;

alter table newsletter_issues enable row level security;  -- service-role only
alter table subscribers enable row level security;        -- service-role only (PII: emails)
