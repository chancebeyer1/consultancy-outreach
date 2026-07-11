-- 0021 — timestamped notes / activity log for a deal (the CRM detail page).
-- Each deal gets a chronological feed of notes the operator adds. Separate from deals.notes
-- (a one-line summary) and deals.next_action (the next step).
create table if not exists deal_notes (
    id         uuid primary key default gen_random_uuid(),
    deal_id    uuid references deals(id) on delete cascade,
    user_id    uuid,
    body       text not null,
    created_at timestamptz not null default now()
);
create index if not exists deal_notes_deal_idx on deal_notes(deal_id, created_at desc);
alter table deal_notes enable row level security;  -- service-role only (read via serverAdminClient)
