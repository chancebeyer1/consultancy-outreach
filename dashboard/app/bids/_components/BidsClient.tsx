"use client";

import { useMemo, useState } from "react";

import type { BidReviewRow, OpportunitySource } from "@/lib/types";

type Action = "save" | "approve" | "reject" | "submit" | "pass" | "submit_api" | "won" | "lost";

const SOURCE_META: Record<OpportunitySource, { label: string; cls: string }> = {
  sam_gov: { label: "SAM.gov", cls: "bg-blue-500/15 text-blue-300 ring-blue-500/30" },
  upwork: { label: "Upwork", cls: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30" },
  freelancer: { label: "Freelancer", cls: "bg-teal-500/15 text-teal-300 ring-teal-500/30" },
  remoteok: { label: "RemoteOK", cls: "bg-fuchsia-500/15 text-fuchsia-300 ring-fuchsia-500/30" },
  hn_hiring: { label: "HN hiring", cls: "bg-orange-500/15 text-orange-300 ring-orange-500/30" },
  linkedin_jobs: { label: "LinkedIn", cls: "bg-sky-500/15 text-sky-300 ring-sky-500/30" },
};

// Sources whose official API lets us place the bid from here (mirrors the backend's
// API_SUBMITTABLE). Upwork's ToS bans automated proposals; SAM has no submission API.
const API_SUBMITTABLE = new Set<OpportunitySource>(["freelancer"]);

// Bulk-pass threshold: undrafted rows under this fit are junk by definition —
// the scorer reserves <40 for out-of-scope work (see prompts/score_opportunity.md).
const BULK_PASS_FIT = 40;

function fitColor(score: number | null): string {
  if (score == null) return "text-neutral-500";
  if (score >= 80) return "text-emerald-400";
  if (score >= 65) return "text-lime-400";
  if (score >= 45) return "text-amber-400";
  return "text-neutral-500";
}

function deadlineLabel(iso: string | null): { text: string; urgent: boolean } | null {
  if (!iso) return null;
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return null;
  const days = Math.ceil(ms / 86_400_000);
  if (days < 0) return { text: "closed", urgent: true };
  if (days === 0) return { text: "due today", urgent: true };
  return { text: `${days}d left`, urgent: days <= 5 };
}

function amountFromEstPrice(estPrice: string | null): string {
  const m = (estPrice ?? "").replace(/,/g, "").match(/\d+(\.\d+)?/);
  return m ? m[0] : "";
}

type Bucket = "needs_approval" | "approved" | "submitted" | "low_fit";

function bucketOf(r: BidReviewRow): Bucket {
  if (r.bid?.status === "submitted") return "submitted";
  if (r.bid?.status === "approved") return "approved";
  if (r.bid) return "needs_approval";
  return "low_fit";
}

export function BidsClient({ initialRows }: { initialRows: BidReviewRow[] }) {
  const [rows, setRows] = useState<BidReviewRow[]>(initialRows);
  const [sourceFilter, setSourceFilter] = useState<OpportunitySource | "all">("all");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkNote, setBulkNote] = useState<string | null>(null);

  const sources = useMemo(() => {
    const s = new Set<OpportunitySource>();
    rows.forEach((r) => s.add(r.opportunity.source));
    return Array.from(s);
  }, [rows]);

  const visible = useMemo(
    () => (sourceFilter === "all" ? rows : rows.filter((r) => r.opportunity.source === sourceFilter)),
    [rows, sourceFilter],
  );
  const needsApproval = visible.filter((r) => bucketOf(r) === "needs_approval");
  const approved = visible.filter((r) => bucketOf(r) === "approved");
  const submitted = visible.filter((r) => bucketOf(r) === "submitted");
  const lowFit = visible.filter((r) => bucketOf(r) === "low_fit");

  function removeRow(oppId: string) {
    setRows((prev) => {
      const next = prev.filter((r) => r.opportunity.id !== oppId);
      if (sourceFilter !== "all" && !next.some((r) => r.opportunity.source === sourceFilter)) {
        setSourceFilter("all");
      }
      return next;
    });
  }

  // Approve keeps the row — it MOVES to the Approved section (and the server keeps
  // returning it), so a refresh shows exactly the same state.
  function markApproved(oppId: string) {
    setRows((prev) =>
      prev.map((r) =>
        r.opportunity.id === oppId && r.bid
          ? {
              opportunity: { ...r.opportunity, status: "approved" as const },
              bid: { ...r.bid, status: "approved" as const },
            }
          : r,
      ),
    );
  }

  // Mirrors the server-side bulk_pass guards: undecided, undrafted, fit below threshold.
  const isLowFit = (r: BidReviewRow) =>
    !r.bid &&
    (r.opportunity.status === "new" || r.opportunity.status === "scored") &&
    r.opportunity.fit_score != null &&
    r.opportunity.fit_score < BULK_PASS_FIT;
  const lowFitCount = rows.filter(isLowFit).length;

  async function bulkPass() {
    const ids = rows.filter(isLowFit).map((r) => r.opportunity.id);
    if (ids.length === 0) return;
    if (!window.confirm(`Pass ${ids.length} low-fit opportunities (fit < ${BULK_PASS_FIT})?`)) return;
    setBulkBusy(true);
    setBulkNote(null);
    try {
      const res = await fetch("/api/bids", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "bulk_pass", max_fit: BULK_PASS_FIT, opportunity_ids: ids }),
      });
      const data = (await res.json()) as { persisted?: boolean; passed?: number; error?: string; reason?: string };
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      const removed = new Set(ids);
      setRows((prev) => {
        const next = prev.filter((r) => !removed.has(r.opportunity.id));
        if (sourceFilter !== "all" && !next.some((r) => r.opportunity.source === sourceFilter)) {
          setSourceFilter("all");
        }
        return next;
      });
      setBulkNote(
        data.persisted === false ? `cleared locally (${data.reason ?? "mock mode"})` : `passed ${data.passed ?? ids.length}`,
      );
    } catch (err) {
      setBulkNote(`error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBulkBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-white">Bids</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Software / AI-agent work discovered across SAM.gov, Upwork, Freelancer, RemoteOK, HN and
          LinkedIn — fit-scored, with drafted proposals. Freelancer bids submit from here via
          their official API; other platforms you submit by hand and mark submitted.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <FilterChip active={sourceFilter === "all"} onClick={() => setSourceFilter("all")}>
          All ({rows.length})
        </FilterChip>
        {sources.map((s) => (
          <FilterChip key={s} active={sourceFilter === s} onClick={() => setSourceFilter(s)}>
            {SOURCE_META[s]?.label ?? s} ({rows.filter((r) => r.opportunity.source === s).length})
          </FilterChip>
        ))}
        {lowFitCount > 0 && (
          <button
            onClick={bulkPass}
            disabled={bulkBusy}
            className="ml-auto rounded-md bg-neutral-900 px-3 py-1 text-xs font-medium text-red-300 ring-1 ring-red-500/30 transition hover:bg-red-500/10 disabled:opacity-40"
          >
            {bulkBusy ? "…" : `Pass ${lowFitCount} low-fit (<${BULK_PASS_FIT})`}
          </button>
        )}
        {bulkNote && <span className="text-xs text-neutral-400">{bulkNote}</span>}
      </div>

      {visible.length === 0 ? (
        <div className="rounded-lg border border-dashed border-neutral-800 px-6 py-16 text-center text-sm text-neutral-500">
          No opportunities in the queue. The daily sweep drafts new bids as it finds
          high-fit work — or run one now with{" "}
          <code className="text-neutral-400">scripts.sweep_opportunities</code>.
        </div>
      ) : (
        <div className="space-y-8">
          <Section
            title="Needs approval"
            hint="Drafted proposals awaiting your decision"
            count={needsApproval.length}
            accent="text-amber-300"
          >
            {needsApproval.map((row) => (
              <BidCard key={row.opportunity.id} row={row} onApproved={markApproved} onRemoved={removeRow} />
            ))}
          </Section>
          <Section
            title="Approved — ready to submit"
            hint="Freelancer submits from here; other platforms: submit on the portal, then mark submitted"
            count={approved.length}
            accent="text-emerald-300"
          >
            {approved.map((row) => (
              <BidCard key={row.opportunity.id} row={row} onApproved={markApproved} onRemoved={removeRow} />
            ))}
          </Section>
          <Section
            title="Submitted — awaiting response"
            hint="Freelancer outcomes auto-track hourly (you're emailed on an award); mark the rest won/lost as replies come in"
            count={submitted.length}
            accent="text-sky-300"
          >
            {submitted.map((row) => (
              <BidCard key={row.opportunity.id} row={row} onApproved={markApproved} onRemoved={removeRow} />
            ))}
          </Section>
          <Section
            title="Low fit — no bid drafted"
            hint="Scored below the draft gate; pass them or pursue by hand"
            count={lowFit.length}
            accent="text-neutral-400"
          >
            {lowFit.map((row) => (
              <BidCard key={row.opportunity.id} row={row} onApproved={markApproved} onRemoved={removeRow} />
            ))}
          </Section>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  hint,
  count,
  accent,
  children,
}: {
  title: string;
  hint: string;
  count: number;
  accent: string;
  children: React.ReactNode;
}) {
  if (count === 0) return null;
  return (
    <section>
      <div className="mb-3 flex items-baseline gap-2">
        <h2 className={`text-sm font-semibold uppercase tracking-wide ${accent}`}>{title}</h2>
        <span className="text-xs text-neutral-500">{count}</span>
        <span className="hidden text-xs text-neutral-600 sm:inline">— {hint}</span>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium ring-1 transition ${
        active
          ? "bg-white text-neutral-900 ring-white"
          : "bg-neutral-900 text-neutral-400 ring-neutral-800 hover:text-neutral-200"
      }`}
    >
      {children}
    </button>
  );
}

