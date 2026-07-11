import { PageHeader } from "@/components/PageHeader";
import { dataSource, serverAdminClient, serverClient } from "@/lib/supabase";

import { TeamClient, type TeamMember } from "./TeamClient";

export const dynamic = "force-dynamic";

export default async function TeamPage() {
  if (dataSource !== "supabase") {
    return (
      <Shell>
        <p className="text-sm italic text-neutral-600">
          Team management requires the Supabase data source.
        </p>
      </Shell>
    );
  }

  // Admin gate: only an admin profile may view/manage the team.
  const supabase = await serverClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const admin = serverAdminClient();

  let isAdmin = false;
  if (user) {
    const { data: me } = await admin
      .from("profiles")
      .select("is_admin")
      .eq("id", user.id)
      .single();
    isAdmin = Boolean(me?.is_admin);
  }

  if (!isAdmin) {
    return (
      <Shell>
        <p className="text-sm italic text-neutral-600">
          You don&apos;t have access to team management.
        </p>
      </Shell>
    );
  }

  const { data } = await admin
    .from("profiles")
    .select("id, email, name, unipile_account_id, unipile_email_account_id, is_admin, created_at")
    .order("created_at", { ascending: true });

  const members = (data ?? []) as TeamMember[];

  return (
    <Shell>
      <TeamClient members={members} />
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-4xl px-6 py-6">
      <PageHeader
        title="Team"
        description="Invite-only accounts. Create a login, then paste a teammate's Unipile account-id once they've connected LinkedIn — their leads then send from their own account."
      />
      {children}
    </div>
  );
}
