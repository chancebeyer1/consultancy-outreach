import clsx from "clsx";

import { PageHeader } from "@/components/PageHeader";
import { getAnalytics, type AnalyticsRow, type Experiment, type VariantStat } from "@/lib/analytics";
import { requireAdmin } from "@/lib/auth";
import { getSelectedCampaignId } from "@/lib/campaign-filter";
import { dataSource } from "@/lib/supabase";

export default async function AnalyticsPage() {
  await requireAdmin();
  const campaignId = await getSelectedCampaignId();
  const a = await getAnalytics(campaignId);

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
      <PageHeader
        title="Analytics"
        description="Reply rate by segment, trigger, and hook type. Reply = any inbound; Interested = LLM-classified positive intent."
      />

      <KpiStrip totals={a.totals} />

      <div className="mt-10">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-300">
          Head-to-head
        </h2>
        <div className="mt-4 grid gap-10 lg:grid-cols-2">
          <Breakdown
            title="By campaign × channel"
            subtitle="Which campaign + channel actually converts"
            rows={a.byCampaignChannel}
          />
          <Breakdown
            title="By channel"
            subtitle="LinkedIn vs email, overall"
            rows={a.byChannel}
          />
        </div>
      </div>

      {a.experiments.length > 0 && (
        <div className="mt-10">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-300">
            Experiments
          </h2>
          <p className="mt-1 text-xs text-neutral-500">
            A/B tests across email, LinkedIn, and search. A winner is only flagged once each arm has
            enough volume to be meaningful — small leads aren’t called.
          </p>
          <div className="mt-4 grid gap-6 lg:grid-cols-2">
            {a.experiments.map((e) => (
              <ExperimentCard key={e.key} exp={e} />
            ))}
          </div>
        </div>
      )}

      <div className="mt-10 grid gap-10 lg:grid-cols-2">
        <Breakdown
          title="By campaign"
          subtitle="Which audience + offer is landing"
          rows={a.byCampaign}
        />
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

function ExperimentCard({ exp }: { exp: Experiment }) {
  const hasWinner = exp.variants.some((v) => v.isWinner);
  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-neutral-200">{exp.title}</h3>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-neutral-500">
          {exp.metric === "acceptRate" ? "accept rate" : "reply rate"} decides
        </span>
      </div>
      <p className="mt-0.5 text-xs text-neutral-500">{exp.subtitle}</p>
      <div className="mt-3 space-y-2">
        {exp.variants.map((v) => (
          <VariantBar key={v.variant} v={v} metric={exp.metric} sampleLabel={exp.sampleLabel} />
        ))}
      </div>
      {!hasWinner && (
        <p className="mt-2 text-[11px] italic text-neutral-600">Gathering data — no clear winner yet.</p>
      )}
    </section>
  );
}

function VariantBar({
  v,
  metric,
  sampleLabel,
}: {
  v: VariantStat;
  metric: "replyRate" | "acceptRate";
  sampleLabel: string;
}) {
  const headline = metric === "acceptRate" ? v.acceptRate ?? 0 : v.replyRate;
  return (
    <div
      className={clsx(
        "rounded-md border p-3",
        v.isWinner ? "border-emerald-800 bg-emerald-950/30" : "border-neutral-800 bg-neutral-950",
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate font-mono text-sm text-neutral-200">
          {v.variant.toUpperCase()}
          {v.label && <span className="text-neutral-500"> · {v.label}</span>}
          {v.isWinner && (
            <span className="ml-2 rounded border border-emerald-800 bg-emerald-950 px-1.5 py-0.5 font-mono text-[10px] uppercase text-emerald-300">
              winner
            </span>
          )}
        </span>
        <span className={clsx("shrink-0 font-mono text-lg", rateTone(headline, "reply"))}>{pct(headline)}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[11px] text-neutral-500">
        <span>
          {fmt(v.sample)} {sampleLabel}
        </span>
        {v.accepted != null && <span>{fmt(v.accepted)} accepted</span>}
        <span>{fmt(v.replied)} replied</span>
        {v.avgFit != null && <span>fit {v.avgFit.toFixed(0)}</span>}
      </div>
    </div>
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
