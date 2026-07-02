import { PageHeader } from "@/components/PageHeader";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { PipelineClient, type Deal } from "./PipelineClient";

export const dynamic = "force-dynamic";

export default async function PipelinePage() {
  let deals: Deal[] = [];
  if (dataSource === "supabase") {
    const { data } = await serverAdminClient()
      .from("deals")
      .select("id, contact_name, company, value_usd, stage, source, notes, brief, created_at, updated_at")
      .order("updated_at", { ascending: false })
      .limit(200);
    deals = (data ?? []) as Deal[];
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Pipeline"
        description="Deals from interested replies (auto-captured) and ones you add. Move them through stages and track value — so warm leads never slip."
      />
      <PipelineClient deals={deals} />
    </div>
  );
}
