-- 0006_mailboxes.sql — connected sending mailboxes for the cold-email system.
--
-- One row per mailbox (Zoho/Google/Outlook/SMTP). The cold-email sender rotates
-- across active boxes, each capped by a rising warmup ramp. Credentials live here
-- (app-passwords), so RLS is ON with NO anon policy — only the backend (superuser /
-- service_role, which bypass RLS) can read them; the public anon key cannot.

create table if not exists mailboxes (
    id            uuid primary key default gen_random_uuid(),
    email         text not null unique,
    provider      text not null default 'zoho',   -- zoho | google | outlook | smtp
    from_name     text,                            -- display name on the From header
    domain        text,                            -- sending domain (for grouping/health)
    smtp_host     text not null,
    smtp_port     int  not null default 465,
    imap_host     text not null,
    imap_port     int  not null default 993,
    username      text not null,                   -- usually the full email address
    app_password  text not null,                   -- app-specific password (revocable)
    status        text not null default 'warming', -- warming | active | paused | disabled
    daily_cap     int  not null default 10,        -- current per-day send ceiling (ramps up)
    warmup_stage  int  not null default 0,         -- weeks into warmup
    ramp_started_at date,
    bounce_count  int  not null default 0,
    last_send_at  timestamptz,
    last_error    text,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

alter table mailboxes enable row level security;  -- no anon policy: passwords stay backend-only

-- Email sends record which mailbox delivered them (per-box accounting + threading).
alter table sends add column if not exists mailbox_id uuid references mailboxes(id);
create index if not exists sends_mailbox_idx on sends(mailbox_id);
