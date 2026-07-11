"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type Issue = {
  id: string;
  subject: string | null;
  body: string | null;
  status: string;
  sent_at: string | null;
  recipients: number | null;
  error: string | null;
  created_at: string | null;
};

async function post(payload: object): Promise<{ ok: boolean; error?: string; sent?: number }> {
  const res = await fetch("/api/newsletter", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, error: data?.error, sent: data?.sent };
}

export function NewsletterClient({ issues, subscribers }: { issues: Issue[]; subscribers: number }) {
  const draft = issues.find((i) => i.status === "draft" || i.status === "approved") ?? null;
  const past = issues.filter((i) => i.status === "sent");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-neutral-800 bg-neutral-950 p-4">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">Subscribers</div>
          <div className="mt-0.5 font-mono text-2xl text-neutral-100">{subscribers}</div>
        </div>
        <GenerateButton hasDraft={!!draft} />
      </div>

      {draft ? (
        <DraftEditor issue={draft} subscribers={subscribers} />
      ) : (
        <p className="rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-6 text-center text-sm italic text-neutral-600">
          No draft right now. One is written automatically each Monday, or generate one above.
        </p>
      )}

      {past.length > 0 && (
        <section>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-neutral-400">Sent</h2>
          <div className="space-y-2">
            {past.map((i) => (
              <div
                key={i.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-2.5"
              >
                <span className="truncate text-sm text-neutral-300">{i.subject}</span>
                <span className="shrink-0 font-mono text-[11px] text-neutral-600">
                  {i.recipients ?? 0} sent{i.sent_at ? ` · ${new Date(i.sent_at).toLocaleDateString()}` : ""}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function GenerateButton({ hasDraft }: { hasDraft: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function go() {
    setBusy(true);
    setMsg(null);
    const r = await post({ action: "generate" });
    setBusy(false);
    if (r.ok) {
      setMsg({ ok: true, text: "Draft created below." });
      router.refresh();
    } else {
      setMsg({ ok: false, text: r.error || "Failed" });
    }
  }

  return (
    <div className="flex items-center gap-3">
      {msg && <span className={`text-xs ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</span>}
      <button
        onClick={go}
        disabled={busy}
        className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-800 disabled:opacity-50"
      >
        {busy ? "Writing…" : hasDraft ? "Regenerate issue" : "Generate this week's issue"}
      </button>
    </div>
  );
}

function DraftEditor({ issue, subscribers }: { issue: Issue; subscribers: number }) {
  const router = useRouter();
  const [subject, setSubject] = useState(issue.subject ?? "");
  const [body, setBody] = useState(issue.body ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const dirty = subject !== (issue.subject ?? "") || body !== (issue.body ?? "");

  async function save() {
    setBusy("save");
    setMsg(null);
    const r = await post({ action: "save", id: issue.id, subject, body });
    setBusy(null);
    if (r.ok) {
      setMsg({ ok: true, text: "Saved." });
      router.refresh();
    } else setMsg({ ok: false, text: r.error || "Failed" });
  }

  async function send() {
    if (!confirm(`Send "${subject}" to ${subscribers} subscriber${subscribers === 1 ? "" : "s"}?`)) return;
    setBusy("send");
    setMsg(null);
    const r = await post({ action: "send", id: issue.id, subject, body });
    setBusy(null);
    if (r.ok) {
      setMsg({ ok: true, text: `Sent to ${r.sent ?? subscribers} subscribers.` });
      router.refresh();
    } else setMsg({ ok: false, text: r.error || "Send failed" });
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="rounded border border-amber-800 bg-amber-950 px-1.5 py-0.5 font-mono text-[10px] uppercase text-amber-300">
          Draft
        </span>
        <span className="text-[11px] text-neutral-600">
          {issue.created_at ? new Date(issue.created_at).toLocaleDateString() : ""}
        </span>
      </div>

      <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">Subject</label>
      <input
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
        className="mb-3 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none"
      />
      <label className="mb-1 block text-[10px] uppercase tracking-wide text-neutral-500">Body</label>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={Math.max(14, Math.ceil(body.length / 80))}
        className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 p-3 font-mono text-[13px] leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
      />

      {issue.error && (
        <p className="mt-2 rounded border border-red-900/60 bg-red-950/30 px-2 py-1 text-xs text-red-300">
          {issue.error}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          onClick={send}
          disabled={!!busy || subscribers === 0 || !body.trim()}
          className="rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-500 disabled:opacity-50"
          title={subscribers === 0 ? "No subscribers yet" : undefined}
        >
          {busy === "send" ? "Sending…" : `Send to ${subscribers} subscriber${subscribers === 1 ? "" : "s"}`}
        </button>
        <button
          onClick={save}
          disabled={!!busy || !dirty}
          className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
        >
          {busy === "save" ? "Saving…" : "Save edits"}
        </button>
        {msg && <span className={`text-xs ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>{msg.text}</span>}
      </div>
    </div>
  );
}
