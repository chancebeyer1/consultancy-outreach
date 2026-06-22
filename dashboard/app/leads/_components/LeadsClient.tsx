"use client";

import clsx from "clsx";
import { useMemo, useState } from "react";
import type { Campaign, LeadDisplayStatus, LeadRow } from "../../../lib/types";

const STATUS_META: Record<LeadDisplayStatus, { label: string; cls: string }> = {
  new: { label: "New", cls: "bg-neutral-800 text-neutral-300" },
  queued: { label: "Queued", cls: "bg-sky-900/50 text-sky-300" },
  sent: { label: "Sent", cls: "bg-amber-900/50 text-amber-300" },
  connected: { label: "Connected", cls: "bg-violet-900/50 text-violet-300" },
  replied: { label: "Replied", cls: "bg-emerald-900/50 text-emerald-300" },
};

const FILTERS: Array<{ key: "all" | LeadDisplayStatus; label: string }> = [
  { key: "all", label: "All" },
  { key: "queued", label: "Queued" },
  { key: "sent", label: "Sent" },
  { key: "connected", label: "Connected" },
  { key: "replied", label: "Replied" },
];

interface Props {
  rows: LeadRow[];
  campaigns: Campaign[];
}

export function LeadsClient({ rows, campaigns }: Props) {
  const [filter, setFilter] = useState<"all" | LeadDisplayStatus>("all");
  const [q, setQ] = useState("");

  const campaignName = useMemo(() => {
    const m = new Map(campaigns.map((c) => [c.id, c.name]));
    return (id: string | null) => (id ? (m.get(id) ?? "—") : "—");
  }, [campaigns]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: rows.length };
    for (const r of rows) c[r.display_status] = (c[r.display_status] ?? 0) + 1;
    return c;
  }, [rows]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((r) => {
      if (filter !== "all" && r.display_status !== filter) return false;
      if (!needle) return true;
      const hay =
        `${r.lead.name ?? ""} ${r.lead.company ?? ""} ${r.lead.role ?? ""} ${r.lead.location ?? ""}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [rows, filter, q]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Leads</h1>
          <p className="mt-1 text-sm text-neutral-500">
            {rows.length} total · filter by status, or use the campaign selector up top.
          </p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name, company, role…"
          className="w-64 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
        />
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={clsx(
              "rounded-full px-3 py-1 text-xs font-medium",
              filter === f.key
                ? "bg-neutral-200 text-neutral-900"
                : "border border-neutral-700 text-neutral-400 hover:bg-neutral-900",
            )}
          >
            {f.label} <span className="opacity-60">{counts[f.key] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-neutral-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wide text-neutral-500">
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Role</th>
              <th className="px-4 py-2 font-medium">Location</th>
              <th className="px-4 py-2 text-right font-medium">Fit</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Campaign</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const meta = STATUS_META[r.display_status];
              return (
                <tr
                  key={r.lead.id}
                  className="border-b border-neutral-900 last:border-0 hover:bg-neutral-900/50"
                >
                  <td className="px-4 py-2.5">
                    <a
                      href={r.lead.linkedin_url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-medium text-neutral-100 hover:text-sky-400 hover:underline"
                    >
                      {r.lead.name ?? "—"}
                    </a>
                  </td>
                  <td className="px-4 py-2.5 text-neutral-400">{r.lead.company ?? "—"}</td>
                  <td className="max-w-[18rem] truncate px-4 py-2.5 text-neutral-400">
                    {r.lead.role ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-neutral-500">{r.lead.location ?? "—"}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-neutral-300">
                    {r.fit_score ?? "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={clsx("rounded-full px-2 py-0.5 text-xs font-medium", meta.cls)}>
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-neutral-500">{campaignName(r.lead.campaign_id)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="px-4 py-16 text-center text-sm text-neutral-500">
            No leads match this filter.
          </div>
        )}
      </div>
    </div>
  );
}
