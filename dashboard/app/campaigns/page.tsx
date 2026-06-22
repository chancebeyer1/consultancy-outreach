import { getCampaigns } from "@/lib/queries";
import { dataSource } from "@/lib/supabase";

import { CampaignsClient } from "./_components/CampaignsClient";

export default async function CampaignsPage() {
  const campaigns = await getCampaigns();
  return (
    <CampaignsClient initialCampaigns={campaigns} writable={dataSource === "supabase"} mode={dataSource} />
  );
}
