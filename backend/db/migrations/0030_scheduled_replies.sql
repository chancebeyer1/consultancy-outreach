-- Scheduled follow-up replies ("reconnect in the fall"). A daily cron auto-sends due rows.
create table if not exists scheduled_replies (
    id           uuid primary key default gen_random_uuid(),
    lead_id      uuid references leads(id),
    reply_id     uuid references replies(id),
    channel      text not null,                    -- 'email' | 'linkedin_dm'
    chat_id      text,                             -- LinkedIn chat to send into (if known)
    provider_id  text,                             -- LinkedIn member id (fallback send target)
    body         text not null,
    due_at       timestamptz not null,
    status       text not null default 'pending',  -- pending | sent | cancelled | failed
    error        text,
    created_at   timestamptz not null default now(),
    sent_at      timestamptz
);
create index if not exists scheduled_replies_due_idx
    on scheduled_replies(due_at) where status = 'pending';
