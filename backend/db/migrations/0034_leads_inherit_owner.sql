-- 0034 — leads inherit their campaign's owner at insert time.
-- 0032 backfilled user_id on existing rows, but the ingestion paths (replenish
-- upsert, ingest_run, apollo sourcing) don't stamp user_id, so every lead sourced
-- after the backfill landed NULL-owned — invisible to the owning non-admin user
-- (both RLS and the dashboard's explicit scoping filter on user_id). A trigger
-- fixes every insert path at once, with no worker redeploy, and keeps doing so
-- for paths added later. Also re-backfills rows created between 0032 and now.
-- Idempotent; safe to re-run.

create or replace function public.lead_inherit_owner() returns trigger
language plpgsql as $$
begin
    if new.user_id is null and new.campaign_id is not null then
        select user_id into new.user_id from campaigns where id = new.campaign_id;
    end if;
    return new;
end $$;

drop trigger if exists leads_inherit_owner on leads;
create trigger leads_inherit_owner
    before insert or update of campaign_id on leads
    for each row execute function public.lead_inherit_owner();

-- catch-up for leads sourced since the 0032 backfill
update leads l set user_id = c.user_id
from campaigns c
where l.campaign_id = c.id and l.user_id is null and c.user_id is not null;
