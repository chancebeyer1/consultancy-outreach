"use client";

import clsx from "clsx";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

export type MediaImage = {
  kind?: string | null; // "photo" | "video" | "gif"
  mime?: string | null; // e.g. "image/jpeg"
  b64: string; // base64 image bytes
  video_url?: string | null; // playable mp4 for video/gif (dashboard "watch" link only)
};

export type ContentPost = {
  id: string;
  source_title: string | null;
  source_url: string | null;
  discussion_url: string | null;
  body: string;
  format: string | null;
  image_idea: string | null;
  card_image: string | null;
  // Original-tweet attachments, published after the text card as a multi-image carousel.
  media_images: MediaImage[] | null;
  status: string;
  external_id: string | null;
  error: string | null;
  created_at: string | null;
  posted_at: string | null;
};

export type BlogStats = { count: number; last: string | null; slug: string | null };

export function ContentClient({
  drafts,
  recent,
  page = 1,
  totalPages = 1,
  recentTotal = 0,
  autoBlog = false,
  blogStats = { count: 0, last: null, slug: null },
}: {
  drafts: ContentPost[];
  recent: ContentPost[];
  page?: number;
  totalPages?: number;
  recentTotal?: number;
  autoBlog?: boolean;
  blogStats?: BlogStats;
}) {
  return (
    <div className="space-y-8">
      <GeneratePanel />
      <AutoBlogPanel initialOn={autoBlog} stats={blogStats} />
      {/* Drafts are the actionable queue — always shown in full, never paginated. Only render this
          section on page 1 so paging through "Recent" doesn't repeat it. */}
      {page === 1 && (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            Needs review {drafts.length > 0 && <span className="text-amber-400">· {drafts.length}</span>}
          </h2>
          {drafts.length === 0 ? (
            <p className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-6 text-center text-sm italic text-neutral-600">
              No drafts waiting. Pick a variant above and generate one — nothing is drafted automatically.
            </p>
          ) : (
            <div className="space-y-3">
              {drafts.map((p) => (
                <Card key={p.id} post={p} editable />
              ))}
            </div>
          )}
        </section>
      )}

      {(recent.length > 0 || page > 1) && (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-400">
            Recent {recentTotal > 0 && <span className="text-neutral-600">· {recentTotal}</span>}
          </h2>
          {recent.length === 0 ? (
            <p className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-6 text-center text-sm italic text-neutral-600">
              Nothing on this page.
            </p>
          ) : (
            <div className="space-y-3">
              {recent.map((p) => (
                <Card key={p.id} post={p} />
              ))}
            </div>
          )}
          <Pager page={page} totalPages={totalPages} />
        </section>
      )}
    </div>
  );
}

// Prev/Next pagination for the Recent list. Uses <Link> (scroll:false keeps you in place while the
// server swaps the page in) so the global TopLoader fires on click for instant feedback.
function Pager({ page, totalPages }: { page: number; totalPages: number }) {
  if (totalPages <= 1) return null;
  const btn =
    "rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800";
  const disabled = "pointer-events-none opacity-40";
  return (
    <div className="mt-4 flex items-center justify-between">
      <Link
        href={`/content?page=${page - 1}`}
        scroll={false}
        aria-disabled={page <= 1}
        className={clsx(btn, page <= 1 && disabled)}
      >
        ← Newer
      </Link>
      <span className="text-[11px] text-neutral-500">
        Page {page} of {totalPages}
      </span>
      <Link
        href={`/content?page=${page + 1}`}
        scroll={false}
        aria-disabled={page >= totalPages}
        className={clsx(btn, page >= totalPages && disabled)}
      >
        Older →
      </Link>
    </div>
  );
}

type VariantKey = "news" | "build" | "tweet_reaction" | "tool_promo";

const VARIANTS: { key: VariantKey; label: string; blurb: string }[] = [
  { key: "news", label: "News reaction", blurb: "Drafts a post reacting to a fresh AI news story, in the angle you choose." },
  { key: "build", label: "Build-in-public", blurb: "Describe what you shipped and get a post in your voice — not a news reaction." },
  { key: "tweet_reaction", label: "Tweet reaction", blurb: "Pulls a high-engagement AI tweet, renders it as an image, and drafts your take around it." },
  { key: "tool_promo", label: "Promote a tool", blurb: "A value-first post that points readers at one of your free tools — distribution you own." },
];

const TOOL_OPTIONS: { key: string; label: string }[] = [
  { key: "audit", label: "AI Opportunity Audit" },
  { key: "roi", label: "AI Agent ROI Calculator" },
  { key: "roast", label: "Roast My Cold Outreach" },
];

const POST_FORMATS: { key: string; label: string }[] = [
  { key: "", label: "Auto (let it pick)" },
  { key: "contrarian", label: "Contrarian take" },
  { key: "stat_hook", label: "Stat hook" },
  { key: "before_after", label: "Before / after" },
  { key: "breakdown", label: "Breakdown" },
  { key: "story", label: "Story" },
  { key: "listicle", label: "Listicle" },
  { key: "one_liner", label: "One-liner" },
];

