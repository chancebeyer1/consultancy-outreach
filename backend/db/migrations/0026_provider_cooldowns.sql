-- Cross-run provider cooldowns. When LinkedIn returns a temporary account-level
-- throttle (422 cannot_resend_yet / "temporary provider limit"), we must STOP
-- re-attempting that channel for a while — otherwise the every-47-min cron keeps
-- poking LinkedIn with failed invites, which prolongs the block and looks bot-like.
-- Modal containers are ephemeral, so this state lives in Postgres, not memory.
create table if not exists provider_cooldowns (
    key           text primary key,        -- channel key, e.g. 'linkedin_connect'
    blocked_until timestamptz not null,
    reason        text,
    hits          int not null default 1,  -- how many times tripped (debugging/escalation)
    updated_at    timestamptz not null default now()
);

-- Credentials/PII-free, but keep it service-role only like the rest of the backend
-- tables (no anon policy → the dashboard reads via serverAdminClient).
alter table provider_cooldowns enable row level security;
