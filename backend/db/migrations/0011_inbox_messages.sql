-- 0011 — unified inbox (the in-dashboard "master inbox")
-- The 30 Maildoso boxes keep warmup traffic OUT of their INBOX folders, so the visible
-- inbox is real replies only. The unibox poller stores every inbound message here so the
-- dashboard can show one unified inbox across all boxes — reliable even when email alerts
-- get spam-foldered by recipients. Curated lead-matched replies still also land in `replies`.
-- Idempotent; safe to re-run.

create table if not exists inbox_messages (
    id           uuid primary key default gen_random_uuid(),
    mailbox_id   uuid references mailboxes(id),
    mailbox_email text,
    from_email   text,
    from_name    text,
    subject      text,
    body         text,
    message_id   text unique,
    in_reply_to  text,
    lead_id      uuid references leads(id),
    campaign_id  uuid references campaigns(id),
    is_auto      boolean not null default false,
    direction    text not null default 'in',   -- 'in' = received | 'out' = your reply (sent from the dashboard)
    received_at  timestamptz,
    created_at   timestamptz not null default now()
);

create index if not exists inbox_messages_received_idx on inbox_messages(received_at desc nulls last);

-- Holds prospect reply bodies (PII) — keep off the public anon key. The dashboard /inbox
-- reads via the service-role client (serverAdminClient), which bypasses RLS.
alter table inbox_messages enable row level security;  -- no anon policy on purpose
