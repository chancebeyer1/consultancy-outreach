-- 0012 — activity logging + multi-tenant foundation
--
-- (a) activity_log: append-only unified action timeline (every cron run, send, reply,
--     dashboard action). RLS on, service-role only. Backed by backend/activity.py.
-- (b) multi-tenant FOUNDATION (non-breaking, no RLS yet): a profiles table (one row per
--     user, holding their per-user LinkedIn/Unipile account ids) and a nullable user_id on
--     the owned root entities. Existing rows keep user_id NULL until backfilled to user #1
--     when Supabase Auth is wired. Shared keys (Apollo/MillionVerifier/Claude) stay global.
-- Idempotent; safe to re-run.

create table if not exists activity_log (
    id           uuid primary key default gen_random_uuid(),
    created_at   timestamptz not null default now(),
    actor        text not null default 'system',
    action       text not null,
    source       text not null default 'worker',
    channel      text,
    entity_type  text,
    entity_id    uuid,
    campaign_id  uuid references campaigns(id),
    lead_id      uuid references leads(id),
    summary      text,
    meta         jsonb
);
create index if not exists activity_log_created_idx on activity_log(created_at desc);
alter table activity_log enable row level security;  -- service-role only

create table if not exists profiles (
    id                       uuid primary key,   -- = auth.users.id once Supabase Auth is wired
    email                    text unique,
    name                     text,
    unipile_account_id       text,               -- the user's connected LinkedIn (per-user)
    unipile_email_account_id text,
    is_admin                 boolean not null default false,
    created_at               timestamptz not null default now()
);

alter table campaigns add column if not exists user_id uuid;
alter table leads     add column if not exists user_id uuid;
alter table mailboxes add column if not exists user_id uuid;
