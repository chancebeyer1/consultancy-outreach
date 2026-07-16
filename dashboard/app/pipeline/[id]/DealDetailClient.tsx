"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import type { DealDetail } from "@/lib/queries";
import { titleCase } from "@/lib/labels";

const STAGES = ["interested", "call_booked", "proposal_sent", "won", "lost"];
const STAGE_TONE: Record<string, string> = {
  interested: "border-sky-800 bg-sky-950 text-sky-300",
  call_booked: "border-violet-800 bg-violet-950 text-violet-300",
  proposal_sent: "border-amber-800 bg-amber-950 text-amber-300",
  won: "border-emerald-800 bg-emerald-950 text-emerald-300",
  lost: "border-neutral-700 bg-neutral-900 text-neutral-500",
};
const money = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(n % 1000 === 0 ? 0 : 1)}k` : `$${n}`;

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
function fmtDateTime(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

async function post(payload: object): Promise<{ ok: boolean; error?: string }> {
  const res = await fetch("/api/pipeline", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, error: data?.error };
}

export function DealDetailClient({ detail }: { detail: DealDetail }) {
  const { deal, lead, campaignName, messages, notes, auditReport } = detail;
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const name = deal.contact_name || lead?.name || "Unnamed contact";
  const company = deal.company || lead?.company;
  const valueNum = Number(deal.value_usd ?? 0) || 0;

  async function setStage(stage: string) {
    setBusy(true);
    const r = await post({ action: "update", id: deal.id, stage });
    setBusy(false);
    if (r.ok) router.refresh();
  }

  const { meetings } = detail;

  return (
    <div className="space-y-6">
      <Link href="/pipeline" className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-200">
        <span aria-hidden>←</span> Pipeline
      </Link>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-neutral-100">{name}</h1>
          <p className="mt-1 text-sm text-neutral-400">
            {[lead?.role, company].filter(Boolean).join(" · ") || "No title on file"}
            {lead?.location ? `  ·  ${lead.location}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={`rounded-md border px-2.5 py-1 text-xs font-medium ${STAGE_TONE[deal.stage] ?? "border-neutral-700 text-neutral-300"}`}>
            {titleCase(deal.stage)}
          </span>
          {valueNum > 0 && <span className="font-mono text-lg text-neutral-100">{money(valueNum)}</span>}
        </div>
      </div>

      <DealControls deal={deal} busy={busy} setBusy={setBusy} onStage={setStage} />

      <div className="grid gap-5 lg:grid-cols-3">
        {/* Main column */}
        <div className="space-y-5 lg:col-span-2">
          {auditReport && <AuditReportView report={auditReport} />}
          <MeetingPrep deal={deal} />
          <Meetings dealId={deal.id} meetings={meetings} />
          <Conversation messages={messages} />
        </div>
        {/* Sidebar */}
        <div className="space-y-5">
          <ContactCard deal={deal} lead={lead} campaignName={campaignName} />
          <NotesFeed dealId={deal.id} legacyNote={deal.notes} notes={notes} />
        </div>
      </div>
    </div>
  );
}

