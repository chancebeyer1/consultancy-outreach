-- 0025 — failure-alert throttle. One row per distinct failure signature so a persistent failure
-- (like the LinkedIn note-limit bug) emails once, then stays quiet for the cooldown window
-- instead of alerting every cron tick. count tracks how many times it has recurred.
create table if not exists alert_log (
    signature    text primary key,
    source       text,
    summary      text,
    count        int not null default 1,
    last_sent_at timestamptz not null default now(),
    first_seen   timestamptz not null default now()
);
create index if not exists alert_log_last_idx on alert_log(last_sent_at desc);
alter table alert_log enable row level security;  -- service-role only
