// Persists bid-review decisions from /bids.
//
// Actions:
//   save      — store your edits to the proposal body (no status change)
//   approve   — mark the bid ready to submit (bid.approved, opportunity.approved)
//   reject    — discard the drafted bid            (bid.rejected, opportunity.passed)
//   submit    — you submitted it on the portal      (bid.submitted, opportunity.submitted)
//   pass      — drop an opportunity with no bid      (opportunity.passed)
//
// Nothing here contacts an external portal — the operator submits by hand (federal
// solicitations and Upwork proposals cannot/​must-not be auto-submitted). This only
// records the decision so the queue reflects it.
//
// - mock     mode: 204 no-op.
// - supabase mode: owner (or admin) only; updates bids + opportunities.status.

import { NextResponse } from "next/server";

import { requireApiUser } from "@/lib/auth";
import { dataSource, serverAdminClient } from "@/lib/supabase";

type BidAction = "save" | "approve" | "reject" | "submit" | "pass";

interface BidDecisionPayload {
  opportunity_id: string;
  bid_id?: string | null;
  action: BidAction;
  edited_body?: string | null;
  rejection_reason?: string | null;
}

// Queue hygiene: pass every still-undecided, undrafted opportunity under a fit threshold in
// one call. Only touches status new/scored — drafted/approved rows always need human eyes.
interface BulkPassPayload {
  action: "bulk_pass";
  max_fit: number;
}

const ACTIONS: BidAction[] = ["save", "approve", "reject", "submit", "pass"];

function isValid(p: unknown): p is BidDecisionPayload {
  if (!p || typeof p !== "object") return false;
  const o = p as Record<string, unknown>;
  return typeof o.opportunity_id === "string" && ACTIONS.includes(o.action as BidAction);
}

function isBulkPass(p: unknown): p is BulkPassPayload {
  if (!p || typeof p !== "object") return false;
  const o = p as Record<string, unknown>;
  return o.action === "bulk_pass" && typeof o.max_fit === "number" && o.max_fit >= 0 && o.max_fit <= 100;
}

// Map an action → (bid fields, opportunity.status). Some actions touch only one table.
function bidPatch(action: BidAction, payload: BidDecisionPayload): Record<string, unknown> | null {
  const now = new Date().toISOString();
  switch (action) {
    case "save":
      return { edited_body: payload.edited_body ?? null };
    case "approve":
      return { status: "approved", edited_body: payload.edited_body ?? null, decided_at: now };
    case "reject":
      return { status: "rejected", rejection_reason: payload.rejection_reason ?? null, decided_at: now };
    case "submit":
      return {
        status: "submitted",
        edited_body: payload.edited_body ?? null,
        decided_at: now,
        submitted_at: now,
      };
    case "pass":
      return null; // opportunity-only
  }
}

function oppStatus(action: BidAction): string | null {
  return { save: null, approve: "approved", reject: "passed", submit: "submitted", pass: "passed" }[action];
}

export async function POST(request: Request) {
  if (dataSource === "mock") {
    return NextResponse.json({ persisted: false, reason: "mock mode" });
  }
  if (dataSource !== "supabase") {
    return NextResponse.json({ error: `unsupported in ${dataSource} mode` }, { status: 400 });
  }

  const payload = (await request.json()) as unknown;
  if (!isValid(payload) && !isBulkPass(payload)) {
    return NextResponse.json({ error: "invalid payload" }, { status: 400 });
  }

  const gate = await requireApiUser();
  if (gate.error) return gate.error;

  const admin = serverAdminClient();

  if (isBulkPass(payload)) {
    let q = admin
      .from("opportunities")
      .update({ status: "passed" }, { count: "exact" })
      .in("status", ["new", "scored"])
      .lt("fit_score", payload.max_fit);
    if (!gate.profile.isAdmin) q = q.eq("user_id", gate.profile.id);
    const { error, count } = await q;
    if (error) {
      console.error("[bids] bulk pass failed", error);
      return NextResponse.json({ persisted: false, error: error.message }, { status: 500 });
    }
    return NextResponse.json({ persisted: true, passed: count ?? 0 });
  }

  // Owner check: non-admins may only decide on opportunities they own.
  if (!gate.profile.isAdmin) {
    const { data: opp } = await admin
      .from("opportunities")
      .select("user_id")
      .eq("id", payload.opportunity_id)
      .maybeSingle();
    if (!opp || opp.user_id !== gate.profile.id) {
      return NextResponse.json({ error: "not your opportunity" }, { status: 403 });
    }
  }

  try {
    const patch = bidPatch(payload.action, payload);
    if (patch) {
      // Always scope by the owner-checked opportunity_id — bid_id alone would let a caller
      // who owns opportunity A pass the gate yet write to a bid on someone else's opportunity.
      let q = admin.from("bids").update(patch).eq("opportunity_id", payload.opportunity_id);
      if (payload.bid_id) q = q.eq("id", payload.bid_id);
      const { error } = await q;
      if (error) throw error;
    }
    const nextOpp = oppStatus(payload.action);
    if (nextOpp) {
      const { error } = await admin
        .from("opportunities")
        .update({ status: nextOpp })
        .eq("id", payload.opportunity_id);
      if (error) throw error;
    }
  } catch (err) {
    console.error("[bids] decision failed", err);
    return NextResponse.json(
      { persisted: false, error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }

  return NextResponse.json({ persisted: true });
}
