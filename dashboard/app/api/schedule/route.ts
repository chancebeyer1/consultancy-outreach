import { NextResponse } from "next/server";

import { serverAdminClient, serverClient } from "@/lib/supabase";

export const runtime = "nodejs";

async function requireUser() {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: NextResponse.json({ error: "not signed in" }, { status: 401 }) };
  return { admin: serverAdminClient() };
}

// Schedule a reply to auto-send on a future date ("reconnect in the fall"). The hourly send cron
// picks up due rows. Marks the reply handled so it leaves the active queue.
export async function POST(req: Request) {
  const gate = await requireUser();
  if (gate.error) return gate.error;
  const admin = gate.admin!;

  let p: { action?: string; id?: string; replyId?: string; dueAt?: string; body?: string };
  try {
    p = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  // Cancel a pending scheduled send (before the cron fires it).
  if (p.action === "cancel") {
    if (!p.id) return NextResponse.json({ error: "missing id" }, { status: 400 });
    const { error, count } = await admin
      .from("scheduled_replies")
      .update({ status: "cancelled" }, { count: "exact" })
      .eq("id", p.id)
      .eq("status", "pending");
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true, cancelled: count ?? 0 });
  }

  const body = (p.body || "").trim();
  if (!p.replyId || !p.dueAt || !body) {
    return NextResponse.json({ error: "replyId, dueAt, body required" }, { status: 400 });
  }
  const due = new Date(p.dueAt);
  if (Number.isNaN(due.getTime()) || due.getTime() < Date.now()) {
    return NextResponse.json({ error: "dueAt must be a valid future date" }, { status: 400 });
  }

  const { data: reply } = await admin
    .from("replies")
    .select("id, lead_id, channel, chat_id")
    .eq("id", p.replyId)
    .single();
  if (!reply) return NextResponse.json({ error: "reply not found" }, { status: 404 });

  const { data: lead } = await admin.from("leads").select("provider_id").eq("id", reply.lead_id).single();

  const { error } = await admin.from("scheduled_replies").insert({
    lead_id: reply.lead_id,
    reply_id: reply.id,
    channel: reply.channel,
    chat_id: reply.chat_id,
    provider_id: lead?.provider_id ?? null,
    body,
    due_at: due.toISOString(),
    status: "pending",
  });
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });

  // Scheduled = handled; it leaves the active queue.
  await admin.from("replies").update({ handled_at: new Date().toISOString() }).eq("id", reply.id).is("handled_at", null);

  await admin
    .from("activity_log")
    .insert({
      actor: "operator",
      source: "dashboard",
      action: "reply_scheduled",
      channel: String(reply.channel || "").startsWith("linkedin") ? "linkedin" : "email",
      lead_id: reply.lead_id,
      summary: `Scheduled a follow-up for ${due.toISOString().slice(0, 10)}`,
      meta: { due_at: due.toISOString() },
    })
    .then(() => {}, () => {});

  return NextResponse.json({ ok: true, due_at: due.toISOString() });
}
