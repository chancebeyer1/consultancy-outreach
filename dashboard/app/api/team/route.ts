import { NextResponse } from "next/server";

import { serverAdminClient, serverClient } from "@/lib/supabase";

// User creation needs the service-role admin API → Node runtime.
export const runtime = "nodejs";

// Only a signed-in admin may create accounts or edit account-ids — this route holds the
// service-role key, so it must gate every call on the caller's own profile.is_admin.
async function requireAdmin() {
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: NextResponse.json({ error: "not signed in" }, { status: 401 }) };
  const admin = serverAdminClient();
  const { data: profile } = await admin
    .from("profiles")
    .select("is_admin")
    .eq("id", user.id)
    .single();
  if (!profile?.is_admin) {
    return { error: NextResponse.json({ error: "admin only" }, { status: 403 }) };
  }
  return { admin };
}

// POST — create a teammate: a Supabase Auth user + their profile row (one transaction-ish flow).
export async function POST(req: Request) {
  const gate = await requireAdmin();
  if (gate.error) return gate.error;
  const admin = gate.admin!;

  let body: { email?: string; password?: string; name?: string; isAdmin?: boolean };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  const email = body.email?.trim().toLowerCase();
  const password = body.password ?? "";
  const name = body.name?.trim() || null;
  if (!email || password.length < 8) {
    return NextResponse.json(
      { error: "email and a password of 8+ characters are required" },
      { status: 400 },
    );
  }

  // 1. Create the auth user (email pre-confirmed — invite-only, no verification email).
  const { data: created, error: createErr } = await admin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
    user_metadata: { name },
  });
  if (createErr || !created?.user) {
    return NextResponse.json(
      { error: `could not create user: ${createErr?.message ?? "unknown"}` },
      { status: 400 },
    );
  }

  // 2. Mirror into profiles (id = auth user id). On any failure, roll back the auth user so
  //    we never leave an orphaned login with no profile.
  const { error: profErr } = await admin.from("profiles").insert({
    id: created.user.id,
    email,
    name,
    is_admin: Boolean(body.isAdmin),
  });
  if (profErr) {
    await admin.auth.admin.deleteUser(created.user.id).catch(() => {});
    return NextResponse.json({ error: `profile insert failed: ${profErr.message}` }, { status: 400 });
  }

  return NextResponse.json({ ok: true, id: created.user.id, email });
}

// PATCH — update a profile: connect their account-ids (paste from Unipile) or rename.
export async function PATCH(req: Request) {
  const gate = await requireAdmin();
  if (gate.error) return gate.error;
  const admin = gate.admin!;

  let body: {
    id?: string;
    name?: string;
    unipile_account_id?: string | null;
    unipile_email_account_id?: string | null;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }
  if (!body.id) return NextResponse.json({ error: "missing id" }, { status: 400 });

  const patch: Record<string, string | null> = {};
  if (body.name !== undefined) patch.name = body.name?.trim() || null;
  // Empty string clears the field; a value sets it. Trim to avoid stray whitespace in ids.
  if (body.unipile_account_id !== undefined)
    patch.unipile_account_id = body.unipile_account_id?.trim() || null;
  if (body.unipile_email_account_id !== undefined)
    patch.unipile_email_account_id = body.unipile_email_account_id?.trim() || null;
  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ error: "nothing to update" }, { status: 400 });
  }

  const { error } = await admin.from("profiles").update(patch).eq("id", body.id);
  if (error) return NextResponse.json({ error: error.message }, { status: 400 });
  return NextResponse.json({ ok: true });
}
