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

// Call the secured Modal endpoint; returns {ok, data} so callers can read the worker's result.
async function callWebhook(payload: object): Promise<{ ok: boolean; data: Record<string, unknown> }> {
  const url = process.env.CONTENT_WEBHOOK_URL;
  const token = process.env.CONTENT_WEBHOOK_TOKEN;
  if (!url || !token) return { ok: false, data: {} };
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Content-Token": token },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  } catch {
    return { ok: false, data: {} };
  }
}

export async function POST(req: Request) {
  const gate = await requireUser();
  if (gate.error) return gate.error;
  const admin = gate.admin!;

  let p: { action?: string; id?: string; subject?: string; body?: string };
  try {
    p = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const { action } = p;

  if (action === "generate") {
    const r = await callWebhook({ action: "newsletter_generate" });
    if (!r.ok || r.data?.generated === false) {
      return NextResponse.json(
        { error: (r.data?.error as string) || "Generation needs the content endpoint configured." },
        { status: 400 },
      );
    }
    return NextResponse.json({ ok: true });
  }

  if (!p.id) return NextResponse.json({ error: "missing id" }, { status: 400 });

  if (action === "save") {
    const { error } = await admin
      .from("newsletter_issues")
      .update({ subject: p.subject, body: p.body })
      .eq("id", p.id);
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  }

  if (action === "send") {
    if (!p.body?.trim()) return NextResponse.json({ error: "empty body" }, { status: 400 });
    await admin
      .from("newsletter_issues")
      .update({ subject: p.subject, body: p.body, status: "approved" })
      .eq("id", p.id);
    const r = await callWebhook({ action: "newsletter_send", issue_id: p.id });
    if (!r.ok) {
      return NextResponse.json(
        { error: "Send endpoint unreachable. Check CONTENT_WEBHOOK_URL/TOKEN." },
        { status: 400 },
      );
    }
    if (r.data?.ok === false) {
      return NextResponse.json({ error: (r.data?.error as string) || "Send failed." }, { status: 400 });
    }
    return NextResponse.json({ ok: true, sent: r.data?.sent ?? 0 });
  }

  return NextResponse.json({ error: "unknown action" }, { status: 400 });
}
