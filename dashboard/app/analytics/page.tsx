import clsx from "clsx";

import { getAnalytics, type AnalyticsRow } from "@/lib/analytics";
import { dataSource } from "@/lib/supabase";

export default async function AnalyticsPage() {
  const a = await getAnalytics();

  if (a.empty && dataSource === "file") {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center text-neutral-500">
        <h1 className="text-2xl font-semibold text-neutral-200">Analytics</h1>
        <p className="mt-3">
          Analytics need joined send + reply state, which lives in Postgres. Set{" "}
          <code className="rounded bg-neutral-900 px-1.5 py-0.5">NEXT_PUBLIC_DATA_SOURCE=supabase</code>{" "}
          to enable this view.
        </p>
      </div>
    );
  }

  if (a.empty) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center text-neutral-500">
        <h1 className="text-2xl font-semibold text-neutral-200">Analytics</h1>
        <p className="mt-3">No sends recorded yet. Run a pipeline and push a few drafts to populate this view.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-6">
      <header className="mb-8 border-b border-neutral-800 pb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Analytics</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Reply rate by segment, trigger, and hook type. Reply = any inbound; Interested = LLM-classified positive intent.
        </p>
      </header>

      <KpiStrip totals={a.totals} />

      <div className="mt-10 grid gap-10 lg:grid-cols-2">
        <Breakdown title="By segment" subtitle="Which ICP is converting" rows={a.bySegment} />
        <Breakdown title="By trigger" subtitle="Cold list vs warm signal" rows={a.byTrigger} />
        <Breakdown
          title="By hook type"
          subtitle="Which personalization angle works"
          rows={a.byHookType}
        />
      </div>
    </div>
  );
}

function KpiStrip({ totals }: { totals: AnalyticsRow }) {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <Kpi label="Sent" value={fmt(totals.sent)} />
      <Kpi label="Replied" value={fmt(totals.replied)} />
      <Kpi label="Reply rate" value={pct(totals.replyRate)} tone={rateTone(totals.replyRate, "reply")} />
      <Kpi
        label="Interest rate"
        value={pct(totals.interestRate)}
        tone={rateTone(totals.interestRate, "interest")}
      />
    </div>
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

function Breakdown({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle: string;
  rows: AnalyticsRow[];
}) {
  if (rows.length === 0) {
    return (
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">{title}</h2>
        <p className="mt-1 text-xs text-neutral-500">{subtitle}</p>
        <p className="mt-6 text-sm italic text-neutral-600">no data</p>
      </section>
    );
  }

  const maxSent = Math.max(...rows.map((r) => r.sent), 1);
  return (
    <section>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-400">{title}</h2>
      <p className="mt-1 text-xs text-neutral-500">{subtitle}</p>
      <ul className="mt-4 space-y-3">
        {rows.map((r) => (
          <li key={r.bucket} className="rounded-md border border-neutral-800 bg-neutral-950 p-3">
            <div className="flex items-baseline justify-between">
              <span className="font-mono text-sm">{r.bucket}</span>
              <span className="font-mono text-xs text-neutral-500">
                {fmt(r.sent)} sent · {fmt(r.replied)} replied · {fmt(r.interested)} interested
              </span>
            </div>
            <div className="mt-2 flex items-center gap-3">
              <div className="h-1.5 flex-1 overflow-hidden rounded bg-neutral-900">
                <div
                  className="h-full bg-sky-700"
                  style={{ width: `${(r.sent / maxSent) * 100}%` }}
                />
              </div>
              <span
                className={clsx(
                  "min-w-12 text-right font-mono text-sm",
                  rateTone(r.replyRate, "reply"),
                )}
              >
                {pct(r.replyRate)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function fmt(n: number): string {
  return n.toLocaleString();
}

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function rateTone(rate: number, kind: "reply" | "interest"): string {
  // Loose benchmarks based on the architecture plan:
  //   reply: >12% strong, 5–12% normal, <5% weak
  //   interest: >5% strong, 2–5% normal
  const goodThreshold = kind === "reply" ? 0.12 : 0.05;
  const okThreshold = kind === "reply" ? 0.05 : 0.02;
  if (rate >= goodThreshold) return "text-emerald-400";
  if (rate >= okThreshold) return "text-amber-400";
  if (rate > 0) return "text-red-400";
  return "text-neutral-500";
}
