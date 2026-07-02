import { NextResponse } from "next/server";

import { serverClient } from "@/lib/supabase";

export const runtime = "nodejs";

const REGENERATE_URL =
  "https://chanceb323--consultancy-outreach-regenerate-reply.modal.run";

async function requireUser() {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: NextResponse.json({ error: "not signed in" }, { status: 401 }) };
  return {};
}

// Re-draft the suggested reply following an operator instruction (proxies the Modal endpoint,
// which has the Claude + campaign context). Returns { suggested_reply }.
export async function POST(req: Request) {
  const gate = await requireUser();
  if (gate.error) return gate.error;

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
