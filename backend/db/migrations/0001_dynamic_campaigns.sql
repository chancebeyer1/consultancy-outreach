-- Migration 0001 — dynamic per-campaign targeting + Unipile switch
--
-- Safe to run against an existing DB created from the pre-re-architecture
-- schema. Idempotent: re-running is a no-op. Fresh installs get the same end
-- state directly from schema.sql, so you only need this if you already have data.
--
--   psql $DATABASE_URL -f db/migrations/0001_dynamic_campaigns.sql

begin;

-- 1. campaigns → persona store ------------------------------------------------
alter table campaigns add column if not exists slug        text;
alter table campaigns add column if not exists icp_md      text;
alter table campaigns add column if not exists offer_md    text;
alter table campaigns add column if not exists style_md    text;
alter table campaigns add column if not exists voice_md    text;
alter table campaigns add column if not exists landing_url text;
alter table campaigns add column if not exists calcom_url  text;
alter table campaigns add column if not exists is_default  boolean not null default false;

create unique index if not exists campaigns_slug_uidx       on campaigns(slug) where slug is not null;
create unique index if not exists campaigns_one_default_idx on campaigns(is_default) where is_default;

-- old columns are superseded by the persona fields above. Left in place for
-- back-compat; uncomment to drop once you've confirmed nothing reads them:
-- alter table campaigns drop column if exists segment;
-- alter table campaigns drop column if exists icp_query;

-- 2. leads → campaign anchor ---------------------------------------------------
alter table leads add column if not exists campaign_id uuid references campaigns(id);
create index if not exists leads_campaign_idx on leads(campaign_id);

-- 3. enrichments → profile_json rename + drop github_json ----------------------
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name = 'enrichments' and column_name = 'proxycurl_json'
  ) and not exists (
    select 1 from information_schema.columns
    where table_name = 'enrichments' and column_name = 'profile_json'
  ) then
    alter table enrichments rename column proxycurl_json to profile_json;
  end if;
end $$;
alter table enrichments add column if not exists profile_json jsonb;  -- in case neither existed
alter table enrichments drop column if exists github_json;

-- 4. sends.provider — values are now 'unipile' | 'manual' (no schema change;
--    historical 'heyreach'/'smartlead' rows are left untouched).

commit;

-- After running scripts.sync_campaigns (which creates the `_default` campaign),
-- backfill any pre-existing leads to it:
--   update leads set campaign_id = (select id from campaigns where is_default)
--   where campaign_id is null;
