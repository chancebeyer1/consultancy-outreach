-- 0007_lead_accepted_at.sql — track LinkedIn connection acceptance.
--
-- Set when the connection-detector finds a lead we invited is now a 1st-degree
-- connection. Gates the post-accept DM (only sent to real connections) and drives
-- the "Connected" status in /leads. Idempotent.

alter table leads
    add column if not exists accepted_at timestamptz;

create index if not exists leads_accepted_idx on leads(accepted_at) where accepted_at is not null;
