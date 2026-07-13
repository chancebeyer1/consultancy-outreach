"use client";

import clsx from "clsx";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "../../../components/PageHeader";
import type { Campaign, LeadChannelKind, LeadDisplayStatus, LeadRow } from "../../../lib/types";

export const PAGE_SIZE = 50;

// Detail payload for an expanded row (from /api/lead-detail).
interface LeadDetail {
  score: { fit_score: number | null; rationale: string | null } | null;
  hooks: Array<{ type: string | null; reference: string | null }>;
  messages: Array<{
    id: string;
    channel: string;
    step_index: number;
    variant: string | null;
    status: string;
    body: string;
    generated_at: string | null;
    send: { status: string; sent_at: string | null } | null;
  }>;
}

const MESSAGE_LABEL: Record<string, string> = {
  linkedin_connect: "Connect note",
  linkedin_dm: "DM (post-accept)",
  linkedin_inmail: "InMail",
  linkedin_followup_1: "LinkedIn follow-up 1",
  linkedin_followup_2: "LinkedIn follow-up 2",
  email: "Email",
  email_followup_1: "Email follow-up 1",
  email_followup_2: "Email follow-up 2",
};

const DRAFT_STATUS_CLS: Record<string, string> = {
  draft: "bg-neutral-800 text-neutral-300",
  approved: "bg-sky-900/50 text-sky-300",
  sent: "bg-amber-900/50 text-amber-300",
  rejected: "bg-red-900/50 text-red-300",
};

const STATUS_META: Record<LeadDisplayStatus, { label: string; cls: string }> = {
  new: { label: "New", cls: "bg-neutral-800 text-neutral-300" },
  queued: { label: "Queued", cls: "bg-sky-900/50 text-sky-300" },
  sent: { label: "Sent", cls: "bg-amber-900/50 text-amber-300" },
  connected: { label: "Connected", cls: "bg-violet-900/50 text-violet-300" },
  replied: { label: "Replied", cls: "bg-emerald-900/50 text-emerald-300" },
};

const CHANNEL_META: Record<LeadChannelKind, { label: string; cls: string }> = {
  linkedin: { label: "LinkedIn", cls: "bg-sky-900/50 text-sky-300" },
  email: { label: "Email", cls: "bg-emerald-900/50 text-emerald-300" },
};

const FILTERS: Array<{ key: "all" | LeadDisplayStatus; label: string }> = [
  { key: "all", label: "All" },
  { key: "queued", label: "Queued" },
  { key: "sent", label: "Sent" },
  { key: "connected", label: "Connected" },
  { key: "replied", label: "Replied" },
];

const CHANNELS: Array<{ key: "all" | LeadChannelKind; label: string }> = [
  { key: "all", label: "All channels" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "email", label: "Email" },
];

interface Props {
  rows: LeadRow[];
  campaigns: Campaign[];
  total: number;
  filteredTotal: number;
  statusCounts: Record<string, number>;
  channelCounts: Record<string, number>;
  page: number;
  status: "all" | LeadDisplayStatus;
  channel: "all" | LeadChannelKind;
  q: string;
}

// Email + a verification dot: green = deliverable, red = bad, amber = risky/unknown.
function emailCell(email?: string | null, status?: string | null) {
  if (!email) return <span className="text-neutral-600">—</span>;
  const tone =
    status === "deliverable"
      ? "bg-emerald-500"
      : status === "undeliverable" || status === "invalid"
        ? "bg-red-500"
        : "bg-amber-500";
  return (
    <span className="flex items-center gap-1.5" title={status ?? "unknown"}>
      <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", tone)} />
      <span className="max-w-[15rem] truncate font-mono text-xs text-neutral-300">{email}</span>
    </span>
  );
}

