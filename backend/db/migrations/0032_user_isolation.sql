-- 0032 — user isolation: make multi-tenancy real.
-- Phase 3 of multi-user: 0012 added profiles + user_id columns (inert), 0013 enabled
-- RLS on a few tables with no policies. This migration (a) backfills ownership of all
-- existing rows to user #1, (b) FKs user_id to profiles, (c) defines is_admin() and
-- per-user RLS policies so a signed-in non-admin (the second user) can only ever read
-- or write rows they own — even through the anon-key client. Workers (postgres role,
-- table owner) and the dashboard's service-role client bypass RLS by design; the
-- dashboard additionally filters explicitly per user in queries.ts.
-- Also adds per-profile LinkedIn send caps (li_daily_cap / li_weekly_cap) so a fresh
-- second account ramps conservatively instead of inheriting the warmed global caps.
-- Idempotent; safe to re-run.

-- ---------------------------------------------------------------
-- 0. Per-profile LinkedIn caps (null → global sender_limits caps)
-- ---------------------------------------------------------------
alter table profiles add column if not exists li_daily_cap  int;
alter table profiles add column if not exists li_weekly_cap int;

-- ---------------------------------------------------------------
-- 1. Backfill ownership to user #1 (the operator)
-- ---------------------------------------------------------------
do $$
declare
    owner_id uuid := '3b1fa28e-8193-40a4-aa27-79cd3d1be398';
begin
    if not exists (select 1 from profiles where id = owner_id) then
        raise exception 'owner profile % missing — aborting backfill', owner_id;
    end if;
    update campaigns     set user_id = owner_id where user_id is null;
    -- leads inherit their campaign's owner; orphans go to user #1
    update leads l set user_id = coalesce(c.user_id, owner_id)
        from campaigns c where l.campaign_id = c.id and l.user_id is null;
    update leads         set user_id = owner_id where user_id is null;
    update mailboxes     set user_id = owner_id where user_id is null;
    update deals         set user_id = owner_id where user_id is null;
    update deal_notes    set user_id = owner_id where user_id is null;
    update content_posts set user_id = owner_id where user_id is null;
    update comment_queue set user_id = owner_id where user_id is null;
end $$;

-- ---------------------------------------------------------------
-- 2. FK user_id → profiles (added post-backfill so they validate)
-- ---------------------------------------------------------------
do $$
declare
    t text;
begin
    foreach t in array array['campaigns','leads','mailboxes','deals','deal_notes',
                             'content_posts','comment_queue'] loop
        if not exists (
            select 1 from pg_constraint
            where conname = t || '_user_id_fkey' and conrelid = t::regclass
        ) then
            execute format(
                'alter table %I add constraint %I foreign key (user_id) '
                'references profiles(id) on delete set null', t, t || '_user_id_fkey');
        end if;
    end loop;
end $$;

-- ---------------------------------------------------------------
-- 3. is_admin() — security definer so policies can check the flag
--    without recursing into profiles' own RLS
-- ---------------------------------------------------------------
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as
$$ select coalesce((select is_admin from profiles where id = auth.uid()), false) $$;

-- ---------------------------------------------------------------
-- 4. RLS — direct user_id tables
--    (drop+create: CREATE POLICY has no IF NOT EXISTS)
-- ---------------------------------------------------------------
do $$
declare
    t text;
begin
    foreach t in array array['campaigns','leads','mailboxes','deals','deal_notes',
                             'content_posts','comment_queue'] loop
        execute format('alter table %I enable row level security', t);
        execute format('drop policy if exists %I on %I', t || '_owner_all', t);
        execute format(
            'create policy %I on %I for all to authenticated '
            'using (is_admin() or user_id = auth.uid()) '
            'with check (is_admin() or user_id = auth.uid())',
            t || '_owner_all', t);
    end loop;
end $$;

-- profiles: RLS already enabled in 0013; add the promised policies.
drop policy if exists profiles_self_select on profiles;
create policy profiles_self_select on profiles for select to authenticated
    using (is_admin() or id = auth.uid());
drop policy if exists profiles_self_update on profiles;
create policy profiles_self_update on profiles for update to authenticated
    using (id = auth.uid()) with check (id = auth.uid());

-- ---------------------------------------------------------------
-- 5. RLS — lead-child tables (ownership via leads.user_id)
-- ---------------------------------------------------------------
do $$
declare
    t text;
begin
    foreach t in array array['enrichments','scores','drafts','replies',
                             'sequence_state'] loop
        execute format('alter table %I enable row level security', t);
        execute format('drop policy if exists %I on %I', t || '_owner_all', t);
        execute format(
            'create policy %I on %I for all to authenticated '
            'using (is_admin() or exists (select 1 from leads l '
            '       where l.id = %I.lead_id and l.user_id = auth.uid())) '
            'with check (is_admin() or exists (select 1 from leads l '
            '       where l.id = %I.lead_id and l.user_id = auth.uid()))',
            t || '_owner_all', t, t, t);
    end loop;
end $$;

-- sends hang off drafts, not leads
alter table sends enable row level security;
drop policy if exists sends_owner_all on sends;
create policy sends_owner_all on sends for all to authenticated
    using (is_admin() or exists (
        select 1 from drafts d join leads l on l.id = d.lead_id
        where d.id = sends.draft_id and l.user_id = auth.uid()))
    with check (is_admin() or exists (
        select 1 from drafts d join leads l on l.id = d.lead_id
        where d.id = sends.draft_id and l.user_id = auth.uid()));
