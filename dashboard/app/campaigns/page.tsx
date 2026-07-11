import { requireAdmin } from "@/lib/auth";
import { getCampaigns } from "@/lib/queries";
import { dataSource } from "@/lib/supabase";

import { CampaignsClient } from "./_components/CampaignsClient";

export default async function CampaignsPage() {
  await requireAdmin();
  const campaigns = await getCampaigns();
  return (
    <CampaignsClient initialCampaigns={campaigns} writable={dataSource === "supabase"} mode={dataSource} />
  );
}
