import { NextResponse } from "next/server";

import { leadOwnedBy, requireApiUser } from "@/lib/auth";
import { serverAdminClient } from "@/lib/supabase";

export const runtime = "nodejs";

const LINKEDIN_THREAD_URL =
  "https://chanceb323--consultancy-outreach-linkedin-thread.modal.run";

type ThreadMsg = { from_me: boolean; text: string; at: string | null };

// Full conversation thread for a reply. LinkedIn is fetched live from Unipile via the Modal
// endpoint; email is reconstructed from the unified inbox (both directions). Read-only.
export async function POST(req: Request) {
  const gate = await requireApiUser();
  if (gate.error) return gate.error;
  const profile = gate.profile;
  const admin = serverAdminClient();

  let payload: { replyId?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (!payload.replyId) return NextResponse.json({ error: "missing replyId" }, { status: 400 });

  const { data: reply } = await admin
    .from("replies")
    .select("id, lead_id, channel, chat_id")
    .eq("id", payload.replyId)
    .single();
  if (!reply) return NextResponse.json({ error: "reply not found" }, { status: 404 });

  // Non-admins may only read threads on their own leads.
  if (!profile.isAdmin && !(await leadOwnedBy(reply.lead_id, profile.id))) {
    return NextResponse.json({ error: "not your reply" }, { status: 403 });
  }

  const isLinkedIn = String(reply.channel || "").startsWith("linkedin");

  if (isLinkedIn) {
    const { data: lead } = await admin
      .from("leads")
      .select("provider_id, linkedin_url")
      .eq("id", reply.lead_id)
      .single();
    const token = process.env.CONTENT_WEBHOOK_TOKEN;
    const url = process.env.LINKEDIN_THREAD_URL || LINKEDIN_THREAD_URL;
    if (!token) return NextResponse.json({ channel: "linkedin", messages: [], note: "not configured" });
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, chat_id: reply.chat_id, provider_id: lead?.provider_id }),
      });
      const data = (await res.json().catch(() => ({}))) as { messages?: ThreadMsg[] };
      return NextResponse.json({ channel: "linkedin", messages: data?.messages ?? [] });
    } catch (e) {
      return NextResponse.json({
        channel: "linkedin",
        messages: [],
        note: e instanceof Error ? e.message : "failed",
      });
    }
  }

  // Email: reconstruct from the unified inbox.
  const { data: msgs } = await admin
    .from("inbox_messages")
    .select("body, direction, received_at")
    .eq("lead_id", reply.lead_id)
    .order("received_at", { ascending: true })
    .limit(100);
  const messages: ThreadMsg[] = (msgs ?? []).map((m) => ({
    from_me: m.direction === "out",
    text: m.body || "",
    at: m.received_at,
  }));
  return NextResponse.json({ channel: "email", messages });
}