function DealControls({
  deal,
  busy,
  setBusy,
  onStage,
}: {
  deal: DealDetail["deal"];
  busy: boolean;
  setBusy: (v: boolean) => void;
  onStage: (s: string) => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState(deal.value_usd != null ? String(deal.value_usd) : "");
  const [nextAction, setNextAction] = useState(deal.next_action ?? "");
  const dirty =
    value !== (deal.value_usd != null ? String(deal.value_usd) : "") || nextAction !== (deal.next_action ?? "");

  async function save() {
    setBusy(true);
    const r = await post({ action: "update", id: deal.id, value_usd: value, next_action: nextAction });
    setBusy(false);
    if (r.ok) router.refresh();
  }

  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-neutral-500">Stage</span>
          <select
            value={deal.stage}
            onChange={(e) => onStage(e.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-sky-600 focus:outline-none"
          >
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-neutral-500">Deal value (USD)</span>
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            inputMode="numeric"
            placeholder="e.g. 12000"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-sky-600 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-neutral-500">Next step</span>
          <input
            value={nextAction}
            onChange={(e) => setNextAction(e.target.value)}
            placeholder="e.g. Send proposal Fri"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-sky-600 focus:outline-none"
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {dirty && (
          <button
            onClick={save}
            disabled={busy}
            className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {busy ? "Saving..." : "Save"}
          </button>
        )}
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => onStage("won")}
            disabled={busy || deal.stage === "won"}
            className="rounded-md border border-emerald-800 bg-emerald-950/50 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-900/50 disabled:opacity-40"
          >
            Mark Won
          </button>
          <button
            onClick={() => onStage("lost")}
            disabled={busy || deal.stage === "lost"}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-400 hover:bg-neutral-800 disabled:opacity-40"
          >
            Mark Lost
          </button>
        </div>
      </div>
    </div>
  );
}

function MeetingPrep({ deal }: { deal: DealDetail["deal"] }) {
  const router = useRouter();
  const [prep, setPrep] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function prepare() {
    setPrep(true);
    setMsg(null);
    const r = await post({ action: "prepare", id: deal.id });
    setPrep(false);
    if (r.ok) router.refresh();
    else setMsg(r.error || "Research failed");
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Meeting prep</h2>
        <button
          onClick={prepare}
          disabled={prep}
          className="rounded-md border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 hover:bg-neutral-800 disabled:opacity-50"
        >
          {prep ? "Researching..." : deal.brief ? "Refresh" : "Prepare"}
        </button>
      </div>
      {deal.brief ? (
        <>
          <BriefView text={deal.brief} />
          {deal.brief_generated_at && (
            <p className="mt-3 text-[10px] text-neutral-600">Researched {fmtDate(deal.brief_generated_at)}</p>
          )}
        </>
      ) : (
        <p className="text-sm italic text-neutral-500">
          {msg || "No brief yet. Click Prepare to research this person and draft a call plan."}
        </p>
      )}
      {msg && deal.brief && <p className="mt-2 text-[11px] text-amber-400">{msg}</p>}
    </section>
  );
}

// Render the meeting-prep brief as clean sections (prompt emits uppercase header lines).
function BriefView({ text }: { text: string }) {
  const isHeader = (l: string) => {
    const t = l.trim();
    return t.length > 1 && t.length < 48 && /^[A-Z][A-Z0-9 ,/&'-]+$/.test(t) && t === t.toUpperCase();
  };
  const sections: { title: string; body: string }[] = [];
  let cur: { title: string; lines: string[] } | null = null;
  for (const line of text.split("\n")) {
    if (isHeader(line)) {
      if (cur) sections.push({ title: cur.title, body: cur.lines.join("\n").trim() });
      cur = { title: line.trim(), lines: [] };
    } else if (cur) {
      cur.lines.push(line);
    } else if (line.trim()) {
      cur = { title: "", lines: [line] };
    }
  }
  if (cur) sections.push({ title: cur.title, body: cur.lines.join("\n").trim() });

  if (sections.length <= 1) {
    return <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-neutral-300">{text}</p>;
  }
  return (
    <div className="space-y-3.5">
      {sections.map((s, i) => (
        <div key={i}>
          {s.title && (
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-sky-400/90">
              {titleCase(s.title)}
            </div>
          )}
          <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-neutral-300">{s.body}</p>
        </div>
      ))}
    </div>
  );
}

// Meeting intelligence: paste a call transcript → the backend extracts pains, buying signals,
// process-automation candidates (factory export), and drafts the follow-up.
function Meetings({ dealId, meetings }: { dealId: string; meetings: DealDetail["meetings"] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [transcript, setTranscript] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // While any transcript is processing, poll so the extraction appears without a manual reload.
  const processing = meetings.some((m) => m.status === "new");
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(() => router.refresh(), 6000);
    return () => clearInterval(t);
  }, [processing, router]);

  async function add() {
    if (transcript.trim().length < 200) {
      setErr("Paste the full transcript (a real call is longer than 200 characters).");
      return;
    }
    setBusy(true);
    setErr(null);
    const r = await post({ action: "add_meeting", id: dealId, title, transcript });
    setBusy(false);
    if (!r.ok) {
      setErr(r.error || "Failed to save the transcript");
      return;
    }
    setTitle("");
    setTranscript("");
    setOpen(false);
    router.refresh();
  }

  async function reprocess(meetingId: string) {
    setBusy(true);
    await post({ action: "reprocess_meeting", id: dealId, meeting_id: meetingId });
    setBusy(false);
    router.refresh();
  }

  function copyFollowUp(m: DealDetail["meetings"][number]) {
    if (!m.follow_up_draft) return;
    navigator.clipboard.writeText(m.follow_up_draft).then(() => {
      setCopiedId(m.id);
      setTimeout(() => setCopiedId(null), 1500);
    });
  }

  function downloadExport(m: DealDetail["meetings"][number]) {
    const blob = new Blob([JSON.stringify(m.factory_export ?? {}, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `factory-export-${m.id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Meetings</h2>
        <button
          onClick={() => setOpen((v) => !v)}
          className="rounded-md border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300 hover:bg-neutral-800"
        >
          {open ? "Close" : "+ Add transcript"}
        </button>
      </div>

      {open && (
        <div className="mb-4 rounded-lg border border-neutral-800 bg-neutral-900/50 p-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title, e.g. Discovery call Jul 15"
            className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-sm text-neutral-200 focus:border-sky-600 focus:outline-none"
          />
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={8}
            placeholder="Paste the call transcript (Zoom / Meet / Otter export)…"
            className="mt-2 w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 p-2.5 font-mono text-[12px] leading-relaxed text-neutral-200 focus:border-sky-600 focus:outline-none"
          />
          {err && <p className="mt-2 text-xs text-red-400">{err}</p>}
          <button
            onClick={add}
            disabled={busy || !transcript.trim()}
            className="mt-2 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save + extract"}
          </button>
        </div>
      )}

      {meetings.length === 0 && !open && (
        <p className="text-sm italic text-neutral-500">
          No transcripts yet. Paste a discovery-call transcript and the agent extracts pains,
          buying signals, automation candidates, and drafts the follow-up.
        </p>
      )}

      <div className="space-y-4">
        {meetings.map((m) => {
          const ex = m.extraction;
          return (
            <div key={m.id} className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0 text-[13px] font-medium text-neutral-200">
                  {m.title || "Untitled meeting"}
                  <span className="ml-2 text-[10px] font-normal text-neutral-600">{fmtDateTime(m.created_at)}</span>
                </div>
                {m.status === "new" && (
                  <span className="shrink-0 rounded-full border border-amber-800 bg-amber-950/50 px-2 py-0.5 text-[10px] text-amber-300">
                    Extracting…
                  </span>
                )}
                {m.status === "failed" && (
                  <button
                    onClick={() => reprocess(m.id)}
                    disabled={busy}
                    className="shrink-0 rounded-full border border-red-800 bg-red-950/50 px-2 py-0.5 text-[10px] text-red-300 hover:bg-red-900/50"
                  >
                    Failed — retry
                  </button>
                )}
              </div>

              {m.status === "failed" && m.error && (
                <p className="mt-1 text-[11px] text-red-400/80">{m.error}</p>
              )}

              {m.status === "processed" && ex && (
                <div className="mt-2 space-y-3">
                  {ex.summary && (
                    <p className="text-[13px] leading-relaxed text-neutral-300">{ex.summary}</p>
                  )}

                  {(ex.pains?.length ?? 0) > 0 && (
                    <div>
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-sky-400/90">Pains</div>
                      <ul className="space-y-1">
                        {ex.pains!.map((pn, i) => (
                          <li key={i} className="text-[12px] leading-relaxed text-neutral-300">
                            <span
                              className={
                                pn.severity === "high"
                                  ? "text-red-400"
                                  : pn.severity === "medium"
                                    ? "text-amber-400"
                                    : "text-neutral-500"
                              }
                            >
                              ●
                            </span>{" "}
                            {pn.pain}
                            {pn.quote && <span className="text-neutral-500"> — “{pn.quote}”</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {((ex.budget_signals?.length ?? 0) > 0 || (ex.timeline_signals?.length ?? 0) > 0) && (
                    <div className="flex flex-wrap gap-1.5">
                      {(ex.budget_signals ?? []).map((s, i) => (
                        <span key={`b${i}`} className="rounded-full border border-emerald-800 bg-emerald-950/40 px-2 py-0.5 text-[10px] text-emerald-300">
                          $ {s}
                        </span>
                      ))}
                      {(ex.timeline_signals ?? []).map((s, i) => (
                        <span key={`t${i}`} className="rounded-full border border-violet-800 bg-violet-950/40 px-2 py-0.5 text-[10px] text-violet-300">
                          ⏱ {s}
                        </span>
                      ))}
                    </div>
                  )}

                  {(ex.next_steps?.length ?? 0) > 0 && (
                    <div>
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-sky-400/90">Next steps</div>
                      <ul className="space-y-0.5">
                        {ex.next_steps!.map((s, i) => (
                          <li key={i} className="text-[12px] text-neutral-300">
                            <span className={s.owner === "us" ? "text-sky-400" : "text-neutral-500"}>
                              {s.owner === "us" ? "You:" : "Them:"}
                            </span>{" "}
                            {s.action}
                            {s.due_hint && <span className="text-neutral-600"> ({s.due_hint})</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {(ex.process_candidates?.length ?? 0) > 0 && (
                    <div>
                      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-sky-400/90">
                        Automation candidates ({ex.process_candidates!.length})
                      </div>
                      <ul className="space-y-1.5">
                        {ex.process_candidates!.map((c, i) => (
                          <li key={i} className="rounded-md border border-neutral-800 bg-neutral-950 p-2">
                            <div className="text-[12px] font-medium text-neutral-200">{c.name}</div>
                            {c.description && (
                              <p className="mt-0.5 text-[11px] leading-relaxed text-neutral-400">{c.description}</p>
                            )}
                            {c.scores && (
                              <div className="mt-1 font-mono text-[10px] text-neutral-500">
                                freq {c.scores.frequency ?? "–"} · time {c.scores.time_cost ?? "–"} · auto{" "}
                                {c.scores.automatability ?? "–"} · risk {c.scores.risk ?? "–"}
                              </div>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {m.follow_up_draft && (
                    <div>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-[10px] font-semibold uppercase tracking-wider text-sky-400/90">
                          Follow-up draft
                        </span>
                        <button
                          onClick={() => copyFollowUp(m)}
                          className="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-400 hover:bg-neutral-800"
                        >
                          {copiedId === m.id ? "Copied ✓" : "Copy"}
                        </button>
                      </div>
                      <p className="whitespace-pre-wrap rounded-md border border-neutral-800 bg-neutral-950 p-2.5 text-[12px] leading-relaxed text-neutral-300">
                        {m.follow_up_draft}
                      </p>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button
                      onClick={() => downloadExport(m)}
                      className="rounded-md border border-neutral-700 px-2.5 py-1 text-[11px] text-neutral-300 hover:bg-neutral-800"
                    >
                      ⬇ Factory export (JSON)
                    </button>
                    <button
                      onClick={() => reprocess(m.id)}
                      disabled={busy}
                      className="rounded-md border border-neutral-800 px-2.5 py-1 text-[11px] text-neutral-500 hover:bg-neutral-800"
                    >
                      Re-extract
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AuditReportView({ report }: { report: NonNullable<DealDetail["auditReport"]> }) {
  const opps = report.opportunities || [];
  if (!opps.length && !report.summary) return null;
  return (
    <section className="rounded-xl border border-sky-900/40 bg-sky-950/10 p-4">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-neutral-200">AI Opportunity Audit</h2>
        <span className="rounded-full bg-sky-500/15 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-sky-400">
          What they received
        </span>
      </div>
      {report.summary && (
        <p className="mb-3 text-[13px] leading-relaxed text-neutral-400">{report.summary}</p>
      )}
      <div className="space-y-2.5">
        {opps.map((o, i) => (
          <div key={i} className="rounded-lg border border-neutral-800 bg-neutral-950 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="text-[13px] font-semibold text-neutral-100">
                {i + 1}. {o.title}
              </div>
              <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
                <span className="rounded-full border border-sky-800 bg-sky-950/50 px-2 py-0.5 text-[10px] text-sky-300">
                  {o.time_saved}
                </span>
                <span className="rounded-full border border-neutral-700 bg-neutral-900 px-2 py-0.5 text-[10px] text-neutral-400">
                  {o.complexity}
                </span>
              </div>
            </div>
            <p className="mt-1.5 text-[12px] leading-relaxed text-neutral-400">
              <span className="text-neutral-500">Today:</span> {o.today}
            </p>
            <p className="mt-1 text-[12px] leading-relaxed text-neutral-300">
              <span className="text-sky-400/80">Agent:</span> {o.agent}
            </p>
          </div>
        ))}
      </div>
      {report.first_build && (
        <div className="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/40 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-sky-400">
            Where to start
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-neutral-300">{report.first_build}</p>
        </div>
      )}
      {report.note && <p className="mt-2 text-[11px] italic leading-relaxed text-neutral-500">{report.note}</p>}
    </section>
  );
}

function Conversation({ messages }: { messages: DealDetail["messages"] }) {
  if (!messages.length) return null;
  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
      <h2 className="mb-3 text-sm font-semibold text-neutral-200">Conversation</h2>
      <div className="space-y-3">
        {messages.map((m) => {
          const out = m.direction === "out";
          return (
            <div
              key={m.id}
              className={`rounded-lg border p-3 ${out ? "border-sky-900/60 bg-sky-950/20" : "border-neutral-800 bg-neutral-900/50"}`}
            >
              <div className="mb-1 flex items-center justify-between text-[11px]">
                <span className="font-medium text-neutral-300">
                  {out ? "You" : m.from_name || m.from_email || "Them"}
                </span>
                <span className="text-neutral-600">{fmtDateTime(m.received_at || m.created_at)}</span>
              </div>
              {m.subject && <div className="mb-1 text-xs font-medium text-neutral-400">{m.subject}</div>}
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-neutral-300">
                {(m.body || "").slice(0, 1500)}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ContactCard({
  deal,
  lead,
  campaignName,
}: {
  deal: DealDetail["deal"];
  lead: DealDetail["lead"];
  campaignName: string | null;
}) {
  const rows: Array<{ label: string; node: ReactNode }> = [];
  if (lead?.linkedin_url)
    rows.push({
      label: "LinkedIn",
      node: (
        <a href={lead.linkedin_url} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">
          View profile
        </a>
      ),
    });
  if (lead?.email)
    rows.push({
      label: "Email",
      node: (
        <a href={`mailto:${lead.email}`} className="text-sky-400 hover:underline">
          {lead.email}
        </a>
      ),
    });
  if (lead?.headline) rows.push({ label: "Headline", node: lead.headline });
  if (campaignName) rows.push({ label: "Campaign", node: campaignName });
  if (deal.source) rows.push({ label: "Source", node: titleCase(deal.source) });
  rows.push({ label: "Added", node: fmtDate(deal.created_at) });

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
      <h2 className="mb-3 text-sm font-semibold text-neutral-200">Contact</h2>
      <dl className="space-y-2.5">
        {rows.map((r, i) => (
          <div key={i} className="flex justify-between gap-3 text-[13px]">
            <dt className="shrink-0 text-neutral-500">{r.label}</dt>
            <dd className="min-w-0 truncate text-right text-neutral-300">{r.node}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function NotesFeed({
  dealId,
  legacyNote,
  notes,
}: {
  dealId: string;
  legacyNote: string | null;
  notes: DealDetail["notes"];
}) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!text.trim()) return;
    setBusy(true);
    const r = await post({ action: "add_note", id: dealId, body: text });
    setBusy(false);
    if (r.ok) {
      setText("");
      router.refresh();
    }
  }
  async function remove(noteId: string) {
    setBusy(true);
    const r = await post({ action: "delete_note", note_id: noteId });
    setBusy(false);
    if (r.ok) router.refresh();
  }

  return (
    <section className="rounded-xl border border-neutral-800 bg-neutral-950 p-4">
      <h2 className="mb-3 text-sm font-semibold text-neutral-200">Notes</h2>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder="Add a note..."
        className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 p-2.5 text-[13px] text-neutral-200 focus:border-sky-600 focus:outline-none"
      />
      <button
        onClick={add}
        disabled={busy || !text.trim()}
        className="mt-2 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
      >
        {busy ? "Saving..." : "Add note"}
      </button>

      <div className="mt-4 space-y-3">
        {notes.map((n) => (
          <div key={n.id} className="group rounded-lg border border-neutral-800 bg-neutral-900/40 p-2.5">
            <div className="mb-1 flex items-center justify-between text-[10px] text-neutral-600">
              <span>{fmtDateTime(n.created_at)}</span>
              <button
                onClick={() => remove(n.id)}
                className="opacity-0 transition group-hover:opacity-100 hover:text-red-400"
                aria-label="Delete note"
              >
                Delete
              </button>
            </div>
            <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-neutral-300">{n.body}</p>
          </div>
        ))}
        {legacyNote && notes.length === 0 && (
          <p className="whitespace-pre-wrap rounded-lg border border-neutral-800 bg-neutral-900/40 p-2.5 text-[13px] leading-relaxed text-neutral-300">
            {legacyNote}
          </p>
        )}
        {notes.length === 0 && !legacyNote && (
          <p className="text-xs italic text-neutral-600">No notes yet.</p>
        )}
      </div>
    </section>
  );
}
