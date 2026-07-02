import clsx from "clsx";

import { PageHeader } from "@/components/PageHeader";
import { getActivity, getCampaigns, type ActivityRow } from "@/lib/queries";

export const dynamic = "force-dynamic";

const LABELS: Record<string, string> = {
  cron_send: "First-touch send run",
  cron_inbound_sweep: "Inbox + reply sweep",
  cron_replenish: "Lead sourcing run",
  cron_sequences: "Sequence advance",
  cron_detect_connections: "Connection-accept check",
  reply_received: "Reply received",
  reply_sent: "Reply sent",
  draft_decided: "Draft decided",
};

export default async function ActivityPage() {
  const [rows, campaigns] = await Promise.all([getActivity(300), getCampaigns()]);
  const campaignName = new Map(campaigns.map((c) => [c.id, c.name]));

  return (
    <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <PageHeader
        title="Activity"
        description="Everything the system does — every cron run, send, reply, and dashboard action."
      />

      {rows.length === 0 ? (
        <p className="mt-12 text-center text-sm italic text-neutral-600">No activity yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((r) => (
            <Row key={r.id} r={r} campaign={r.campaign_id ? campaignName.get(r.campaign_id) ?? null : null} />
          ))}
        </ul>
      )}
    </div>
  );
}

function Row({ r, campaign }: { r: ActivityRow; campaign: string | null }) {
  const label = LABELS[r.action] ?? r.action;
  const detail = r.summary || summarizeMeta(r.action, r.meta);
  return (
    <li className="flex items-baseline gap-3 rounded-md border border-neutral-900 bg-neutral-950 px-3 py-2 text-sm">
      <span className="w-16 shrink-0 font-mono text-[10px] text-neutral-600">{relTime(r.created_at)}</span>
      <span
        className={clsx(
          "shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase",
          r.source === "dashboard"
            ? "border border-sky-800 bg-sky-950 text-sky-300"
            : "border border-neutral-700 bg-neutral-900 text-neutral-400",
        )}
      >
        {r.source === "dashboard" ? "you" : "auto"}
      </span>
      <div className="min-w-0 flex-1">
        <span className="text-neutral-200">{label}</span>
        {detail && <span className="text-neutral-500"> — {detail}</span>}
        {campaign && <span className="text-[11px] text-neutral-600"> · {campaign}</span>}
      </div>
    </li>
  );
}

// Build a short human line from a cron run's result counts.
function summarizeMeta(action: string, meta: Record<string, unknown> | null): string {
  if (!meta) return "";
  const parts: string[] = [];
  const n = (obj: unknown, key: string): number | null => {
    if (obj && typeof obj === "object" && key in (obj as Record<string, unknown>)) {
      const v = (obj as Record<string, unknown>)[key];
      return typeof v === "number" ? v : null;
    }
    return null;
  };
  if (action === "cron_send") {
    const li = n(meta.linkedin, "pushed");
    const em = n(meta.email, "pushed");
    if (li != null) parts.push(`${li} LinkedIn`);
    if (em != null) parts.push(`${em} email`);
    return parts.length ? `sent ${parts.join(", ")}` : "nothing due";
  }
  if (action === "cron_replenish") {
    const apollo = meta.apollo_email as { campaigns?: unknown[] } | undefined;
    const sourced = Array.isArray(apollo?.campaigns)
      ? (apollo!.campaigns as Array<{ sourced?: number }>).reduce((s, c) => s + (c.sourced ?? 0), 0)
      : null;
    return sourced != null ? `${sourced} email leads sourced` : "checked queues";
  }
  if (action === "cron_inbound_sweep") {
    const em = meta.email as { replies_stored?: number; warmup_filtered?: number } | undefined;
    if (em?.replies_stored != null) return `${em.replies_stored} replies, ${em.warmup_filtered ?? 0} warmup filtered`;
    return "swept inboxes";
  }
  if (action === "cron_sequences") return `${n(meta, "pushed") ?? 0} steps advanced`;
  if (action === "cron_detect_connections") return `${n(meta, "accepted") ?? 0} new connections`;
  return "";
}

function relTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}
