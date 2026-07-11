-- 0013 — enable RLS on apollo_seen + profiles (Supabase linter: rls_disabled_in_public)
--
-- Both were created without RLS and are exposed to PostgREST (the anon API). Neither is read
-- via the anon key (workers use the owner/service-role connection, which bypasses RLS; the
-- dashboard reads them, if at all, via serverAdminClient). Enable RLS with NO anon policy so
-- the public API can't read them. profiles will get a per-user policy (auth.uid() = id) when
-- Supabase Auth lands in the multi-user phase.
-- Idempotent; safe to re-run.

alter table apollo_seen enable row level security;
alter table profiles    enable row level security;
