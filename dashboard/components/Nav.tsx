import Link from "next/link";
import { cookies } from "next/headers";

import { CampaignSelector } from "./CampaignSelector";
import { CAMPAIGN_COOKIE } from "../lib/campaign-filter";
import { getCampaigns } from "../lib/queries";
import { dataSource } from "../lib/supabase";

const links = [
  { href: "/drafts", label: "Drafts" },
  { href: "/replies", label: "Replies" },
  { href: "/leads", label: "Leads" },
  { href: "/sequences", label: "Sequences" },
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
      <div className="mx-auto flex max-w-7xl items-center gap-8 px-6 py-3">
        <Link href="/" className="font-mono text-sm font-bold tracking-wide">
          OUTREACH
        </Link>
        <nav className="flex gap-5 text-sm text-neutral-400">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-white">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-5">
          <CampaignSelector campaigns={campaigns} selected={selected} />
          <div className={`font-mono text-[10px] uppercase tracking-wide ${sourceColor[dataSource]}`}>
            source · {dataSource}
          </div>
        </div>
      </div>
    </header>
  );
}
