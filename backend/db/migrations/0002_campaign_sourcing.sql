-- 0002 — campaign sourcing config
-- Adds the automated-sourcing search URL and per-campaign initial channels so the
-- dashboard can edit targeting live and the replenish cron knows what to search.
-- Idempotent; safe to re-run.

alter table campaigns add column if not exists search_url text;
alter table campaigns add column if not exists channels   text[];
