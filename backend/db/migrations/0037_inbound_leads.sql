-- 0037 — inbound / paid leads: let the pipeline accept leads that don't come from
-- LinkedIn (Meta/Google lead ads, website forms, CSV sphere imports). leads.linkedin_url
-- was NOT NULL UNIQUE — only ever true for Sales-Nav sourced leads. Relax it and add the
-- inbound identity + routing columns so a hand-raiser from an ad flows into the same
-- score→draft→respond pipeline, tagged to the right campaign (and, via the 0034 trigger,
-- the right owner). Reusable for any inbound source, not just Meta. Idempotent.

-- linkedin_url optional now. Postgres unique indexes allow multiple NULLs, so the existing
-- UNIQUE stays valid — LinkedIn leads still can't duplicate, inbound leads just carry NULL.
alter table leads alter column linkedin_url drop not null;

alter table leads add column if not exists phone        text;
alter table leads add column if not exists email        text;   -- may already exist (0009)
alter table leads add column if not exists external_id  text;   -- provider lead id (Meta leadgen_id) for dedup
alter table leads add column if not exists form_payload jsonb;  -- raw inbound form answers

-- Dedup inbound leads by their provider id (a Meta webhook can fire more than once).
create unique index if not exists leads_external_id_uidx
    on leads(external_id) where external_id is not null;

-- Routing: each ad lead-form (or website form) the operator creates is tied to a campaign
-- here, so the webhook can map an incoming leadgen event → campaign → owner with no
-- per-lead guesswork. platform lets one table serve Meta, Google, and site forms.
create table if not exists lead_ad_forms (
    form_id     text primary key,               -- Meta lead-form id, or 'website:<slug>', etc.
    campaign_id uuid references campaigns(id) on delete cascade,
    platform    text not null default 'meta',   -- meta | google | website
    label       text,
    created_at  timestamptz not null default now()
);

-- Config table (like provider_cooldowns / mailboxes): service-role + admin only, no anon.
alter table lead_ad_forms enable row level security;
drop policy if exists lead_ad_forms_admin_all on lead_ad_forms;
create policy lead_ad_forms_admin_all on lead_ad_forms for all to authenticated
    using (is_admin()) with check (is_admin());
