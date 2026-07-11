-- A/B testing foundation: attribute outcomes back to the exact variant that earned them.
--
-- 1) replies.draft_id — today a reply only links to a lead, so we can't say WHICH draft
--    (and thus which A/B variant) earned the reply. This FK closes that gap for both email
--    (attributed to the opener draft) and LinkedIn (attributed to the connect draft).
-- 2) leads.search_variant — tags which named sourcing recipe found the lead, so we can compare
--    targeting approaches on fit score (now), accept rate (days), and reply rate (weeks).
alter table replies add column if not exists draft_id uuid references drafts(id);
create index if not exists replies_draft_idx on replies(draft_id);

alter table leads add column if not exists search_variant text;
create index if not exists leads_search_variant_idx on leads(search_variant);

-- Per-recipe Apollo pagination. The single apollo_cursor (migration 0019) can't track
-- independent page positions for multiple search recipes, so multi-variant campaigns keep a
-- {recipe_name: page} map here. Single-recipe campaigns keep using apollo_cursor unchanged.
alter table campaigns add column if not exists apollo_cursors jsonb not null default '{}'::jsonb;
