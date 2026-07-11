// Server-side helper: which campaign is the dashboard currently scoped to?
//
// The selection is a plain (non-httpOnly) cookie written by the client
// <CampaignSelector> in the Nav. Server components read it here and pass the
// id into the query/analytics fetchers. `undefined` (or the sentinel "all")
// means "all campaigns" — no filter applied.

import "server-only";

import { cookies } from "next/headers";

export const CAMPAIGN_COOKIE = "campaign_id";
export const ALL_CAMPAIGNS = "all";

export async function getSelectedCampaignId(): Promise<string | undefined> {
  const store = await cookies();
  const value = store.get(CAMPAIGN_COOKIE)?.value;
  return value && value !== ALL_CAMPAIGNS ? value : undefined;
}
