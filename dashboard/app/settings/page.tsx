import { PageHeader } from "@/components/PageHeader";
import { requireAdmin } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { SettingsClient } from "./SettingsClient";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  await requireAdmin();
  let operatorBio = "";
  if (dataSource === "supabase") {
    const { data } = await serverAdminClient()
      .from("app_settings")
      .select("value")
      .eq("key", "operator_bio")
      .maybeSingle();
    if (typeof data?.value === "string") operatorBio = data.value;
  }
  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Settings"
        description="Your operator profile — the background the AI treats as true about you when drafting replies and outreach in your voice."
      />
      <SettingsClient operatorBio={operatorBio} />
    </div>
  );
}
