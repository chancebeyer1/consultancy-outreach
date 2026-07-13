-- 0040 — lead_rows_v: the /leads page's derived row, computed in SQL.
--
-- The dashboard used to load EVERY lead (range-paging past the 1000-row cap) plus four chunked
-- side-queries (scores/drafts/replies/sends over ~2k ids) just to derive each lead's display
-- status client-side — at 1,800+ leads the page lagged hard. This view moves the derivation into
-- Postgres so the page can filter + paginate server-side and fetch exactly one page.
--
-- security_invoker: the view runs with the QUERYING user's rights, so the underlying tables' RLS
-- still applies (a plain view would silently bypass it with the owner's rights).

create or replace view lead_rows_v
with (security_invoker = true) as
select
  l.*,
  sc.fit_score,
  ds.last_sent_at,
  case
    when er.has_reply then 'replied'
    when l.accepted_at is not null then 'connected'
    when ds.last_sent_at is not null then 'sent'
    when coalesce(ds.has_pending, false) then 'queued'
    else 'new'
  end as display_status,
  case
    when ds.channels is not null and array_length(ds.channels, 1) > 0 then ds.channels
    when l.email is not null then array['email']
    else array['linkedin']
  end as channels
from leads l
left join lateral (
  select s.fit_score from scores s where s.lead_id = l.id order by s.scored_at desc nulls last limit 1
) sc on true
left join lateral (
  select
    max(s.sent_at) as last_sent_at,
    bool_or(d.status in ('draft', 'approved')) as has_pending,
    array_remove(array_agg(distinct case
        when d.channel like 'linkedin%' then 'linkedin'
        when d.channel like 'email%' then 'email'
      end), null) as channels
  from drafts d
  left join sends s on s.draft_id = d.id
  where d.lead_id = l.id
) ds on true
left join lateral (
  select exists (select 1 from replies r where r.lead_id = l.id) as has_reply
) er on true;

-- The lateral subqueries hit these hot paths on every row — make sure they're indexed.
create index if not exists drafts_lead_idx on drafts(lead_id);
create index if not exists replies_lead_idx on replies(lead_id);
create index if not exists scores_lead_idx on scores(lead_id);
create index if not exists sends_draft_idx on sends(draft_id);
