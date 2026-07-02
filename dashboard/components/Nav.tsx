import Link from "next/link";
import { cookies } from "next/headers";

import { AuthStatus } from "./AuthStatus";
import { CampaignSelector } from "./CampaignSelector";
import { NavLinks } from "./NavLinks";
import { CAMPAIGN_COOKIE } from "../lib/campaign-filter";
import { getCampaigns } from "../lib/queries";
import { dataSource, serverAdminClient, serverClient } from "../lib/supabase";

const links = [
  { href: "/content", label: "Content" },
  { href: "/comments", label: "Comments" },
  { href: "/newsletter", label: "Newsletter" },
  { href: "/replies", label: "Replies" },
  { href: "/sends", label: "Sends" },
  { href: "/pipeline", label: "Pipeline" },
  { href: "/leads", label: "Leads" },
  { href: "/sequences", label: "Sequences" },
  { href: "/mailboxes", label: "Mailboxes" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/analytics", label: "Analytics" },
  { href: "/activity", label: "Activity" },
];

const sourceColor = {
  mock: "text-amber-400",
  file: "text-sky-400",
  supabase: "text-emerald-400",
} as const;

export async function Nav() {
  const [campaigns, cookieStore] = await Promise.all([getCampaigns(), cookies()]);
  const selected = cookieStore.get(CAMPAIGN_COOKIE)?.value ?? "all";

  let userEmail: string | null = null;
  let isAdmin = false;
  if (dataSource === "supabase") {
    try {
      const supabase = await serverClient();
      const { data } = await supabase.auth.getUser();
      userEmail = data.user?.email ?? null;
      if (data.user) {
        const { data: me } = await serverAdminClient()
          .from("profiles")
          .select("is_admin")
          .eq("id", data.user.id)
          .single();
        isAdmin = Boolean(me?.is_admin);
      }
    } catch {
      userEmail = null;
    }
  }

  // Admins get the Team (invite/onboarding) link; members don't.
  const navLinks = isAdmin ? [...links, { href: "/team", label: "Team" }] : links;

  return (
    <header className="sticky top-0 z-30 border-b border-neutral-800 bg-[#0a0a0a]/80 backdrop-blur-md">
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        {/* Row 1 — brand + utilities. Kept light so the tab bar below has room to breathe. */}
        <div className="flex h-14 items-center justify-between gap-4">
          <Link
            href="/"
            className="flex shrink-0 items-center gap-2 font-mono text-sm font-bold tracking-wide text-white"
          >
            <span className="h-2 w-2 rounded-full bg-sky-400" />
            OUTREACH
          </Link>
          <div className="flex min-w-0 items-center gap-3">
            <CampaignSelector campaigns={campaigns} selected={selected} />
            <span
              className={`hidden font-mono text-[10px] uppercase tracking-wide sm:inline ${sourceColor[dataSource]}`}
            >
              {dataSource}
            </span>
            {dataSource === "supabase" && <AuthStatus email={userEmail} />}
          </div>
        </div>
        {/* Row 2 — primary navigation as a full-width tab bar (scrolls horizontally on mobile). */}
        <nav className="-mx-4 -mb-px flex gap-0.5 overflow-x-auto px-4 [-ms-overflow-style:none] [scrollbar-width:none] sm:mx-0 sm:px-0">
          <NavLinks links={navLinks} />
        </nav>
      </div>
    </header>
  );
}
