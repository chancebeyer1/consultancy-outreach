-- 2026-08-18: scheduled_replies was created after the Phase-2 RLS pass and shipped with RLS
-- off while carrying the default anon/authenticated grants, so it was readable through the
-- public Data API (Supabase Security Advisor error). All dashboard access goes through the
-- service-role server client and workers connect as the table owner, both of which bypass
-- RLS, so enabling it with no policies blocks the public API and changes nothing else.
alter table public.scheduled_replies enable row level security;
