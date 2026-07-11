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

// Queue hygiene: pass the low-fit rows the client is DISPLAYING, by explicit id. The client
// sends the ids so the confirm dialog's count is exactly what gets passed — a filter-only
// update would also hit rows beyond the page's 400-row read that the user never saw. The
// status/fit guards are kept server-side so a stale client can't pass a row that has since
// been drafted or decided.
interface BulkPassPayload {
  action: "bulk_pass";
  max_fit: number;
  opportunity_ids: string[];
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
  return (
    o.action === "bulk_pass" &&
    typeof o.max_fit === "number" &&
    o.max_fit >= 0 &&
    o.max_fit <= 100 &&
    Array.isArray(o.opportunity_ids) &&
    o.opportunity_ids.length > 0 &&
    o.opportunity_ids.length <= 1000 &&
    o.opportunity_ids.every((x) => typeof x === "string")
  );
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
    let passed = 0;
    for (let i = 0; i < payload.opportunity_ids.length; i += 200) {
      const chunk = payload.opportunity_ids.slice(i, i + 200);
      let q = admin
        .from("opportunities")
        .update({ status: "passed" }, { count: "exact" })
        .in("id", chunk)
        .in("status", ["new", "scored"])
        .lt("fit_score", payload.max_fit);
      if (!gate.profile.isAdmin) q = q.eq("user_id", gate.profile.id);
      const { error, count } = await q;
      if (error) {
        console.error("[bids] bulk pass failed", error);
        return NextResponse.json(
          { persisted: passed > 0, passed, error: error.message },
          { status: 500 },
        );
      }
      passed += count ?? 0;
    }
    return NextResponse.json({ persisted: true, passed });
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
