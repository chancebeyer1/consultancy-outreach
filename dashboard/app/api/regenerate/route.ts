import { NextResponse } from "next/server";

import { leadOwnedBy, requireApiUser } from "@/lib/auth";
import { serverAdminClient } from "@/lib/supabase";

export const runtime = "nodejs";

const REGENERATE_URL =
  "https://chanceb323--consultancy-outreach-regenerate-reply.modal.run";

// Re-draft the suggested reply following an operator instruction (proxies the Modal endpoint,
// which has the Claude + campaign context). Returns { suggested_reply }.
export async function POST(req: Request) {
  const gate = await requireApiUser();
  if (gate.error) return gate.error;
  const profile = gate.profile;

  let payload: { replyId?: string; instruction?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const replyId = payload.replyId;
  const instruction = (payload.instruction || "").trim();
  if (!replyId || !instruction) {
    return NextResponse.json({ error: "replyId + instruction required" }, { status: 400 });
  }

  // Non-admins may only regenerate suggestions for replies on their own leads.
  if (!profile.isAdmin) {
    const { data: reply } = await serverAdminClient()
      .from("replies")
      .select("lead_id")
      .eq("id", replyId)
      .maybeSingle();
    if (!reply || !(await leadOwnedBy(reply.lead_id as string | null, profile.id))) {
      return NextResponse.json({ error: "not your reply" }, { status: 403 });
    }
  }

  const token = process.env.CONTENT_WEBHOOK_TOKEN;
  const url = process.env.REGENERATE_REPLY_URL || REGENERATE_URL;
  if (!token) return NextResponse.json({ error: "not configured (set CONTENT_WEBHOOK_TOKEN)" }, { status: 503 });

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, reply_id: replyId, instruction }),
    });
    const data = (await res.json().catch(() => ({}))) as { suggested_reply?: string; detail?: string };
    if (!res.ok || !data.suggested_reply) {
      return NextResponse.json({ error: data.detail || `regenerate failed (${res.status})` }, { status: 502 });
    }
    return NextResponse.json({ ok: true, suggested_reply: data.suggested_reply });
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : "unreachable" }, { status: 502 });
  }
}
