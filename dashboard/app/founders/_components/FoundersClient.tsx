"use client";

import { useMemo, useState } from "react";

import type { FoundersPageResult } from "@/lib/queries";
import type { FounderPostKind, FounderPostStatus, FounderReviewRow, FounderVenueKind } from "@/lib/types";

type Action = "save" | "approve" | "skip" | "posted" | "respond";

const VENUE_KIND_META: Record<FounderVenueKind, { label: string; cls: string }> = {
  cofounder_matching: { label: "Co-founder matching", cls: "bg-violet-500/15 text-violet-300 ring-violet-500/30" },
  community: { label: "Community", cls: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30" },
  forum: { label: "Forum", cls: "bg-orange-500/15 text-orange-300 ring-orange-500/30" },
  subreddit: { label: "Subreddit", cls: "bg-sky-500/15 text-sky-300 ring-sky-500/30" },
};

const POST_KIND_META: Record<FounderPostKind, { label: string; cls: string }> = {
  venue_post: { label: "Venue post", cls: "bg-neutral-500/15 text-neutral-300 ring-neutral-500/30" },
  profile_copy: { label: "Profile copy", cls: "bg-fuchsia-500/15 text-fuchsia-300 ring-fuchsia-500/30" },
  reachout_dm: { label: "DM reachout", cls: "bg-teal-500/15 text-teal-300 ring-teal-500/30" },
  comment_reply: { label: "Comment reply", cls: "bg-amber-500/15 text-amber-300 ring-amber-500/30" },
};

type Bucket = "needs_review" | "ready" | "posted" | "replied";

// skipped rows never render (like passed bids); everything else buckets by status.
function bucketOf(r: FounderReviewRow): Bucket | null {
  switch (r.post.status) {
    case "draft":
      return "needs_review";
    case "approved":
      return "ready";
    case "posted":
      return "posted";
    case "replied":
      return "replied";
    default:
      return null;
  }
}

const STATUS_FILTERS: { value: FounderPostStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "approved", label: "Approved" },
  { value: "posted", label: "Posted" },
  { value: "replied", label: "Replied" },
];

