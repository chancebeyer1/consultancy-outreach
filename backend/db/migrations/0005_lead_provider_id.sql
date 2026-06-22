-- 0005_lead_provider_id.sql — store the LinkedIn member id on leads.
--
-- provider_id (the ACoAA… member urn) keys inbound replies (webhook + poller) back
-- to the lead we contacted, so the operator's normal LinkedIn inbox stays out of
-- /replies and real broker replies land on the right lead. Idempotent.

alter table leads
    add column if not exists provider_id text;

create index if not exists leads_provider_id_idx on leads(provider_id) where provider_id is not null;
