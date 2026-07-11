-- 0008 — structured Sales-Navigator search params
-- A campaign can source either from a raw `search_url` (classic LinkedIn search copied
-- from the browser) OR from structured `search_params` (Sales-Navigator filters:
-- industry / region / seniority / company_headcount / role). The replenish worker
-- prefers `search_params` when present. Structured filters return far higher-ICP leads
-- than broad keyword URLs, so they score better.
-- Idempotent; safe to re-run.

alter table campaigns add column if not exists search_params jsonb;
