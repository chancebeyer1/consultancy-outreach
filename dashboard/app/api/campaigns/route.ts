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
    const campaigns = await getCampaigns();
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

  const payload = (await request.json()) as unknown;
  if (!isValid(payload)) {
    return NextResponse.json({ error: "name is required" }, { status: 400 });
  }

  const supabase = serverAdminClient();
  const row = normalize(payload);

  try {
    let id = payload.id ?? null;

    if (id) {
      const { error } = await supabase.from("campaigns").update(row).eq("id", id);
      if (error) throw error;
    } else {
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
    // would trip the campaigns_one_default_idx unique index).
    if (row.is_default && id) {
      const { error } = await supabase
        .from("campaigns")
        .update({ is_default: false })
        .neq("id", id)
        .eq("is_default", true);
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
