import clsx from "clsx";

import { PageHeader } from "@/components/PageHeader";
import { getMailboxes, type MailboxRow } from "@/lib/queries";

export const dynamic = "force-dynamic";

export default async function MailboxesPage() {
  const boxes = await getMailboxes();

  const total = boxes.length;
  const active = boxes.filter((b) => b.status === "active").length;
  const warming = boxes.filter((b) => b.status === "warming").length;
  const offline = boxes.filter((b) => b.status === "paused" || b.status === "disabled").length;
  const sentToday = boxes.reduce((n, b) => n + b.sent_today, 0);
  const bounces = boxes.reduce((n, b) => n + (b.bounce_count ?? 0), 0);
  const liveCapacity = boxes
    .filter((b) => b.status === "active" || b.status === "warming")
    .reduce((n, b) => n + (b.daily_cap ?? 0), 0);

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <PageHeader
        title="Mailboxes"
        description="Maildoso sending fleet — status, daily volume, and health. Sends rotate evenly across boxes, warmup-ramped. Credentials stay backend-only."
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <Kpi label="Boxes" value={String(total)} />
        <Kpi label="Active" value={String(active)} tone="text-emerald-400" />
        <Kpi label="Warming" value={String(warming)} tone="text-amber-400" />
        <Kpi label="Sent · 24h" value={`${sentToday} / ${liveCapacity}`} />
        <Kpi
          label="Bounces"
          value={String(bounces)}
          tone={bounces > 0 ? "text-red-400" : "text-neutral-100"}
        />
      </div>

      {offline > 0 && (
        <p className="mt-4 text-xs text-neutral-500">
          {offline} box{offline === 1 ? "" : "es"} paused/disabled (not sending).
        </p>
      )}

      {total === 0 ? (
        <p className="mt-12 text-center text-sm italic text-neutral-600">
          No mailboxes loaded. Import them with{" "}
          <code className="rounded bg-neutral-900 px-1.5 py-0.5">scripts.import_mailboxes</code>.
        </p>
      ) : (
        <div className="mt-8 overflow-x-auto rounded-lg border border-neutral-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-left text-[10px] uppercase tracking-wide text-neutral-500">
                <Th>Mailbox</Th>
                <Th>Status</Th>
                <Th className="text-right">Sent · 24h</Th>
                <Th className="text-right">Cap</Th>
                <Th className="text-right">Warmup</Th>
                <Th className="text-right">Bounces</Th>
                <Th className="text-right">Last send</Th>
                <Th>Last error</Th>
              </tr>
            </thead>
            <tbody>
              {boxes.map((b) => (
                <Row key={b.id} b={b} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Row({ b }: { b: MailboxRow }) {
  const atCap = b.sent_today >= b.daily_cap && b.daily_cap > 0;
  return (
    <tr className="border-b border-neutral-900 last:border-0 hover:bg-neutral-950">
      <td className="px-3 py-2.5">
        <div className="font-mono text-[13px] text-neutral-200">{b.email}</div>
        <div className="text-[11px] text-neutral-600">{b.domain ?? ""}</div>
      </td>
      <td className="px-3 py-2.5">
        <StatusBadge status={b.status} />
      </td>
      <td className={clsx("px-3 py-2.5 text-right font-mono", atCap ? "text-amber-400" : "text-neutral-300")}>
        {b.sent_today}
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-neutral-500">{b.daily_cap}</td>
      <td className="px-3 py-2.5 text-right font-mono text-neutral-500">
        {b.status === "warming" ? `wk ${b.warmup_stage ?? 0}` : "—"}
      </td>
      <td
        className={clsx(
          "px-3 py-2.5 text-right font-mono",
          (b.bounce_count ?? 0) > 0 ? "text-red-400" : "text-neutral-600",
        )}
      >
        {b.bounce_count ?? 0}
      </td>
      <td className="px-3 py-2.5 text-right font-mono text-[11px] text-neutral-500">
        {relTime(b.last_send_at)}
      </td>
      <td className="max-w-[220px] truncate px-3 py-2.5 text-[11px] text-red-400/80" title={b.last_error ?? ""}>
        {b.last_error ?? ""}
      </td>
    </tr>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "active"
      ? "border-emerald-800 bg-emerald-950 text-emerald-300"
      : status === "warming"
        ? "border-amber-800 bg-amber-950 text-amber-300"
        : "border-neutral-700 bg-neutral-900 text-neutral-400";
  return (
    <span className={clsx("rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase", tone)}>
      {status}
    </span>
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

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return <th className={clsx("px-3 py-2 font-medium", className)}>{children}</th>;
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
