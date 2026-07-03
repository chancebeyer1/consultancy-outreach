// Server-side auth helpers: who is signed in, and are they an admin?
//
// getCurrentProfile() is the one place pages and API routes resolve the caller.
// It's React-cached, so multiple readers in one render share the fetch. In
// mock/file mode there is no auth — it returns null and callers treat that as
// the local operator (full access), matching the middleware no-op.

import "server-only";

import { redirect } from "next/navigation";
import { NextResponse } from "next/server";
import { cache } from "react";

import { dataSource, serverAdminClient, serverClient } from "./supabase";

export interface CurrentProfile {
  id: string;
  email: string | null;
  name: string | null;
  isAdmin: boolean;
}

// Scope threaded through lib/queries readers. Admins — and mock/file mode's
// null — see everything; a non-admin scope filters every reader to rows they
// own (directly via user_id, or through the lead → user relationship).
export type Scope = Pick<CurrentProfile, "id" | "isAdmin"> | null | undefined;

export const getCurrentProfile = cache(async (): Promise<CurrentProfile | null> => {
  if (dataSource !== "supabase") return null;
  let userId: string | null = null;
  let userEmail: string | null = null;
  try {
    const supabase = await serverClient();
    const { data } = await supabase.auth.getUser();
    if (!data.user) return null;
    userId = data.user.id;
    userEmail = data.user.email ?? null;
    const { data: me } = await serverAdminClient()
      .from("profiles")
      .select("id, email, name, is_admin")
      .eq("id", data.user.id)
      .single();
    if (me) {
      return {
        id: me.id as string,
        email: (me.email as string | null) ?? userEmail,
        name: (me.name as string | null) ?? null,
        isAdmin: Boolean(me.is_admin),
      };
    }
  } catch {
    // fall through to the fail-closed default below
  }
  // Signed in but no profiles row (or the lookup failed): FAIL CLOSED. The
  // session uid IS the profile id by design, so scoping by it filters readers
  // to rows they own — which for a missing profile is nothing, never everything.
  if (userId) return { id: userId, email: userEmail, name: null, isAdmin: false };
  return null;
});

// Page gate for admin-only surfaces (campaigns, analytics, mailboxes, …).
// Non-admins land back on '/' (which resolves to their default page). Mock/file
// mode has no auth, so the local operator passes straight through.
export async function requireAdmin(): Promise<CurrentProfile | null> {
  if (dataSource !== "supabase") return null;
  const profile = await getCurrentProfile();
  if (!profile?.isAdmin) redirect("/");
  return profile;
}

// API-route gates. Return { profile } on success or { error } (a ready
// NextResponse) — routes bail with `if (gate.error) return gate.error`.
export async function requireApiUser(): Promise<
  { profile: CurrentProfile; error?: undefined } | { profile?: undefined; error: NextResponse }
> {
  const profile = await getCurrentProfile();
  if (!profile) {
    return { error: NextResponse.json({ error: "not signed in" }, { status: 401 }) };
  }
  return { profile };
}

export async function requireApiAdmin(): Promise<
  { profile: CurrentProfile; error?: undefined } | { profile?: undefined; error: NextResponse }
> {
  const gate = await requireApiUser();
  if (gate.error) return gate;
  if (!gate.profile.isAdmin) {
    return { error: NextResponse.json({ error: "admin only" }, { status: 403 }) };
  }
  return gate;
}

// True when a lead belongs to the user (leads.user_id) — the ownership check
// API routes run before letting a non-admin touch lead-scoped rows (drafts,
// replies, inbox messages, scheduled sends).
export async function leadOwnedBy(
  leadId: string | null | undefined,
  userId: string,
): Promise<boolean> {
  if (!leadId) return false;
  const { data } = await serverAdminClient()
    .from("leads")
    .select("user_id")
    .eq("id", leadId)
    .maybeSingle();
  return (data as { user_id?: string | null } | null)?.user_id === userId;
}
