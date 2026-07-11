-- 0039 — Site concierge chat.
--
-- The on-site AI assistant (agentry.contentdrip.ai) answers questions, qualifies visitors, and
-- points them at the audit tool / booking link. One row per chat session: the running transcript,
-- plus the visitor's email once they share it (lead capture → operator notification, once).
-- RLS on, service-role only.

create table if not exists concierge_chats (
    id          uuid primary key default gen_random_uuid(),
    session_id  text unique not null,             -- browser-generated, sessionStorage-scoped
    page        text,                             -- the page the chat started on
    messages    jsonb not null default '[]'::jsonb,
    email       text,                             -- captured visitor email (lead)
    notified    boolean not null default false,   -- operator alerted about this lead yet?
    turns       int not null default 0,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create index if not exists concierge_chats_created_idx on concierge_chats(created_at desc);
alter table concierge_chats enable row level security;  -- service-role only
