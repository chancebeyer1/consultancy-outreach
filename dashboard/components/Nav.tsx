import Link from "next/link";
import { cookies } from "next/headers";

import { CampaignSelector } from "./CampaignSelector";
import { CAMPAIGN_COOKIE } from "../lib/campaign-filter";
import { getCampaigns } from "../lib/queries";
import { dataSource } from "../lib/supabase";

const links = [
  { href: "/drafts", label: "Drafts" },
  { href: "/inbox", label: "Inbox" },
  { href: "/replies", label: "Replies" },
  { href: "/leads", label: "Leads" },
  { href: "/sequences", label: "Sequences" },
  { href: "/mailboxes", label: "Mailboxes" },
  { href: "/campaigns", label: "Campaigns" },
  { href: "/analytics", label: "Analytics" },
];

const sourceColor = {
  mock: "text-amber-400",
  file: "text-sky-400",
  supabase: "text-emerald-400",
} as const;

export async function Nav() {
  const [campaigns, cookieStore] = await Promise.all([getCampaigns(), cookies()]);
  const selected = cookieStore.get(CAMPAIGN_COOKIE)?.value ?? "all";

  return (
    <header className="border-b border-neutral-800">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-5 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="font-mono text-sm font-bold tracking-wide">
          OUTREACH
        </Link>
        {/* Mobile: full-width, horizontally scrollable row under the logo. Desktop: inline. */}
        <nav className="order-3 -mx-4 flex w-full gap-4 overflow-x-auto px-4 text-sm text-neutral-400 [-ms-overflow-style:none] [scrollbar-width:none] sm:order-none sm:mx-0 sm:w-auto sm:flex-1 sm:overflow-visible sm:px-0">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="whitespace-nowrap hover:text-white">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <CampaignSelector campaigns={campaigns} selected={selected} />
          <div
            className={`hidden font-mono text-[10px] uppercase tracking-wide sm:block ${sourceColor[dataSource]}`}
          >
            source · {dataSource}
          </div>
        </div>
      </div>
    </header>
  );
}