export function FoundersClient({ rows: initialRows, campaigns }: FoundersPageResult) {
  const [rows, setRows] = useState<FounderReviewRow[]>(initialRows);
  const [campaignFilter, setCampaignFilter] = useState<string>("all");
  const [venueFilter, setVenueFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<FounderPostStatus | "all">("all");

  const venues = useMemo(() => {
    const seen = new Map<string, string>(); // slug → name
    rows.forEach((r) => seen.set(r.venue.slug, r.venue.name));
    return Array.from(seen.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [rows]);

  const visible = useMemo(
    () =>
      rows.filter(
        (r) =>
          bucketOf(r) !== null &&
          (campaignFilter === "all" || r.post.campaign_slug === campaignFilter) &&
          (venueFilter === "all" || r.venue.slug === venueFilter) &&
          (statusFilter === "all" || r.post.status === statusFilter),
      ),
    [rows, campaignFilter, venueFilter, statusFilter],
  );
  const needsReview = visible.filter((r) => bucketOf(r) === "needs_review");
  const ready = visible.filter((r) => bucketOf(r) === "ready");
  const posted = visible.filter((r) => bucketOf(r) === "posted");
  const replied = visible.filter((r) => bucketOf(r) === "replied");

  function patchRow(postId: string, patch: Partial<FounderReviewRow["post"]>) {
    setRows((prev) =>
      prev.map((r) => (r.post.id === postId ? { ...r, post: { ...r.post, ...patch } } : r)),
    );
  }

  function removeRow(postId: string) {
    setRows((prev) => prev.filter((r) => r.post.id !== postId));
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-white">Founders</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Co-founder / operating-partner / distribution-partner copy — venue posts, YC-CFM
          profile sections, and reachouts drafted per campaign. Review, edit, approve, then
          paste on the venue yourself and mark it posted. Nothing is ever auto-posted — a
          human pastes every post and sends every reachout.
        </p>
      </header>

      <div className="mb-6 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip active={campaignFilter === "all"} onClick={() => setCampaignFilter("all")}>
            All campaigns ({rows.filter((r) => bucketOf(r) !== null).length})
          </FilterChip>
          {campaigns.map((c) => (
            <FilterChip key={c} active={campaignFilter === c} onClick={() => setCampaignFilter(c)}>
              {c} ({rows.filter((r) => r.post.campaign_slug === c && bucketOf(r) !== null).length})
            </FilterChip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterChip active={venueFilter === "all"} onClick={() => setVenueFilter("all")}>
            All venues
          </FilterChip>
          {venues.map(([slug, name]) => (
            <FilterChip key={slug} active={venueFilter === slug} onClick={() => setVenueFilter(slug)}>
              {name}
            </FilterChip>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {STATUS_FILTERS.map((s) => (
            <FilterChip
              key={s.value}
              active={statusFilter === s.value}
              onClick={() => setStatusFilter(s.value)}
            >
              {s.label}
            </FilterChip>
          ))}
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-lg border border-dashed border-neutral-800 px-6 py-16 text-center text-sm text-neutral-500">
          Nothing in the queue. The daily leg drafts venue posts and reachouts for every
          campaign with <code className="text-neutral-400">founder_search = true</code> — or run
          one now with <code className="text-neutral-400">scripts.founders draft</code> /{" "}
          <code className="text-neutral-400">scripts.founders sweep</code>.
        </div>
      ) : (
        <div className="space-y-8">
          <Section
            title="Needs review"
            hint="Drafted copy awaiting your call"
            count={needsReview.length}
            accent="text-amber-300"
          >
            {needsReview.map((row) => (
              <FounderCard key={row.post.id} row={row} onPatched={patchRow} onRemoved={removeRow} />
            ))}
          </Section>
          <Section
            title="Approved — ready to paste"
            hint="Open the venue, paste the copy by hand, then mark posted"
            count={ready.length}
            accent="text-emerald-300"
          >
            {ready.map((row) => (
              <FounderCard key={row.post.id} row={row} onPatched={patchRow} onRemoved={removeRow} />
            ))}
          </Section>
          <Section
            title="Posted — awaiting response"
            hint="Log responses as they come in (free text)"
            count={posted.length}
            accent="text-sky-300"
          >
            {posted.map((row) => (
              <FounderCard key={row.post.id} row={row} onPatched={patchRow} onRemoved={removeRow} />
            ))}
          </Section>
          <Section
            title="Replied — response logged"
            hint="Conversations in flight; continue them on the venue"
            count={replied.length}
            accent="text-violet-300"
          >
            {replied.map((row) => (
              <FounderCard key={row.post.id} row={row} onPatched={patchRow} onRemoved={removeRow} />
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
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
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

function FounderCard({
  row,
  onPatched,
  onRemoved,
}: {
  row: FounderReviewRow;
  onPatched: (postId: string, patch: Partial<FounderReviewRow["post"]>) => void;
  onRemoved: (postId: string) => void;
}) {
  const { post, venue } = row;
  const venueMeta = VENUE_KIND_META[venue.kind] ?? {
    label: venue.kind,
    cls: "bg-neutral-500/15 text-neutral-300 ring-neutral-500/30",
  };
  const kindMeta = POST_KIND_META[post.kind] ?? {
    label: post.kind,
    cls: "bg-neutral-500/15 text-neutral-300 ring-neutral-500/30",
  };
  const isDraft = post.status === "draft";
  const isApproved = post.status === "approved";
  const isPosted = post.status === "posted";
  const isReplied = post.status === "replied";
  const editable = isDraft || isApproved;

  const [title, setTitle] = useState(post.title ?? "");
  const [body, setBody] = useState(post.body);
  const [savedBody, setSavedBody] = useState(post.body);
  const [savedTitle, setSavedTitle] = useState(post.title ?? "");
  const [response, setResponse] = useState("");
  const [busy, setBusy] = useState<Action | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const dirty = body !== savedBody || title !== savedTitle;

  async function act(action: Action) {
    if (action === "respond" && !response.trim()) {
      setNote("write what they said first");
      return;
    }
    setBusy(action);
    setNote(null);
    try {
      const res = await fetch("/api/founders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          post_id: post.id,
          action,
          body: editable ? body : null,
          title: editable ? title : null,
          response_summary: action === "respond" ? response.trim() : null,
        }),
      });
      const data = (await res.json()) as { persisted?: boolean; reason?: string; error?: string };
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      if (action === "save") {
        setSavedBody(body);
        setSavedTitle(title);
        setNote(data.persisted === false ? `saved (${data.reason ?? "no-op"})` : "saved");
      } else if (action === "approve") {
        setSavedBody(body);
        setSavedTitle(title);
        onPatched(post.id, { status: "approved", body, title: title || null });
      } else if (action === "posted") {
        setSavedBody(body);
        setSavedTitle(title);
        onPatched(post.id, {
          status: "posted",
          body,
          title: title || null,
          posted_at: new Date().toISOString(),
        });
      } else if (action === "respond") {
        onPatched(post.id, { status: "replied", response_summary: response.trim() });
      } else {
        onRemoved(post.id); // skip clears the row
      }
    } catch (err) {
      setNote(`error: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(title ? `${title}\n\n${body}` : body);
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
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${venueMeta.cls}`}>
              {venue.name}
            </span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${kindMeta.cls}`}>
              {kindMeta.label}
            </span>
            <span className="rounded px-1.5 py-0.5 text-[10px] font-medium text-neutral-300 ring-1 ring-neutral-700">
              {post.campaign_slug}
            </span>
            {isPosted && post.posted_at && (
              <span className="text-[11px] font-medium text-neutral-400">
                posted {new Date(post.posted_at).toLocaleDateString()}
              </span>
            )}
          </div>
          {editable ? (
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="(no title — profile copy / reply)"
              className="w-full rounded-md border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-base font-semibold text-white outline-none placeholder:font-normal placeholder:text-neutral-600 focus:border-neutral-600"
            />
          ) : (
            <h2 className="truncate text-base font-semibold text-white">
              {post.title || `${venue.name} ${kindMeta.label.toLowerCase()}`}
            </h2>
          )}
          {post.target_url && (
            <p className="mt-0.5 truncate text-sm text-neutral-400">
              in reply to{" "}
              <a
                href={post.target_url}
                target="_blank"
                rel="noreferrer"
                className="text-sky-300 hover:underline"
              >
                {post.target_url}
              </a>
            </p>
          )}
        </div>
      </div>

      {/* fit note */}
      {post.fit_note && (
        <p className="mt-3 rounded-md bg-neutral-950/60 px-3 py-2 text-sm text-neutral-300">
          {post.fit_note}
        </p>
      )}

      {/* where + how to paste — the human is the transport */}
      <div className="mt-3 rounded-md border border-dashed border-neutral-800 px-3 py-2 text-xs text-neutral-400">
        <span className="font-semibold uppercase tracking-wide text-neutral-500">Post it here: </span>
        {venue.url ? (
          <a href={venue.url} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline">
            {venue.url}
          </a>
        ) : (
          venue.name
        )}
        {venue.posting_rules && <span className="block pt-1">{venue.posting_rules}</span>}
      </div>

      {/* body */}
      <div className="mt-4">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          disabled={!editable}
          rows={editable ? Math.min(18, Math.max(6, body.split("\n").length + 1)) : 4}
          className="w-full resize-y rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 font-mono text-[13px] leading-relaxed text-neutral-100 outline-none focus:border-neutral-600 disabled:opacity-60"
        />
        {isReplied && post.response_summary && (
          <p className="mt-2 rounded-md bg-violet-500/10 px-3 py-2 text-sm text-violet-200">
            Response: {post.response_summary}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {isDraft && (
            <ActionBtn tone="primary" busy={busy === "approve"} onClick={() => act("approve")}>
              Approve
            </ActionBtn>
          )}
          {isApproved && (
            <ActionBtn tone="primary" busy={busy === "posted"} onClick={() => act("posted")}>
              Mark posted
            </ActionBtn>
          )}
          {editable && (
            <ActionBtn tone="ghost" busy={busy === "save"} disabled={!dirty} onClick={() => act("save")}>
              {dirty ? "Save edits" : "Saved"}
            </ActionBtn>
          )}
          <ActionBtn tone="ghost" onClick={copy}>
            Copy
          </ActionBtn>
          {(isDraft || isApproved) && (
            <ActionBtn tone="danger" busy={busy === "skip"} onClick={() => act("skip")}>
              Skip
            </ActionBtn>
          )}
          {isPosted && (
            <span className="flex min-w-0 flex-1 items-center gap-1.5">
              <input
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                placeholder="what did they say?"
                className="min-w-0 flex-1 rounded-md border border-neutral-800 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100 outline-none focus:border-neutral-600"
              />
              <ActionBtn tone="primary" busy={busy === "respond"} onClick={() => act("respond")}>
                Log response
              </ActionBtn>
            </span>
          )}
        </div>
      </div>

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
