-- 0010 — Apollo email-sourcing config + durable dedup
-- `campaigns.apollo_params` holds the Apollo people-search filters (title/seniority/
-- location/headcount), parallel to `search_params` for Sales Navigator. `apollo_seen`
-- is a durable processed-ledger so the hourly Apollo sourcing never re-scores or
-- re-enriches (re-spends credits on) a contact it already evaluated — the local JSONL
-- ledger can't persist across ephemeral Modal containers, the DB can.
-- Idempotent; safe to re-run.

alter table campaigns add column if not exists apollo_params jsonb;

create table if not exists apollo_seen (
    apollo_id    text primary key,
    campaign_id  uuid references campaigns(id),
    fit          int,
    email_status text,
    seen_at      timestamptz not null default now()
);
