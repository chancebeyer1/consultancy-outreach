import { NextResponse } from "next/server";

import { requireApiUser } from "@/lib/auth";
import { serverAdminClient } from "@/lib/supabase";

export const runtime = "nodejs";

const STAGES = ["interested", "call_booked", "proposal_sent", "won", "lost"];

type Admin = ReturnType<typeof serverAdminClient>;

// Ownership check for non-admin writes: a deal is theirs iff deals.user_id matches.
async function dealOwnedBy(admin: Admin, dealId: string, userId: string): Promise<boolean> {
  const { data } = await admin.from("deals").select("user_id").eq("id", dealId).maybeSingle();
  return (data as { user_id?: string | null } | null)?.user_id === userId;
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
  const gate = await requireApiUser();
  if (gate.error) return gate.error;
  const profile = gate.profile;
  const admin = serverAdminClient();

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
    title?: string;
    transcript?: string;
    meeting_id?: string;
  };
  try {
    p = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  // Every action below except `create` targets an existing deal (directly or via
  // a note) — non-admins must own that deal.
  if (!profile.isAdmin && p.action !== "create") {
    let dealId = p.id ?? null;
    if (p.action === "delete_note" && p.note_id) {
      const { data: note } = await admin
        .from("deal_notes")
        .select("deal_id")
        .eq("id", p.note_id)
        .maybeSingle();
      dealId = (note as { deal_id?: string } | null)?.deal_id ?? null;
    }
    if (!dealId || !(await dealOwnedBy(admin, dealId, profile.id))) {
      return NextResponse.json({ error: "not your deal" }, { status: 403 });
    }
  }

  if (p.action === "create") {
    const { error } = await admin.from("deals").insert({
      contact_name: p.contact_name?.trim() || null,
      company: p.company?.trim() || null,
      value_usd: numOrNull(p.value_usd),
      notes: p.notes?.trim() || null,
      stage: "interested",
      source: "manual",
      // Deals a non-admin creates belong to them; admin-created stay unowned (global).
      ...(profile.isAdmin ? {} : { user_id: profile.id }),
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

  // Attach a pasted call transcript to the deal and kick off extraction (pains, signals,
  // process candidates, follow-up draft). The Modal side spawns a background job and returns
  // instantly; the UI polls the meeting row's status.
  if (p.action === "add_meeting") {
    if (!p.id) return NextResponse.json({ error: "missing id" }, { status: 400 });
    const transcript = (p.transcript || "").trim();
    if (transcript.length < 200) {
      return NextResponse.json({ error: "transcript looks too short — paste the full call" }, { status: 400 });
    }
    if (transcript.length > 400_000) {
      return NextResponse.json({ error: "transcript too large" }, { status: 400 });
    }
    const { data: deal } = await admin
      .from("deals")
      .select("id, lead_id, user_id")
      .eq("id", p.id)
      .maybeSingle();
    if (!deal) return NextResponse.json({ error: "deal not found" }, { status: 404 });
    const { data: meeting, error } = await admin
      .from("meetings")
      .insert({
        deal_id: p.id,
        lead_id: (deal as { lead_id?: string | null }).lead_id ?? null,
        user_id: (deal as { user_id?: string | null }).user_id ?? null,
        title: p.title?.trim() || null,
        transcript,
        status: "new",
      })
      .select("id")
      .single();
    if (error) return NextResponse.json({ error: error.message }, { status: 400 });
    const meetingId = (meeting as { id: string }).id;
    const r = await callWebhook({ action: "process_meeting", meeting_id: meetingId });
    if (!r.ok) {
      // Row is saved; processing can be retried from the card.
      return NextResponse.json({ ok: true, meeting_id: meetingId, processing: false });
    }
    return NextResponse.json({ ok: true, meeting_id: meetingId, processing: true });
  }

  // Re-run extraction on an existing meeting (after a failure, or to refresh).
  if (p.action === "reprocess_meeting") {
    if (!p.id || !p.meeting_id) return NextResponse.json({ error: "missing id" }, { status: 400 });
    const { data: meeting } = await admin
      .from("meetings")
      .select("id, deal_id")
      .eq("id", p.meeting_id)
      .maybeSingle();
    if (!meeting || (meeting as { deal_id?: string | null }).deal_id !== p.id) {
      return NextResponse.json({ error: "meeting not found on this deal" }, { status: 404 });
    }
    await admin.from("meetings").update({ status: "new", error: null }).eq("id", p.meeting_id);
    const r = await callWebhook({ action: "process_meeting", meeting_id: p.meeting_id });
    return NextResponse.json({ ok: true, processing: r.ok });
  }

  return NextResponse.json({ error: "unknown action" }, { status: 400 });
}

function numOrNull(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/[^0-9.]/g, ""));
  return Number.isFinite(n) ? n : null;
}
