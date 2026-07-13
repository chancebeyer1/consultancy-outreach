-- 0041 — lead_page_counts(): all /leads filter-chip counts in ONE scan.
--
-- The paginated leads page needs total + per-status + per-channel counts for its chips. Eight
-- separate head-count queries against lead_rows_v would each re-scan the view (~800ms apiece);
-- this function computes them all from a single pass. security invoker, so RLS applies.

create index if not exists leads_updated_idx on leads(updated_at desc);

create or replace function lead_page_counts(
  p_campaign uuid default null,
  p_user uuid default null,
  p_q text default null
) returns jsonb
language sql stable security invoker as $$
  with base as (
    select display_status, channels
    from lead_rows_v
    where (p_campaign is null or campaign_id = p_campaign)
      and (p_user is null or user_id = p_user)
      and (
        p_q is null or p_q = '' or
        (coalesce(name, '') || ' ' || coalesce(company, '') || ' ' || coalesce(role, '') || ' ' ||
         coalesce(email, '') || ' ' || coalesce(location, '')) ilike '%' || p_q || '%'
      )
  )
  select jsonb_build_object(
    'total', (select count(*) from base),
    'status', (
      select coalesce(jsonb_object_agg(display_status, n), '{}'::jsonb)
      from (select display_status, count(*) as n from base group by 1) s
    ),
    'channels', jsonb_build_object(
      'linkedin', (select count(*) from base where 'linkedin' = any(channels)),
      'email', (select count(*) from base where 'email' = any(channels))
    )
  )
$$;
