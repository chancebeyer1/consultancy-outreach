-- 0003_auto_send.sql — per-campaign auto-send toggle.
--
-- When true, the first-touch connection note auto-approves on ingest (no manual
-- review), so the send_approved cron sends it. Default false: review each draft.
-- Idempotent; safe to re-run.

alter table campaigns
    add column if not exists auto_send boolean not null default false;
