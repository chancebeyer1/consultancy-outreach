-- 0036 — automatic LinkedIn cap ramp-up (workers/ramp.py).
-- li_ramp_target opts a profile into the auto-ramp ladder (5→10→15→20/day) toward
-- that ceiling; li_cap_updated_at stamps every cap change and doubles as the
-- one-change-per-~20h rate limiter. Enables the ramp for Tanner (target 20/day).
-- Idempotent; safe to re-run.

alter table profiles add column if not exists li_ramp_target int;
alter table profiles add column if not exists li_cap_updated_at timestamptz;

update profiles
set li_ramp_target = 20,
    li_cap_updated_at = coalesce(li_cap_updated_at, now())
where email = 'tannerbuyhomes@gmail.com' and li_ramp_target is null;
