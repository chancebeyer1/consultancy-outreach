"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import type { Campaign } from "../lib/types";

const COOKIE = "campaign_id";
const ALL = "all";

interface Props {
  campaigns: Campaign[];
  selected: string; // campaign id, or "all"
}

// Global campaign scope. Writes a plain cookie the server reads on the next
// render (see lib/campaign-filter.ts), then refreshes so every page re-fetches
// scoped to the chosen campaign. Hidden when there are no campaigns (file mode).
export function CampaignSelector({ campaigns, selected }: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  if (campaigns.length === 0) return null;

  function onChange(value: string) {
    // 1 year, site-wide. Non-httpOnly so it's set straight from the client.
    document.cookie = `${COOKIE}=${encodeURIComponent(value)}; path=/; max-age=31536000; samesite=lax`;
    startTransition(() => router.refresh());
  }

  return (
    <label className="flex items-center gap-2 text-xs text-neutral-400">
      <span className="hidden uppercase tracking-wide text-neutral-600 sm:inline">campaign</span>
      <select
        aria-label="Filter by campaign"
        value={selected}
        disabled={pending}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-neutral-800 bg-neutral-950 px-2 py-1 font-mono text-xs text-neutral-200 outline-none focus:border-neutral-600 disabled:opacity-50"
      >
        <option value={ALL}>all campaigns</option>
        {campaigns.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
            {c.is_default ? " ★" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