function BidCard({
  row,
  onApproved,
  onRemoved,
}: {
  row: BidReviewRow;
  onApproved: (oppId: string) => void;
  onRemoved: (oppId: string) => void;
}) {
  const { opportunity: o, bid } = row;
  const meta = SOURCE_META[o.source] ?? {
    label: o.source,
    cls: "bg-neutral-500/15 text-neutral-300 ring-neutral-500/30",
  };
  const dl = deadlineLabel(o.deadline);
  const flags = o.fit_flags ?? {};
  const isApproved = bid?.status === "approved";
  const isSubmitted = bid?.status === "submitted";
  const canApiSubmit = isApproved && API_SUBMITTABLE.has(o.source);

  const [body, setBody] = useState(bid?.edited_body ?? bid?.body ?? "");
  const [savedBody, setSavedBody] = useState(bid?.edited_body ?? bid?.body ?? "");
  const [amount, setAmount] = useState(() => amountFromEstPrice(bid?.est_price ?? null));
  const [busy, setBusy] = useState<Action | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const dirty = bid ? body !== savedBody : false;

  async function act(action: Action) {
    if (action === "submit_api" && (!amount || Number(amount) <= 0)) {
      setNote("enter a bid amount first");
      return;
    }
    setBusy(action);
    setNote(null);
    try {
      const res = await fetch("/api/bids", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          opportunity_id: o.id,
          bid_id: bid?.id ?? null,
          action,
          edited_body: body || null,
          amount: action === "submit_api" ? Number(amount) : null,
          period_days: action === "submit_api" ? 7 : null,
        }),
      });
      const data = (await res.json()) as {
        persisted?: boolean;
        submitted?: boolean;
        reason?: string;
        error?: string;
      };
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      if (action === "save") {
        setNote(data.persisted === false ? `saved (${data.reason ?? "no-op"})` : "saved");
        setSavedBody(body);
      } else if (action === "approve") {
        setSavedBody(body);
        onApproved(o.id);
      } else {
        onRemoved(o.id); // reject / pass / submit / submit_api / won / lost clear the row
      }
    } catch (err) {
      setNote(`error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(body);
      setNote("copied to clipboard");
    } catch {
      setNote("couldn't copy");
    }
  }

  return (
    <article className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-5">
      {/* header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${meta.cls}`}>
              {meta.label}
            </span>
            {flags.is_ai_agent && (
              <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-violet-500/30 bg-violet-500/15 text-violet-300">
                AI agent
              </span>
            )}
            {o.set_aside && (
              <span className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-300 ring-1 ring-neutral-700">
                {o.set_aside}
              </span>
            )}
            {dl && (
              <span className={`text-[11px] font-medium ${dl.urgent ? "text-red-400" : "text-neutral-400"}`}>
                {dl.text}
              </span>
            )}
          </div>
          <h2 className="truncate text-base font-semibold text-white">
            {o.url ? (
              <a href={o.url} target="_blank" rel="noreferrer" className="hover:underline">
                {o.title}
              </a>
            ) : (
              o.title
            )}
          </h2>
          <p className="mt-0.5 truncate text-sm text-neutral-400">
            {[o.org, o.location, o.budget].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className={`text-2xl font-bold tabular-nums ${fitColor(o.fit_score)}`}>
            {o.fit_score ?? "—"}
          </div>
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">fit</div>
        </div>
      </div>

      {/* fit rationale */}
      {o.fit_rationale && (
        <p className="mt-3 rounded-md bg-neutral-950/60 px-3 py-2 text-sm text-neutral-300">
          {o.fit_rationale}
        </p>
      )}
      {(o.naics || o.psc) && (
        <p className="mt-2 text-[11px] text-neutral-500">
          {o.naics && <>NAICS {o.naics}</>} {o.psc && <>· PSC {o.psc}</>}
        </p>
      )}

      {/* bid */}
      {bid ? (
        <div className="mt-4">
          {bid.summary && <p className="mb-2 text-sm font-medium text-neutral-200">{bid.summary}</p>}
          {bid.est_price && (
            <p className="mb-2 text-xs text-neutral-400">
              Suggested: <span className="text-neutral-200">{bid.est_price}</span>
            </p>
          )}
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            disabled={isSubmitted}
            rows={isSubmitted ? 4 : Math.min(16, Math.max(6, body.split("\n").length + 1))}
            className="w-full resize-y rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-[13px] leading-relaxed text-neutral-100 outline-none focus:border-neutral-600 disabled:opacity-60"
          />
          {isSubmitted && (
            <p className="mt-2 text-xs text-neutral-400">
              Submitted {bid.submitted_at ? new Date(bid.submitted_at).toLocaleDateString() : ""}
              {bid.submitted_via === "api" ? " via API" : ""}
              {API_SUBMITTABLE.has(o.source)
                ? " — outcome auto-tracks hourly; you'll be emailed if awarded."
                : " — mark the outcome when they respond."}
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {isSubmitted && (
              <>
                <ActionBtn tone="primary" busy={busy === "won"} onClick={() => act("won")}>
                  Won 🎉
                </ActionBtn>
                <ActionBtn tone="danger" busy={busy === "lost"} onClick={() => act("lost")}>
                  Lost
                </ActionBtn>
              </>
            )}
            {!isApproved && !isSubmitted && (
              <ActionBtn tone="primary" busy={busy === "approve"} onClick={() => act("approve")}>
                Approve
              </ActionBtn>
            )}
            {canApiSubmit && (
              <span className="flex items-center gap-1.5">
                <span className="text-xs text-neutral-400">$</span>
                <input
                  value={amount}
                  onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
                  inputMode="decimal"
                  placeholder="amount"
                  className="w-24 rounded-md border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100 outline-none focus:border-neutral-600"
                />
                <ActionBtn tone="primary" busy={busy === "submit_api"} onClick={() => act("submit_api")}>
                  Submit on {meta.label}
                </ActionBtn>
              </span>
            )}
            {isApproved && (
              <ActionBtn tone="ghost" busy={busy === "submit"} onClick={() => act("submit")}>
                Mark submitted
              </ActionBtn>
            )}
            {!isSubmitted && (
              <ActionBtn tone="ghost" busy={busy === "save"} disabled={!dirty} onClick={() => act("save")}>
                {dirty ? "Save edits" : "Saved"}
              </ActionBtn>
            )}
            <ActionBtn tone="ghost" onClick={copy}>
              Copy
            </ActionBtn>
            {!isSubmitted && (
              <ActionBtn tone="danger" busy={busy === "reject"} onClick={() => act("reject")}>
                Reject
              </ActionBtn>
            )}
            {o.url && (
              <a
                href={o.url}
                target="_blank"
                rel="noreferrer"
                className="ml-auto text-xs text-neutral-400 hover:text-neutral-200"
              >
                Open posting ↗
              </a>
            )}
          </div>
        </div>
      ) : (
        <div className="mt-4 flex items-center gap-2">
          <span className="text-sm text-neutral-500">
            Scored, no bid drafted{" "}
            {flags.is_software === false ? "(not software)" : flags.eligible === false ? "(not eligible)" : ""}.
          </span>
          <ActionBtn tone="danger" busy={busy === "pass"} onClick={() => act("pass")}>
            Pass
          </ActionBtn>
          {o.url && (
            <a
              href={o.url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto text-xs text-neutral-400 hover:text-neutral-200"
            >
              Open posting ↗
            </a>
          )}
        </div>
      )}

      {note && <p className="mt-2 text-xs text-neutral-400">{note}</p>}
    </article>
  );
}

function ActionBtn({
  children,
  onClick,
  tone,
  busy,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  tone: "primary" | "ghost" | "danger";
  busy?: boolean;
  disabled?: boolean;
}) {
  const cls =
    tone === "primary"
      ? "bg-white text-neutral-900 hover:bg-neutral-200"
      : tone === "danger"
        ? "bg-neutral-900 text-red-300 ring-1 ring-red-500/30 hover:bg-red-500/10"
        : "bg-neutral-900 text-neutral-300 ring-1 ring-neutral-800 hover:text-white";
  return (
    <button
      onClick={onClick}
      disabled={busy || disabled}
      className={`rounded-md px-3 py-1.5 text-xs font-medium transition disabled:opacity-40 ${cls}`}
    >
      {busy ? "…" : children}
    </button>
  );
}
