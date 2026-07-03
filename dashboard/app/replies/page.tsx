import { getCurrentProfile } from "@/lib/auth";
import { getSelectedCampaignId } from "@/lib/campaign-filter";
import { getReplyRows } from "@/lib/queries";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { RepliesClient, type ScheduledRow } from "./_components/RepliesClient";

export const dynamic = "force-dynamic";

export default async function RepliesPage() {
  const [campaignId, profile] = await Promise.all([getSelectedCampaignId(), getCurrentProfile()]);
  const rows = await getReplyRows(campaignId, profile);

  // Pending scheduled sends ("reconnect in the fall") — shown so they can be cancelled before firing.
  let scheduled: ScheduledRow[] = [];
  if (dataSource === "supabase") {
    const admin = serverAdminClient();
    // Non-admin: only scheduled sends for their own leads (via the lead join).
    const uid = profile && !profile.isAdmin ? profile.id : null;
    let q = admin
      .from("scheduled_replies")
      .select("id, channel, due_at, body, lead_id" + (uid ? ", leads!inner(user_id)" : ""))
      .eq("status", "pending")
      .order("due_at", { ascending: true });
    if (uid) q = q.eq("leads.user_id", uid);
    const { data } = await q;
    const pending = (data ?? []) as unknown as Array<{
      id: string;
      channel: string;
      due_at: string;
      body: string;
      lead_id: string | null;
    }>;
    const leadIds = Array.from(new Set(pending.map((r) => r.lead_id as string).filter(Boolean)));
    const nameById = new Map<string, string | null>();
    if (leadIds.length) {
      const { data: leads } = await admin.from("leads").select("id, name").in("id", leadIds);
      for (const l of leads ?? []) nameById.set(l.id as string, (l.name as string | null) ?? null);
    }
    scheduled = pending.map((r) => ({
      id: r.id as string,
      channel: r.channel as string,
      due_at: r.due_at as string,
      body: r.body as string,
      lead_name: nameById.get(r.lead_id as string) ?? null,
    }));
  }

  return <RepliesClient initialRows={rows} scheduled={scheduled} />;
}