export function LeadsClient({
  rows,
  campaigns,
  total,
  filteredTotal,
  statusCounts,
  channelCounts,
  page,
  status,
  channel,
  q,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const [search, setSearch] = useState(q);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, LeadDetail | "loading" | "error">>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Build a URL for a filter/page change; page resets whenever a filter changes.
  function hrefFor(next: Partial<{ status: string; channel: string; q: string; page: number }>) {
    const p = new URLSearchParams();
    const s = next.status ?? status;
    const c = next.channel ?? channel;
    const query = next.q ?? q;
    const pg = next.page ?? 1;
    if (s !== "all") p.set("status", s);
    if (c !== "all") p.set("channel", c);
    if (query) p.set("q", query);
    if (pg > 1) p.set("page", String(pg));
    const qs = p.toString();
    return qs ? `${pathname}?${qs}` : pathname;
  }

  // Debounced search → URL (server re-queries). Keeps typing snappy at any lead count.
  useEffect(() => {
    if (search === q) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      router.replace(hrefFor({ q: search, page: 1 }), { scroll: false });
    }, 350);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  async function toggleRow(leadId: string) {
    if (expandedId === leadId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(leadId);
    if (details[leadId] && details[leadId] !== "error") return; // cached
    setDetails((d) => ({ ...d, [leadId]: "loading" }));
    try {
      const res = await fetch("/api/lead-detail", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ leadId }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as LeadDetail;
      setDetails((d) => ({ ...d, [leadId]: data }));
    } catch {
      setDetails((d) => ({ ...d, [leadId]: "error" }));
    }
  }

  const campaignName = useMemo(() => {
    const m = new Map(campaigns.map((c) => [c.id, c.name]));
    return (id: string | null) => (id ? (m.get(id) ?? "—") : "—");
  }, [campaigns]);

  const lastPage = Math.max(1, Math.ceil(filteredTotal / PAGE_SIZE));
  const showFrom = filteredTotal === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const showTo = Math.min(page * PAGE_SIZE, filteredTotal);

  const statusCount = (k: string) => (k === "all" ? total : (statusCounts[k] ?? 0));
  const channelCount = (k: string) => (k === "all" ? total : (channelCounts[k] ?? 0));

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <PageHeader
        title="Leads"
        description={`${total.toLocaleString()} total · filter by status, or use the campaign selector up top.`}
      >
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, company, role, email…"
          className="w-56 rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none sm:w-64"
        />
      </PageHeader>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => router.push(hrefFor({ status: f.key, page: 1 }), { scroll: false })}
            className={clsx(
              "rounded-full px-3 py-1 text-xs font-medium",
              status === f.key
                ? "bg-neutral-200 text-neutral-900"
                : "border border-neutral-700 text-neutral-400 hover:bg-neutral-900",
            )}
          >
            {f.label} <span className="opacity-60">{statusCount(f.key).toLocaleString()}</span>
          </button>
        ))}

        <span className="mx-1 hidden h-5 w-px bg-neutral-800 sm:inline-block" aria-hidden />

        {CHANNELS.map((c) => (
          <button
            key={c.key}
            onClick={() => router.push(hrefFor({ channel: c.key, page: 1 }), { scroll: false })}
            className={clsx(
              "rounded-full px-3 py-1 text-xs font-medium",
              channel === c.key
                ? "bg-neutral-200 text-neutral-900"
                : "border border-neutral-700 text-neutral-400 hover:bg-neutral-900",
            )}
          >
            {c.label} <span className="opacity-60">{channelCount(c.key).toLocaleString()}</span>
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-lg border border-neutral-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-800 text-left text-xs uppercase tracking-wide text-neutral-500">
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Email</th>
              <th className="px-4 py-2 font-medium">Role</th>
              <th className="px-4 py-2 font-medium">Location</th>
              <th className="px-4 py-2 text-right font-medium">Fit</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Channel</th>
              <th className="px-4 py-2 font-medium">Campaign</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const meta = STATUS_META[r.display_status];
              const isOpen = expandedId === r.lead.id;
              const detail = details[r.lead.id];
              return (
                <Fragment key={r.lead.id}>
                <tr
                  onClick={() => toggleRow(r.lead.id)}
                  className={clsx(
                    "cursor-pointer border-b border-neutral-900 last:border-0 hover:bg-neutral-900/50",
                    isOpen && "bg-neutral-900/50",
                  )}
                >
                  <td className="px-4 py-2.5">
                    <a
                      href={r.lead.linkedin_url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="font-medium text-neutral-100 hover:text-sky-400 hover:underline"
                    >
                      {r.lead.name ?? "—"}
                    </a>
                  </td>
                  <td className="px-4 py-2.5 text-neutral-400">{r.lead.company ?? "—"}</td>
                  <td className="px-4 py-2.5">{emailCell(r.lead.email, r.lead.email_status)}</td>
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
                  <td className="px-4 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      {r.channels.map((k) => (
                        <span
                          key={k}
                          className={clsx(
                            "rounded-full px-2 py-0.5 text-xs font-medium",
                            CHANNEL_META[k].cls,
                          )}
                        >
                          {CHANNEL_META[k].label}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-neutral-500">{campaignName(r.lead.campaign_id)}</td>
                </tr>
                {isOpen && (
                  <tr className="border-b border-neutral-900 last:border-0">
                    <td colSpan={9} className="bg-neutral-950/70 px-6 py-4">
                      {detail === "loading" || detail === undefined ? (
                        <p className="text-sm text-neutral-500">Loading…</p>
                      ) : detail === "error" ? (
                        <p className="text-sm text-red-400">Couldn&apos;t load details.</p>
                      ) : (
                        <div className="space-y-4">
                          {detail.score?.rationale && (
                            <div>
                              <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
                                Why this fit score
                              </p>
                              <p className="mt-1 max-w-3xl text-sm text-neutral-400">
                                {detail.score.rationale}
                              </p>
                            </div>
                          )}
                          <div>
                            <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
                              Messages
                            </p>
                            {detail.messages.length === 0 ? (
                              <p className="mt-1 text-sm text-neutral-500">Nothing drafted yet.</p>
                            ) : (
                              <ul className="mt-2 space-y-3">
                                {detail.messages.map((m) => (
                                  <li key={m.id} className="max-w-3xl">
                                    <div className="flex flex-wrap items-center gap-2 text-xs">
                                      <span className="font-medium text-neutral-300">
                                        {MESSAGE_LABEL[m.channel] ?? m.channel}
                                        {m.step_index > 0 && !MESSAGE_LABEL[m.channel]
                                          ? ` · step ${m.step_index + 1}`
                                          : ""}
                                      </span>
                                      {m.variant && (
                                        <span className="rounded-full border border-neutral-700 px-1.5 text-[10px] uppercase text-neutral-500">
                                          variant {m.variant}
                                        </span>
                                      )}
                                      <span
                                        className={clsx(
                                          "rounded-full px-2 py-0.5 font-medium",
                                          DRAFT_STATUS_CLS[m.status] ?? DRAFT_STATUS_CLS.draft,
                                        )}
                                      >
                                        {m.send
                                          ? `sent ${m.send.sent_at ? new Date(m.send.sent_at).toLocaleDateString() : ""}`
                                          : m.status}
                                      </span>
                                    </div>
                                    <p className="mt-1 whitespace-pre-wrap rounded-md border border-neutral-800 bg-neutral-900/60 px-3 py-2 text-sm text-neutral-200">
                                      {m.body || "—"}
                                    </p>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="px-4 py-16 text-center text-sm text-neutral-500">
            No leads match this filter.
          </div>
        )}
      </div>

      {/* Pagination — server-side pages of PAGE_SIZE. */}
      <div className="mt-4 flex items-center justify-between text-sm text-neutral-400">
        <span>
          {showFrom.toLocaleString()}–{showTo.toLocaleString()} of {filteredTotal.toLocaleString()}
          {status !== "all" || channel !== "all" || q ? " matching" : ""}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push(hrefFor({ page: page - 1 }), { scroll: false })}
            disabled={page <= 1}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-900 disabled:opacity-40"
          >
            ← Prev
          </button>
          <span className="text-xs text-neutral-500">
            Page {page} of {lastPage}
          </span>
          <button
            onClick={() => router.push(hrefFor({ page: page + 1 }), { scroll: false })}
            disabled={page >= lastPage}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-900 disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}
