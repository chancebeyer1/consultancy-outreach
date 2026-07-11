-- 0032 — Error Agent ticket store.
--
-- One row per distinct failure signature (matches alert_log.signature = sha1(source|summary)). The
-- error agent collects failures here, root-causes each ONCE with code context, opens a fix PR, and
-- rolls them into a single digest — replacing the per-error alert spam. RLS on, service-role only.

create table if not exists error_tickets (
    signature    text primary key,                 -- = alert_log.signature (sha1(source|summary)[:20])
    app          text not null default 'outreach', -- 'outreach' | 'trading-bot'
    source       text not null,                    -- process name (e.g. 'cron_send')
    summary      text not null,                     -- short problem line
    detail       text,                              -- fullest traceback/error we captured
    occurrences  int  not null default 1,
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now(),
    status       text not null default 'new',       -- new | analyzed | pr_opened | resolved | muted | wontfix
    severity     text,                              -- low | medium | high | critical
    confidence   real,                              -- 0..1 from the analyst
    risk         text,                              -- safe | moderate | risky (does the fix touch sends/trades/deletes)
    root_cause   text,
    fix_summary  text,
    fix_file     text,
    analysis     jsonb,                             -- full analyst output {root_cause, fix:{file,old,new}, ...}
    pr_url       text,
    analyzed_at  timestamptz,
    pr_opened_at timestamptz,
    digested_at  timestamptz,                        -- last time surfaced in a digest
    resolved_at  timestamptz,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create index if not exists error_tickets_status_idx on error_tickets(status, last_seen desc);
alter table error_tickets enable row level security;  -- service-role only
