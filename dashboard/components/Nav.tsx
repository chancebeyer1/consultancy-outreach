import Link from "next/link";
import { cookies } from "next/headers";

import { AuthStatus } from "./AuthStatus";
import { CampaignSelector } from "./CampaignSelector";
import { NavLinks } from "./NavLinks";
import { getCurrentProfile } from "../lib/auth";
import { CAMPAIGN_COOKIE } from "../lib/campaign-filter";
import { getCampaigns } from "../lib/queries";
import { dataSource } from "../lib/supabase";

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

// Simplified surface for non-admin teammates: just their leads and their
// replies (/drafts and /inbox redirect into these two).
const memberLinks = [
  { href: "/leads", label: "Leads" },
  { href: "/replies", label: "Replies" },
];

const sourceColor = {
  mock: "text-amber-400",
  file: "text-sky-400",
  supabase: "text-emerald-400",
} as const;

export async function Nav() {
  const [profile, cookieStore] = await Promise.all([getCurrentProfile(), cookies()]);
  const selected = cookieStore.get(CAMPAIGN_COOKIE)?.value ?? "all";

  // Campaigns are scoped to the signed-in user (non-admins only see their own).
  const campaigns = await getCampaigns(profile);

  const userEmail = profile?.email ?? null;
  // Mock/file mode has no auth — treat the local operator as admin (full nav).
  const isAdmin = dataSource !== "supabase" || Boolean(profile?.isAdmin);

  // Admins get the full nav + the Team (invite/onboarding) link; members get
  // the simplified two-tab surface.
  const navLinks = isAdmin ? [...links, { href: "/team", label: "Team" }] : memberLinks;

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
