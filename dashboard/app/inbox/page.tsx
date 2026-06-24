import { getSelectedCampaignId } from "@/lib/campaign-filter";
import { getCampaigns, getInboxMessages } from "@/lib/queries";

import { InboxClient } from "./InboxClient";

export const dynamic = "force-dynamic";

export default async function InboxPage() {
  const campaignId = await getSelectedCampaignId();
  const [messages, campaigns] = await Promise.all([getInboxMessages(campaignId), getCampaigns()]);
  const nameById = new Map(campaigns.map((c) => [c.id, c.name]));
  const rows = messages.map((m) => ({
    ...m,
    campaign: m.campaign_id ? (nameById.get(m.campaign_id) ?? null) : null,
  }));
  return <InboxClient messages={rows} />;
}
