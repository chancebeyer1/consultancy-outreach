import clsx from "clsx";

import { getSelectedCampaignId } from "@/lib/campaign-filter";
import { getCampaigns, getInboxMessages, type InboxMessage } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function InboxPage() {
  const campaignId = await getSelectedCampaignId();
  const [messages, campaigns] = await Promise.all([getInboxMessages(campaignId), getCampaigns()]);
  const campaignName = new Map(campaigns.map((c) => [c.id, c.name]));

  const replies = messages.filter((m) => !m.is_auto && m.lead_id).length;
  const autos = messages.filter((m) => m.is_auto).length;
  const last24 = messages.filter(
    (m) => m.received_at && Date.now() - new Date(m.received_at).getTime() < 86_400_000,
  ).length;

  return (
    <div className="mx-auto max-w-5xl px-6 py-6">
      <header className="mb-6 border-b border-neutral-800 pb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
        <p className="mt-1 text-sm text-neutral-500">
          One unified inbox across all sending boxes — real inbound only (warmup stays out).
          Reliable even when alert emails get spam-foldered. Matched replies are tagged to their lead.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi label="Messages" value={String(messages.length)} />
        <Kpi label="Replies" value={String(replies)} tone="text-emerald-400" />
        <Kpi label="Auto / OOO" value={String(autos)} tone="text-neutral-400" />
        <Kpi label="Last 24h" value={String(last24)} />
      </div>

      {messages.length === 0 ? (
        <p className="mt-12 text-center text-sm italic text-neutral-600">
          No inbound yet. Replies from your prospects will land here as they arrive.
        </p>
      ) : (
        <ul className="mt-6 divide-y divide-neutral-900 rounded-lg border border-neutral-800">
          {messages.map((m) => (
            <Row key={m.id} m={m} campaign={m.campaign_id ? campaignName.get(m.campaign_id) : null} />
          ))}
        </ul>
      )}
    </div>
  );
}

function Row({ m, campaign }: { m: InboxMessage; campaign?: string | null }) {
  const matched = !m.is_auto && m.lead_id;
  return (
    <li className="flex gap-4 px-4 py-3 hover:bg-neutral-950">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-neutral-100">
            {m.from_name || m.from_email || "(unknown sender)"}
          </span>
          {matched && (
            <span className="rounded border border-emerald-800 bg-emerald-950 px-1.5 py-0.5 font-mono text-[10px] uppercase text-emerald-300">
              reply
            </span>
          )}
          {m.is_auto && (
            <span className="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 font-mono text-[10px] uppercase text-neutral-500">
              auto
            </span>
          )}
          {campaign && <span className="truncate text-[11px] text-neutral-600">· {campaign}</span>}
        </div>
        <div className="mt-0.5 truncate text-sm text-neutral-300">{m.subject || "(no subject)"}</div>
        <div className="mt-0.5 truncate text-xs text-neutral-500">{(m.body || "").slice(0, 140)}</div>
        <div className="mt-1 font-mono text-[10px] text-neutral-600">
          {m.from_email} → {m.mailbox_email}
        </div>
      </div>
      <div className="shrink-0 text-right font-mono text-[11px] text-neutral-500">{relTime(m.received_at)}</div>
    </li>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={clsx("mt-1 font-mono text-2xl", tone ?? "text-neutral-100")}>{value}</div>
    </div>
  );
}

function relTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
