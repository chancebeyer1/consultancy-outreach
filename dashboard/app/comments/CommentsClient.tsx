"use client";

import clsx from "clsx";
import { useRouter } from "next/navigation";
import { useState } from "react";

export type CommentItem = {
  id: string;
  social_id: string;
  post_url: string | null;
  author_name: string | null;
  author_headline: string | null;
  post_excerpt: string | null;
  reactions: number;
  comments: number;
  keyword: string | null;
  body: string;
  status: string;
  error: string | null;
  approved_at: string | null;
  posted_at: string | null;
  created_at: string | null;
};

export function CommentsClient({ items }: { items: CommentItem[] }) {
  const router = useRouter();
  const pending = items.filter((i) => i.status === "pending");
  const approved = items.filter((i) => i.status === "approved");
  const failed = items.filter((i) => i.status === "failed");
  const posted = items.filter((i) => i.status === "posted");
  const [busyAll, setBusyAll] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function approveAll() {
    setBusyAll(true);
    setMsg(null);
    try {
      const res = await fetch("/api/comments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "approve_all" }),
      });
      const data = await res.json().catch(() => ({}) as { error?: string });
      if (!res.ok) throw new Error(data.error || "failed");
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "failed");
    } finally {
      setBusyAll(false);
    }
  }

  return (
    <div className="space-y-8">
      <HowItWorks />

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">
            Needs approval{" "}
            {pending.length > 0 && <span className="text-amber-400">· {pending.length}</span>}
          </h2>
          {pending.length > 1 && (
            <button
              onClick={approveAll}
              disabled={busyAll}
              className="rounded-md bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {busyAll ? "Approving…" : `Approve all ${pending.length}`}
            </button>
          )}
        </div>
        {msg && <p className="mb-2 text-xs text-red-400">{msg}</p>}
        {pending.length === 0 ? (
          <p className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-6 text-center text-sm italic text-neutral-600">
            Nothing waiting. Fresh posts to comment on are queued each weekday morning.
          </p>
        ) : (
          <div className="space-y-3">
            {pending.map((i) => (
              <Card key={i.id} item={i} editable />
            ))}
          </div>
        )}
      </section>

      {approved.length > 0 && (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            Scheduled — posting through the day <span className="text-sky-400">· {approved.length}</span>
          </h2>
          <div className="space-y-3">
            {approved.map((i) => (
              <Card key={i.id} item={i} />
            ))}
          </div>
        </section>
      )}

      {failed.length > 0 && (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            Failed <span className="text-red-400">· {failed.length}</span>
          </h2>
          <div className="space-y-3">
            {failed.map((i) => (
              <Card key={i.id} item={i} />
            ))}
          </div>
        </section>
      )}

      {posted.length > 0 && (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-400">Posted</h2>
          <div className="space-y-3">
            {posted.map((i) => (
              <Card key={i.id} item={i} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function HowItWorks() {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <h2 className="text-sm font-semibold text-neutral-200">How growth comments work</h2>
      <ol className="mt-2 space-y-1.5 text-[13px] leading-relaxed text-neutral-400">
        <li>
          <span className="font-medium text-neutral-300">1.</span> Each weekday morning the system
          finds big posts in your niche that are pulling engagement, and drafts a comment for each —
          in your voice.
        </li>
        <li>
          <span className="font-medium text-neutral-300">2.</span> You review and approve the ones
          you like (edit any first). One click each, or approve them all.
        </li>
        <li>
          <span className="font-medium text-neutral-300">3.</span> Approved comments post{" "}
          <span className="text-neutral-300">automatically, one at a time, spread across the
          afternoon</span>{" "}
          — weekday business hours only, with random gaps. Never a burst, so LinkedIn reads it as
          human.
        </li>
      </ol>
    </div>
  );
}

function Card({ item, editable = false }: { item: CommentItem; editable?: boolean }) {
  const router = useRouter();
  const [body, setBody] = useState(item.body);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const dirty = body !== item.body;

  async function act(action: "approve" | "save" | "dismiss" | "retry") {
    setBusy(action);
    setMsg(null);
    try {
      const res = await fetch("/api/comments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: item.id, action, body }),
      });
      const data = await res.json().catch(() => ({}) as { error?: string });
      if (!res.ok) throw new Error(data.error || "failed");
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-neutral-200">
            {item.author_name || "LinkedIn author"}
          </div>
          {item.author_headline && (
            <div className="truncate text-[12px] text-neutral-500">{item.author_headline}</div>
          )}
          <div className="mt-0.5 text-[11px] text-neutral-600">
            {item.reactions} reactions · {item.comments} comments
            {item.keyword && (
              <>
                {" · "}
                <span className="text-neutral-500">{item.keyword}</span>
              </>
            )}
          </div>
        </div>
        <StatusBadge status={item.status} />
      </div>

      {item.post_excerpt && (
        <div className="mb-3 rounded border border-neutral-800 bg-neutral-900/50 px-3 py-2 text-[12px] leading-relaxed text-neutral-400">
          <span className="text-neutral-600">Their post: </span>
          {item.post_excerpt}…
          {item.post_url && (
            <>
              {" "}
              <a
                href={item.post_url}
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline"
              >
                open →
              </a>
            </>
          )}
        </div>
      )}

      <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">Your comment</div>
      {editable ? (
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={Math.max(3, Math.ceil(body.length / 70))}
          className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 p-3 text-sm leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
        />
      ) : (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-300">{item.body}</p>
      )}

      {item.error && (
        <p className="mt-2 rounded border border-red-900/60 bg-red-950/30 px-2 py-1 text-xs text-red-300">
          {item.error}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {editable && (
          <>
            <button
              onClick={() => act("approve")}
              disabled={!!busy}
              className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            >
              {busy === "approve" ? "Approving…" : "Approve"}
            </button>
            <button
              onClick={() => act("save")}
              disabled={!!busy || !dirty}
              className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
            >
              {busy === "save" ? "Saving…" : "Save edits"}
            </button>
            <button
              onClick={() => act("dismiss")}
              disabled={!!busy}
              className="rounded-md px-3 py-1.5 text-xs text-neutral-500 hover:text-neutral-300 disabled:opacity-40"
            >
              Dismiss
            </button>
          </>
        )}
        {item.status === "approved" && (
          <>
            <span className="text-[11px] text-neutral-500">Will post at the next good time.</span>
            <button
              onClick={() => act("dismiss")}
              disabled={!!busy}
              className="ml-auto rounded-md px-3 py-1.5 text-xs text-neutral-500 hover:text-red-300 disabled:opacity-40"
            >
              {busy === "dismiss" ? "Cancelling…" : "Cancel"}
            </button>
          </>
        )}
        {item.status === "failed" && (
          <button
            onClick={() => act("retry")}
            disabled={!!busy}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
          >
            {busy === "retry" ? "Requeuing…" : "Retry"}
          </button>
        )}
        {item.status === "posted" && (
          <>
            {item.post_url && (
              <a
                href={item.post_url}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-sky-400 hover:underline"
              >
                view on LinkedIn →
              </a>
            )}
            {item.posted_at && (
              <span className="text-[11px] text-neutral-600">Posted {rel(item.posted_at)}</span>
            )}
          </>
        )}
        {msg && <span className="text-xs text-red-400">{msg}</span>}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending: "border-amber-800 bg-amber-950 text-amber-300",
    approved: "border-sky-800 bg-sky-950 text-sky-300",
    posted: "border-emerald-800 bg-emerald-950 text-emerald-300",
    failed: "border-red-800 bg-red-950 text-red-300",
  };
  const label =
    status === "pending" ? "needs approval" : status === "approved" ? "scheduled" : status;
  return (
    <span
      className={clsx(
        "shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase",
        map[status] ?? "border-neutral-700 bg-neutral-900 text-neutral-400",
      )}
    >
      {label}
    </span>
  );
}

function rel(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
