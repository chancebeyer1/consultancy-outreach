"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { titleCase } from "@/lib/labels";

export type Deal = {
  id: string;
  contact_name: string | null;
  company: string | null;
  value_usd: number | string | null;
  stage: string;
  source: string | null;
  notes: string | null;
  brief: string | null;
  created_at: string | null;
  updated_at: string | null;
};

const STAGES = [
  { key: "interested", label: "Interested", dot: "bg-sky-400" },
  { key: "call_booked", label: "Call Booked", dot: "bg-violet-400" },
  { key: "proposal_sent", label: "Proposal Sent", dot: "bg-amber-400" },
  { key: "won", label: "Won", dot: "bg-emerald-400" },
] as const;
const ALL_STAGES = ["interested", "call_booked", "proposal_sent", "won", "lost"];

const money = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k` : `$${n}`;
const val = (d: Deal) => Number(d.value_usd ?? 0) || 0;

export function PipelineClient({ deals }: { deals: Deal[] }) {
  const open = deals.filter((d) => ["interested", "call_booked", "proposal_sent"].includes(d.stage));
  const won = deals.filter((d) => d.stage === "won");
  const lostCount = deals.filter((d) => d.stage === "lost").length;
  const openValue = open.reduce((s, d) => s + val(d), 0);
  const wonValue = won.reduce((s, d) => s + val(d), 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Kpi label="Open Pipeline" value={money(openValue)} />
        <Kpi label="Open Deals" value={String(open.length)} />
        <Kpi label="Won" value={`${won.length} · ${money(wonValue)}`} tone="text-emerald-400" />
        <Kpi label="Lost" value={String(lostCount)} tone="text-neutral-500" />
      </div>

      <AddDeal />

      <div className="grid gap-4 lg:grid-cols-4">
        {STAGES.map((s) => {
          const col = deals.filter((d) => d.stage === s.key);
          const sum = col.reduce((a, d) => a + val(d), 0);
          return (
            <div key={s.key} className="rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
              <div className="mb-3 flex items-center justify-between px-0.5">
                <span className="flex items-center gap-2 text-sm font-semibold text-neutral-200">
                  <span className={`h-2 w-2 rounded-full ${s.dot}`} />
                  {s.label}
                </span>
                <span className="font-mono text-xs text-neutral-500">
                  {col.length}
                  {sum > 0 ? ` · ${money(sum)}` : ""}
                </span>
              </div>
              <div className="space-y-2.5">
                {col.map((d) => (
                  <DealCard key={d.id} deal={d} />
                ))}
                {col.length === 0 && (
                  <p className="rounded-lg border border-dashed border-neutral-800 px-2 py-5 text-center text-xs italic text-neutral-600">
                    Nothing here yet
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DealCard({ deal }: { deal: Deal }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function setStage(stage: string) {
    setBusy(true);
    try {
      const res = await fetch("/api/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "update", id: deal.id, stage }),
      });
      if (res.ok) router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const v = val(deal);
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-3 transition hover:border-neutral-700">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/pipeline/${deal.id}`} className="group min-w-0">
          <div className="truncate text-sm font-semibold text-neutral-100 group-hover:text-sky-300">
            {deal.contact_name || "Unnamed contact"}
          </div>
          {deal.company && <div className="truncate text-xs text-neutral-500">{deal.company}</div>}
        </Link>
        {deal.source && (
          <span className="shrink-0 rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-neutral-400">
            {titleCase(deal.source)}
          </span>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        {v > 0 ? (
          <span className="font-mono text-xs text-neutral-300">{money(v)}</span>
        ) : (
          <span className="text-[11px] text-neutral-600">No value</span>
        )}
        <select
          value={deal.stage}
          onChange={(e) => setStage(e.target.value)}
          disabled={busy}
          className="rounded-md border border-neutral-800 bg-neutral-900 px-1.5 py-1 text-[11px] text-neutral-300 focus:border-sky-600 focus:outline-none"
        >
          {ALL_STAGES.map((s) => (
            <option key={s} value={s}>
              {titleCase(s)}
            </option>
          ))}
        </select>
      </div>

      <Link
        href={`/pipeline/${deal.id}`}
        className="mt-2.5 flex items-center gap-1 text-xs font-medium text-sky-400 hover:text-sky-300"
      >
        {deal.brief ? "Meeting prep ready" : "Open deal"}
        <span aria-hidden>→</span>
      </Link>
    </div>
  );
}

function AddDeal() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ contact_name: "", company: "", value_usd: "", notes: "" });
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      const res = await fetch("/api/pipeline", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "create", ...f }),
      });
      if (res.ok) {
        setF({ contact_name: "", company: "", value_usd: "", notes: "" });
        setOpen(false);
        router.refresh();
      }
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-800"
      >
        + Add Deal
      </button>
    );
  }
  const input =
    "rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none";
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <div className="grid gap-2 sm:grid-cols-3">
        <input className={input} placeholder="Contact name" value={f.contact_name} onChange={(e) => setF({ ...f, contact_name: e.target.value })} />
        <input className={input} placeholder="Company" value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} />
        <input className={input} placeholder="Value (USD)" inputMode="numeric" value={f.value_usd} onChange={(e) => setF({ ...f, value_usd: e.target.value })} />
      </div>
      <textarea className={`${input} mt-2 w-full`} rows={2} placeholder="Notes (optional)" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
      <div className="mt-2 flex gap-2">
        <button onClick={submit} disabled={busy} className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50">
          {busy ? "Adding..." : "Add Deal"}
        </button>
        <button onClick={() => setOpen(false)} className="rounded-md px-3 py-1.5 text-xs text-neutral-400 hover:text-neutral-200">
          Cancel
        </button>
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className={`mt-1 font-mono text-xl ${tone ?? "text-neutral-100"}`}>{value}</div>
    </div>
  );
}
