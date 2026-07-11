-- 0033 — drop the prototype-era "Allow anon select *" policies.
-- These granted SELECT true to role public (= anon AND authenticated) on the core
-- outreach tables. Permissive policies OR together, so they silently defeated the
-- per-user isolation added in 0032 — and had exposed all lead/campaign data to the
-- bare anon key since the early supabase-mode prototype. The dashboard reads as
-- `authenticated` (covered by 0032's *_owner_all policies) or `service_role`
-- (bypasses RLS); nothing legitimate reads these tables as anon.
-- Idempotent; safe to re-run.

drop policy if exists "Allow anon select campaigns"      on campaigns;
drop policy if exists "Allow anon select leads"          on leads;
drop policy if exists "Allow anon select drafts"         on drafts;
drop policy if exists "Allow anon select enrichments"    on enrichments;
drop policy if exists "Allow anon select scores"         on scores;
drop policy if exists "Allow anon select sends"          on sends;
drop policy if exists "Allow anon select replies"        on replies;
drop policy if exists "Allow anon select sequence_state" on sequence_state;
