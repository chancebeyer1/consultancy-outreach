import { NextResponse } from "next/server";

import { serverAdminClient, serverClient } from "@/lib/supabase";

export const runtime = "nodejs";

const STAGES = ["interested", "call_booked", "proposal_sent", "won", "lost"];

async function requireUser() {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: NextResponse.json({ error: "not signed in" }, { status: 401 }) };
  return { admin: serverAdminClient() };
}

// Trigger the secured Modal endpoint (deal research). No-op if not configured.
async function callWebhook(payload: object): Promise<{ ok: boolean }> {
  const url = process.env.CONTENT_WEBHOOK_URL;
  const token = process.env.CONTENT_WEBHOOK_TOKEN;
  if (!url || !token) return { ok: false };
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Content-Token": token },
      body: JSON.stringify(payload),
    });
    return { ok: res.ok };
  } catch {
    return { ok: false };
  }
}

export async function POST(req: Request) {
  const gate = await requireUser();
  if (gate.error) return gate.error;
  const admin = gate.admin!;

  let p: {
    action?: string;
    id?: string;
    contact_name?: string;
    company?: string;
    value_usd?: number | string | null;
    stage?: string;
    notes?: string;
    next_action?: string;
    body?: string;
    note_id?: string;
  };
  try {
    p = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  if (p.action === "create") {
    const { error } = await admin.from("deals").insert({
      contact_name: p.contact_name?.trim() || null,
      company: p.company?.trim() || null,
      value_usd: numOrNull(p.value_usd),
      notes: p.notes?.trim() || null,
      stage: "interested",
      source: "manual",
    });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  }

  if (p.action === "update") {
    if (!p.id) return NextResponse.json({ error: "missing id" }, { status: 400 });
    const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
    if (p.stage !== undefined) {
      if (!STAGES.includes(p.stage)) return NextResponse.json({ error: "bad stage" }, { status: 400 });
      patch.stage = p.stage;
      patch.closed_at = p.stage === "won" || p.stage === "lost" ? new Date().toISOString() : null;
    }
    if (p.value_usd !== undefined) patch.value_usd = numOrNull(p.value_usd);
    if (p.notes !== undefined) patch.notes = p.notes?.trim() || null;
    if (p.next_action !== undefined) patch.next_action = p.next_action?.trim() || null;
    if (p.contact_name !== undefined) patch.contact_name = p.contact_name?.trim() || null;
    if (p.company !== undefined) patch.company = p.company?.trim() || null;

    const { error } = await admin.from("deals").update(patch).eq("id", p.id);
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  }

  if (p.action === "add_note") {
    if (!p.id || !p.body?.trim()) return NextResponse.json({ error: "empty note" }, { status: 400 });
    const { error } = await admin.from("deal_notes").insert({ deal_id: p.id, body: p.body.trim() });
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  }

  if (p.action === "delete_note") {
    if (!p.note_id) return NextResponse.json({ error: "missing note_id" }, { status: 400 });
    const { error } = await admin.from("deal_notes").delete().eq("id", p.note_id);
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    return NextResponse.json({ ok: true });
  }

  if (p.action === "prepare") {
    if (!p.id) return NextResponse.json({ error: "missing id" }, { status: 400 });
    const r = await callWebhook({ action: "prepare_deal", deal_id: p.id });
    if (!r.ok) {
      return NextResponse.json(
        { error: "Endpoint not set up yet — the hourly cron will research this deal instead." },
        { status: 400 },
      );
    }
    return NextResponse.json({ ok: true });
  }

  return NextResponse.json({ error: "unknown action" }, { status: 400 });
}

function numOrNull(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/[^0-9.]/g, ""));
  return Number.isFinite(n) ? n : null;
}
