-- 0015 — deal pipeline / lightweight CRM.
--
-- A "deal" is an opportunity tracked through stages to won/lost. Deals are auto-created when a
-- reply is classified 'interested' (one open deal per lead, enforced by the partial unique
-- index) and can also be added by hand. The dashboard moves them through stages + tracks value.

create table if not exists deals (
    id           uuid primary key default gen_random_uuid(),
    lead_id      uuid references leads(id),
    campaign_id  uuid references campaigns(id),
    user_id      uuid,
    contact_name text,
    company      text,
    value_usd    numeric,
    stage        text not null default 'interested',  -- interested|call_booked|proposal_sent|won|lost
    source       text,                                  -- reply|manual|warm_signal|inbound
    notes        text,
    next_action  text,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    closed_at    timestamptz
);
create index if not exists deals_stage_idx on deals(stage, updated_at desc);
-- At most one OPEN deal per lead, so auto-create from replies is idempotent.
create unique index if not exists deals_open_lead_idx
    on deals(lead_id) where lead_id is not null and stage not in ('won', 'lost');
alter table deals enable row level security;  -- service-role only
