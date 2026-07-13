import { getCurrentProfile } from "../../lib/auth";
import { getSelectedCampaignId } from "../../lib/campaign-filter";
import { getCampaigns, getLeadRowsPage } from "../../lib/queries";
import type { LeadChannelKind, LeadDisplayStatus } from "../../lib/types";
import { LeadsClient, PAGE_SIZE } from "./_components/LeadsClient";

// Server-paginated list of leads: status/channel/search filters and the page cursor all live in
// the URL, and every filter + count is computed in SQL (lead_rows_v + lead_page_counts) — the old
// load-every-lead-then-filter-client-side path lagged hard past ~1,500 leads.
const STATUSES = new Set(["queued", "sent", "connected", "replied", "new"]);
const CHANNELS = new Set(["linkedin", "email"]);

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";
  const status = (STATUSES.has(one(sp.status)) ? one(sp.status) : "all") as
    | "all"
    | LeadDisplayStatus;
  const channel = (CHANNELS.has(one(sp.channel)) ? one(sp.channel) : "all") as
    | "all"
    | LeadChannelKind;
  const q = one(sp.q).slice(0, 100);
  const page = Math.max(1, Number.parseInt(one(sp.page), 10) || 1);

  const [campaignId, profile] = await Promise.all([getSelectedCampaignId(), getCurrentProfile()]);
  let result;
  let campaigns;
  try {
    [result, campaigns] = await Promise.all([
      getLeadRowsPage(campaignId, profile, { page, pageSize: PAGE_SIZE, status, channel, q }),
      getCampaigns(profile),
    ]);
  } catch (e) {
    // Surface the real failure on the page — an empty table with working chips cost us two
    // debugging round-trips; a visible error costs zero.
    const msg = e instanceof Error ? e.message : JSON.stringify(e);
    return (
      <div className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-xl font-semibold text-white">Leads</h1>
        <div className="mt-6 rounded-lg border border-red-900/60 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          Failed to load leads: {msg}
        </div>
      </div>
    );
  }

  return (
    <LeadsClient
      rows={result.rows}
      campaigns={campaigns}
      total={result.total}
      filteredTotal={result.filteredTotal}
      statusCounts={result.statusCounts}
      channelCounts={result.channelCounts}
      page={page}
      status={status}
      channel={channel}
      q={q}
    />
  );
}
