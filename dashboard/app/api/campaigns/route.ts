// Campaign CRUD for the /campaigns management surface.
//
// - mock / file mode: writes are disabled (no DB). GET still returns the
//   in-memory / empty list so the page renders.
// - supabase mode:    create + update via the service-role client, mirroring
//                     app/api/decisions/route.ts. Enforces a single default
//                     campaign (clearing the flag on others) like
//                     backend/scripts/sync_campaigns.py.
//
// The backend campaigns_loader reads these same rows at runtime, so editing a
// campaign here re-targets the pipeline on its next run.

import { NextResponse } from "next/server";

import { getCurrentProfile, requireApiUser, type CurrentProfile } from "@/lib/auth";
import { getCampaigns } from "@/lib/queries";
import { dataSource, serverAdminClient } from "@/lib/supabase";

// Text fields that fall back to a global/.env default when blank — store NULL
// rather than "" so the backend loader's coalesce works.
const NULLABLE_TEXT = [
  "icp_md",
  "offer_md",
  "style_md",
  "voice_md",
  "landing_url",
  "calcom_url",
  "slug",
] as const;

interface CampaignPayload {
  id?: string | null;
  name: string;
  slug?: string | null;
  icp_md?: string | null;
  offer_md?: string | null;
  style_md?: string | null;
  voice_md?: string | null;
  landing_url?: string | null;
  calcom_url?: string | null;
  is_default?: boolean;
  auto_send?: boolean;
  inmail_min_fit?: number | null;
  status?: "active" | "paused" | "archived";
}

function isValid(p: unknown): p is CampaignPayload {
  if (!p || typeof p !== "object") return false;
  const o = p as Record<string, unknown>;
  return typeof o.name === "string" && o.name.trim().length > 0;
}

function normalize(p: CampaignPayload): Record<string, unknown> {
  const row: Record<string, unknown> = {
    name: p.name.trim(),
    is_default: Boolean(p.is_default),
    auto_send: Boolean(p.auto_send),
    inmail_min_fit:
      typeof p.inmail_min_fit === "number" && Number.isFinite(p.inmail_min_fit)
        ? p.inmail_min_fit
        : null,
    status: p.status ?? "active",
  };
  for (const key of NULLABLE_TEXT) {
    const value = p[key];
    row[key] = typeof value === "string" && value.trim().length > 0 ? value : null;
  }
  return row;
}

export async function GET() {
  try {
    // Scoped to the caller: non-admins only see their own campaigns.
    let profile: CurrentProfile | null = null;
    if (dataSource === "supabase") {
      profile = await getCurrentProfile();
      if (!profile) return NextResponse.json({ error: "not signed in" }, { status: 401 });
    }
    const campaigns = await getCampaigns(profile);
    return NextResponse.json({ campaigns, source: dataSource });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}

export async function POST(request: Request) {
  if (dataSource !== "supabase") {
    return NextResponse.json(
      { persisted: false, reason: `writes disabled in "${dataSource}" mode` },
      { status: 400 },
    );
  }

  const gate = await requireApiUser();
  if (gate.error) return gate.error;
  const profile = gate.profile;

  const payload = (await request.json()) as unknown;
  if (!isValid(payload)) {
    return NextResponse.json({ error: "name is required" }, { status: 400 });
  }

  const supabase = serverAdminClient();
  const row = normalize(payload);

  try {
    let id = payload.id ?? null;

    if (id) {
      // Non-admins may only edit campaigns they own.
      if (!profile.isAdmin) {
        const { data: existing } = await supabase
          .from("campaigns")
          .select("user_id")
          .eq("id", id)
          .maybeSingle();
        if ((existing as { user_id?: string | null } | null)?.user_id !== profile.id) {
          return NextResponse.json({ error: "not your campaign" }, { status: 403 });
        }
      }
      const { error } = await supabase.from("campaigns").update(row).eq("id", id);
      if (error) throw error;
    } else {
      // New campaigns created by a non-admin belong to them.
      if (!profile.isAdmin) row.user_id = profile.id;
      const { data, error } = await supabase
        .from("campaigns")
        .insert(row)
        .select("id")
        .single();
      if (error) throw error;
      id = (data as { id: string }).id;
    }

    // Enforce single default: if this campaign is the default, clear the flag
    // on every other row (two statements avoid a transient double-true that
    // would trip the campaigns_one_default_idx unique index). Non-admins only
    // clear the flag within their own campaigns.
    if (row.is_default && id) {
      let clearQ = supabase
        .from("campaigns")
        .update({ is_default: false })
        .neq("id", id)
        .eq("is_default", true);
      if (!profile.isAdmin) clearQ = clearQ.eq("user_id", profile.id);
      const { error } = await clearQ;
      if (error) throw error;
    }

    return NextResponse.json({ persisted: true, id });
  } catch (err) {
    console.error("[campaigns] write failed", err);
    return NextResponse.json(
      { persisted: false, error: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }
}
