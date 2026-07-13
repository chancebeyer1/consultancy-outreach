-- 0042 — lead_rows_page(): one RPC returning a filtered/paginated page of lead rows + total.
--
-- The dashboard's REST select against lead_rows_v behaved inconsistently in the deployed runtime
-- (row count returned, rows empty) while the RPC path (lead_page_counts) worked everywhere from
-- day one. Rather than fight the PostgREST/view interaction, the rows fetch moves onto the same
-- proven mechanism: one function, one round-trip, filters + order + paging in SQL.

create or replace function lead_rows_page(
  p_campaign uuid default null,
  p_user uuid default null,
  p_q text default null,
  p_status text default null,
  p_channel text default null,
  p_limit int default 50,
  p_offset int default 0
) returns jsonb
language sql stable security invoker as $$
  with base as (
    select *
    from lead_rows_v
    where (p_campaign is null or campaign_id = p_campaign)
      and (p_user is null or user_id = p_user)
      and (
        p_q is null or p_q = '' or
        (coalesce(name, '') || ' ' || coalesce(company, '') || ' ' || coalesce(role, '') || ' ' ||
         coalesce(email, '') || ' ' || coalesce(location, '')) ilike '%' || p_q || '%'
      )
      and (p_status is null or display_status = p_status)
      and (p_channel is null or p_channel = any(channels))
  )
  select jsonb_build_object(
    'filtered_total', (select count(*) from base),
    'rows', coalesce((
      select jsonb_agg(row_to_json(t))
      from (
        select * from base
        order by updated_at desc
        limit least(greatest(p_limit, 1), 200)
        offset greatest(p_offset, 0)
      ) t
    ), '[]'::jsonb)
  )
$$;
