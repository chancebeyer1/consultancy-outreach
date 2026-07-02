import { PageHeader } from "@/components/PageHeader";
import { dataSource, serverAdminClient } from "@/lib/supabase";

import { SendsClient, type ScheduledRow, type SentRow } from "./SendsClient";

export const dynamic = "force-dynamic";

export default async function SendsPage() {
  let scheduled: ScheduledRow[] = [];
  let sent: SentRow[] = [];

  if (dataSource === "supabase") {
    const admin = serverAdminClient();

    const { data: sch } = await admin
      .from("scheduled_replies")
      .select("id, channel, due_at, body, lead_id")
      .eq("status", "pending")
      .order("due_at", { ascending: true });
    const schRows = (sch ?? []) as Array<{ id: string; channel: string; due_at: string; body: string; lead_id: string | null }>;

    const { data: sends } = await admin
      .from("sends")
      .select("draft_id, sent_at")
      .order("sent_at", { ascending: false })
      .limit(150);
    const sendRows = (sends ?? []) as Array<{ draft_id: string; sent_at: string }>;

    const draftIds = Array.from(new Set(sendRows.map((s) => s.draft_id).filter(Boolean)));
    const draftById = new Map<string, { lead_id: string; channel: string; body: string; edited_body: string | null }>();
    if (draftIds.length) {
      const { data: drafts } = await admin.from("drafts").select("id, lead_id, channel, body, edited_body").in("id", draftIds);
      for (const d of (drafts ?? []) as Array<{ id: string; lead_id: string; channel: string; body: string; edited_body: string | null }>) {
        draftById.set(d.id, d);
      }
    }

    const leadIds = Array.from(
      new Set(
        [...schRows.map((r) => r.lead_id), ...Array.from(draftById.values()).map((d) => d.lead_id)].filter(
          (id): id is string => !!id,
        ),
      ),
    );
    const nameById = new Map<string, string | null>();
    if (leadIds.length) {
      const { data: leads } = await admin.from("leads").select("id, name").in("id", leadIds);
      for (const l of (leads ?? []) as Array<{ id: string; name: string | null }>) nameById.set(l.id, l.name ?? null);
    }

    scheduled = schRows.map((r) => ({
      id: r.id,
      channel: r.channel,
      due_at: r.due_at,
      body: r.body,
      lead_name: r.lead_id ? nameById.get(r.lead_id) ?? null : null,
    }));

    sent = sendRows.flatMap((s) => {
      const d = draftById.get(s.draft_id);
      if (!d) return []; // draft/lead was deleted (e.g. pruned non-ICP lead)
      const row: SentRow = {
        channel: d.channel,
        body: d.edited_body ?? d.body ?? "",
        lead_name: nameById.get(d.lead_id) ?? null,
        sent_at: s.sent_at,
      };
      return [row];
    });
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Sends"
        description="Your outbound log — what's queued to auto-send later, and what already went out. Since everything auto-approves now, this is where you glance at activity."
      />
      <SendsClient scheduled={scheduled} sent={sent} />
    </div>
  );
}
