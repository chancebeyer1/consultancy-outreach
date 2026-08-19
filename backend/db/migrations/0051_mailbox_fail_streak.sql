-- 2026-08-19: consecutive-failure counter per mailbox. One failed sweep is a blip (mail
-- waits server-side for the next sweep); 3+ consecutive is a real outage worth paging on.
alter table public.mailboxes add column if not exists imap_fail_streak int not null default 0;
