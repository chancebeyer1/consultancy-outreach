-- 0043 — revival nudges ride scheduled_replies.
--
-- kind distinguishes operator-scheduled sends ('manual') from agent-drafted revival nudges
-- ('revival'). Revival rows are created with status='draft' and NEVER send until the operator
-- approves them on /replies (draft -> pending); the existing due-scheduler then fires them.
alter table scheduled_replies add column if not exists kind text not null default 'manual';
create index if not exists scheduled_replies_kind_idx on scheduled_replies(kind, status);
