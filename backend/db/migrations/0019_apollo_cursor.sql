-- 0019 — Apollo pagination cursor: where the last sourcing run stopped paging, per campaign.
-- The worker resumes from cursor+1 each run (instead of re-scanning page 1), walking the whole
-- result set for a steady stream of NEW leads, then wraps to 0 when it runs off the end.
alter table campaigns add column if not exists apollo_cursor int not null default 0;
