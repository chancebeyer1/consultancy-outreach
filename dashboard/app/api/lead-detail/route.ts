import { NextResponse } from "next/server";

import { leadOwnedBy, requireApiUser } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

export const runtime = "nodejs";

// Detail payload for the expandable row on /leads: why the lead scored the way it
// did, plus every drafted/sent message with its status. Read-only.
export async function POST(req: Request) {
  // Mock/file mode has no DB or auth — return an empty detail so the UI works offline.
  if (dataSource !== "supabase") {
    return NextResponse.json({ score: null, hooks: [], messages: [] });
  }
  const gate = await requireApiUser();
  if (gate.error) return gate.error;
  const profile = gate.profile;
  const admin = serverAdminClient();

  let payload: { leadId?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (!payload.leadId) return NextResponse.json({ error: "missing leadId" }, { status: 400 });

  // Non-admins may only inspect their own leads.
  if (!profile.isAdmin && !(await leadOwnedBy(payload.leadId, profile.id))) {
    return NextResponse.json({ error: "not your lead" }, { status: 403 });
  }

  const [{ data: score }, { data: drafts }, { data: enrichment }] = await Promise.all([
    admin
      .from("scores")
      .select("fit_score, rationale")
      .eq("lead_id", payload.leadId)
      .maybeSingle(),
    admin
      .from("drafts")
      .select("id, channel, step_index, variant, status, body, edited_body, generated_at")
      .eq("lead_id", payload.leadId)
      .order("channel")
      .order("step_index"),
    admin
      .from("enrichments")
      .select("hooks_json")
      .eq("lead_id", payload.leadId)
      .maybeSingle(),
  ]);

  // Attach send status per draft (sends hang off draft_id).
  const draftIds = (drafts ?? []).map((d) => d.id as string);
  let sendsByDraft = new Map<string, { status: string; sent_at: string | null }>();
  if (draftIds.length) {
    const { data: sends } = await admin
      .from("sends")
      .select("draft_id, status, sent_at")
      .in("draft_id", draftIds)
      .order("sent_at", { ascending: false });
    sendsByDraft = new Map(
      (sends ?? []).map((s) => [
        s.draft_id as string,
        { status: s.status as string, sent_at: (s.sent_at as string) ?? null },
      ]),
    );
  }

  const hooks = Array.isArray(enrichment?.hooks_json)
    ? (enrichment?.hooks_json as Array<{ type?: string; reference?: string }>).map((h) => ({
        type: h?.type ?? null,
        reference: h?.reference ?? null,
      }))
    : [];

  return NextResponse.json({
    score: score ?? null,
    hooks,
    messages: (drafts ?? []).map((d) => ({
      id: d.id,
      channel: d.channel,
      step_index: d.step_index,
      variant: d.variant,
      status: d.status,
      body: (d.edited_body as string | null) || (d.body as string | null) || "",
      generated_at: d.generated_at,
      send: sendsByDraft.get(d.id as string) ?? null,
    })),
  });
}