function GeneratePanel() {
  const router = useRouter();
  const [variant, setVariant] = useState<VariantKey>("news");
  const [format, setFormat] = useState("");
  const [tool, setTool] = useState("audit");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const active = VARIANTS.find((v) => v.key === variant)!;

  async function generate() {
    if (variant === "build" && !text.trim()) {
      setMsg({ ok: false, text: "Describe what you shipped first." });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const payload: Record<string, unknown> = { action: variant };
      if (variant === "news" && format) payload.format = format;
      if (variant === "build") payload.text = text;
      if (variant === "tool_promo") payload.tool = tool;
      const res = await fetch("/api/content", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      // A timed-out/failed Vercel function returns a plain-text error page, not JSON — so parse
      // defensively instead of crashing with "Unexpected token".
      const data = await res.json().catch(() => ({}) as { error?: string; spawned?: boolean });
      if (!res.ok) throw new Error(data.error || `Generation failed (HTTP ${res.status}).`);
      if (variant === "build") setText("");
      setMsg({
        ok: true,
        text: data.spawned
          ? "Generating… it'll appear in Needs review below within a minute (refresh to check)."
          : "Draft created — see Needs review below.",
      });
      if (!data.spawned) router.refresh();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <h2 className="text-sm font-semibold text-neutral-200">Generate content</h2>
      <p className="text-[13px] text-neutral-500">
        Pick a variant and generate a draft on demand. Nothing is auto-posted — every draft waits
        for your review below.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {VARIANTS.map((v) => (
          <button
            key={v.key}
            onClick={() => {
              setVariant(v.key);
              setMsg(null);
            }}
            className={clsx(
              "rounded-full px-3 py-1 text-xs font-medium",
              variant === v.key
                ? "bg-neutral-200 text-neutral-900"
                : "border border-neutral-700 text-neutral-400 hover:bg-neutral-900",
            )}
          >
            {v.label}
          </button>
        ))}
      </div>

      <p className="mt-2 text-[12px] text-neutral-500">{active.blurb}</p>

      {variant === "news" && (
        <div className="mt-3">
          <label className="block text-[11px] uppercase tracking-wide text-neutral-500">
            Format / angle
          </label>
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value)}
            className="mt-1 w-full max-w-xs rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
          >
            {POST_FORMATS.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {variant === "tool_promo" && (
        <div className="mt-3">
          <label className="block text-[11px] uppercase tracking-wide text-neutral-500">
            Which tool
          </label>
          <select
            value={tool}
            onChange={(e) => setTool(e.target.value)}
            className="mt-1 w-full max-w-xs rounded-md border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
          >
            {TOOL_OPTIONS.map((t) => (
              <option key={t.key} value={t.key}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {variant === "build" && (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="What did you ship, and what was the interesting decision or lesson? Rough notes are fine."
          className="mt-3 w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 p-3 text-sm leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
        />
      )}

      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={generate}
          disabled={busy}
          className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {busy ? "Generating…" : "Generate draft"}
        </button>
        {msg && (
          <span className={`text-xs ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</span>
        )}
      </div>
    </div>
  );
}

function AutoBlogPanel({ initialOn, stats }: { initialOn: boolean; stats: BlogStats }) {
  const router = useRouter();
  const [on, setOn] = useState(initialOn);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function toggle() {
    const next = !on;
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/blog-settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      const data = await res.json().catch(() => ({}) as { error?: string });
      if (!res.ok) throw new Error(data.error || "failed");
      setOn(next);
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  const lastStr = stats.last ? new Date(stats.last).toLocaleDateString() : null;
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-neutral-200">Auto-publish daily AI blog</h2>
          <p className="text-[13px] text-neutral-500">
            Once a day, an agent writes a full SEO article from the latest AI news and publishes it
            to your site&apos;s blog — weaving in your tools + a booking CTA. Compounding SEO.
          </p>
        </div>
        <button
          type="button"
          onClick={toggle}
          disabled={busy}
          role="switch"
          aria-checked={on}
          className={clsx(
            "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
            on ? "bg-sky-500" : "bg-neutral-700",
          )}
        >
          <span
            className={clsx(
              "inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform",
              on ? "translate-x-6" : "translate-x-1",
            )}
          />
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-neutral-500">
        <span className={clsx("font-medium", on ? "text-sky-400" : "text-neutral-500")}>
          {on ? "On — a new post publishes daily" : "Off — nothing auto-publishes"}
        </span>
        <span>·</span>
        <span>{stats.count} published</span>
        {lastStr && <span>· last {lastStr}</span>}
        <a
          href="https://agentry.contentdrip.ai/blog"
          target="_blank"
          rel="noreferrer"
          className="text-sky-400 hover:underline"
        >
          view blog →
        </a>
      </div>
      {msg && <p className="mt-2 text-xs text-red-400">{msg}</p>}
    </div>
  );
}

function Card({ post, editable = false }: { post: ContentPost; editable?: boolean }) {
  const router = useRouter();
  const [body, setBody] = useState(post.body);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const dirty = body !== post.body;
  const words = body.trim() ? body.trim().split(/\s+/).length : 0;

  // What actually publishes to LinkedIn, in order: the text tweet card, then each original
  // attachment (photo, or video/GIF cover frame). Two or more become a multi-image carousel.
  const attachments: { src: string; label: string; video?: string | null }[] = [];
  if (post.card_image) {
    attachments.push({ src: `data:image/png;base64,${post.card_image}`, label: "Card" });
  }
  for (const m of post.media_images ?? []) {
    if (!m?.b64) continue;
    attachments.push({
      src: `data:${m.mime || "image/jpeg"};base64,${m.b64}`,
      label: m.kind === "video" ? "Video thumbnail" : m.kind === "gif" ? "GIF thumbnail" : "Photo",
      video: m.video_url ?? null,
    });
  }

  async function act(action: "approve" | "save" | "dismiss" | "retry") {
    setBusy(action);
    setMsg(null);
    try {
      const res = await fetch("/api/content", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: post.id, action, body }),
      });
      const data = await res.json();
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
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 text-[11px] text-neutral-500">
          <span className="uppercase tracking-wide text-neutral-600">From </span>
          {post.source_url || post.discussion_url ? (
            <a
              href={post.source_url || post.discussion_url || "#"}
              target="_blank"
              rel="noreferrer"
              className="text-sky-400 hover:underline"
            >
              {post.source_title || "source"}
            </a>
          ) : (
            <span className="text-neutral-400">{post.source_title}</span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {post.format && (
            <span className="rounded border border-neutral-700 bg-neutral-900 px-1.5 py-0.5 font-mono text-[10px] uppercase text-neutral-400">
              {post.format.replace(/_/g, " ")}
            </span>
          )}
          <StatusBadge status={post.status} />
        </div>
      </div>

      {editable ? (
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={Math.max(6, Math.ceil(body.length / 70))}
          className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 p-3 text-sm leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
        />
      ) : (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-neutral-300">{post.body}</p>
      )}

      {attachments.length > 0 && (
        <div className="mt-3">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">
            LinkedIn images
            {attachments.length > 1 && (
              <span className="text-neutral-600"> · {attachments.length} (carousel)</span>
            )}
          </div>
          <div className="flex flex-wrap gap-3">
            {attachments.map((a, i) => (
              <figure key={i} className="w-[150px]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={a.src}
                  alt={a.label}
                  className="h-[150px] w-[150px] rounded-md border border-neutral-800 bg-neutral-950 object-contain"
                />
                <figcaption className="mt-1 flex items-center justify-between gap-1 text-[10px] text-neutral-500">
                  <span>
                    {i + 1} · {a.label}
                  </span>
                  {a.video && (
                    <a
                      href={a.video}
                      target="_blank"
                      rel="noreferrer"
                      className="shrink-0 text-sky-400 hover:underline"
                    >
                      ▶ watch
                    </a>
                  )}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      {post.image_idea && (
        <div className="mt-2 rounded border border-neutral-800 bg-neutral-900/60 px-2.5 py-1.5 text-[11px] leading-relaxed text-neutral-400">
          <span className="font-medium text-neutral-300">Custom image idea:</span> {post.image_idea}
        </div>
      )}

      {post.error && (
        <p className="mt-2 rounded border border-red-900/60 bg-red-950/30 px-2 py-1 text-xs text-red-300">
          {post.error}
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
              {busy === "approve" ? "Publishing…" : "Approve & publish"}
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
            <span className="ml-auto text-[11px] text-neutral-600">{words} words</span>
          </>
        )}
        {post.status === "failed" && (
          <button
            onClick={() => act("retry")}
            disabled={!!busy}
            className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800"
          >
            {busy === "retry" ? "Retrying…" : "Retry publish"}
          </button>
        )}
        {post.status === "posted" && post.posted_at && (
          <span className="text-[11px] text-neutral-600">Posted {rel(post.posted_at)}</span>
        )}
        {msg && <span className="text-xs text-red-400">{msg}</span>}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    draft: "border-amber-800 bg-amber-950 text-amber-300",
    approved: "border-sky-800 bg-sky-950 text-sky-300",
    posted: "border-emerald-800 bg-emerald-950 text-emerald-300",
    failed: "border-red-800 bg-red-950 text-red-300",
    rejected: "border-neutral-700 bg-neutral-900 text-neutral-500",
  };
  const label =
    status === "approved" ? "publishing shortly" : status === "rejected" ? "dismissed" : status;
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
