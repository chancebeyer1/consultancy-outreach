"use client";

import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ReplyReviewRow } from "@/lib/types";

interface Props {
  row: ReplyReviewRow;
  onMarkHandled: () => void;
}

const intentColor: Record<string, string> = {
  interested: "border-emerald-700 bg-emerald-900/30 text-emerald-300",
  referral: "border-sky-700 bg-sky-900/30 text-sky-300",
  objection: "border-amber-700 bg-amber-900/30 text-amber-300",
  not_now: "border-neutral-700 bg-neutral-900 text-neutral-300",
  oof: "border-neutral-800 bg-neutral-900 text-neutral-500",
  unsubscribe: "border-red-700 bg-red-900/30 text-red-300",
  other: "border-neutral-700 bg-neutral-900 text-neutral-300",
};

type ThreadMsg = { from_me: boolean; text: string; at: string | null };

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function ReplyView({ row, onMarkHandled }: Props) {
  const { reply, lead, original_message } = row;
  const intent = (reply.intent ?? "other") as keyof typeof intentColor;
  const isLinkedIn = String(reply.channel || "").startsWith("linkedin");
  const channelLabel = isLinkedIn ? "LinkedIn" : "Email";
  const firstName = lead.name?.split(" ")[0] ?? "them";

  const { minDate, sep1 } = useMemo(() => {
    const now = new Date();
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const y = now.getMonth() >= 8 ? now.getFullYear() + 1 : now.getFullYear();
    return { minDate: isoDate(tomorrow), sep1: `${y}-09-01` };
  }, []);

  const [draftBody, setDraftBody] = useState(reply.suggested_reply ?? "");
  const [copied, setCopied] = useState(false);

  const [thread, setThread] = useState<ThreadMsg[]>([]);
  const [threadState, setThreadState] = useState<"loading" | "ready" | "error">("loading");

  const [sending, setSending] = useState(false);
  const [sentOk, setSentOk] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [instruction, setInstruction] = useState("");
  const [regenerating, setRegenerating] = useState(false);

  const [scheduling, setScheduling] = useState(false);
  const [dueAt, setDueAt] = useState(sep1);
  const [schedulingBusy, setSchedulingBusy] = useState(false);
  const [scheduledMsg, setScheduledMsg] = useState<string | null>(null);
  // Already-handled replies show a collapsed bar (not the editable box) until reopened.
  const [composerOpen, setComposerOpen] = useState(false);

  // Reset per-reply state + fetch the full thread when the active reply changes.
  useEffect(() => {
    setDraftBody(reply.suggested_reply ?? "");
    setSentOk(false);
    setConfirming(false);
    setError(null);
    setInstruction("");
    setScheduling(false);
    setDueAt(sep1);
    setScheduledMsg(null);
    setComposerOpen(false);
    setThread([]);
    setThreadState("loading");

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/api/thread", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ replyId: reply.id }),
        });
        const data = (await res.json().catch(() => ({}))) as { messages?: ThreadMsg[] };
        if (cancelled) return;
        setThread(data.messages ?? []);
        setThreadState("ready");
      } catch {
        if (!cancelled) setThreadState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reply.id, reply.suggested_reply, sep1]);

  async function handleCopy() {
    if (!draftBody) return;
    const ok = await copyToClipboard(draftBody);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  }

  async function handleRegenerate() {
    if (!instruction.trim() || regenerating) return;
    setRegenerating(true);
    setError(null);
    try {
      const res = await fetch("/api/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ replyId: reply.id, instruction: instruction.trim() }),
      });
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean; suggested_reply?: string; error?: string };
      if (!res.ok || !data.suggested_reply) {
        setError(data.error || `Regenerate failed (${res.status})`);
        return;
      }
      setDraftBody(data.suggested_reply);
      setInstruction("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Regenerate failed");
    } finally {
      setRegenerating(false);
    }
  }

  function armConfirm() {
    setError(null);
    setConfirming(true);
    if (confirmTimer.current) clearTimeout(confirmTimer.current);
    confirmTimer.current = setTimeout(() => setConfirming(false), 4500);
  }

  async function handleSend() {
    if (!draftBody.trim() || sending) return;
    setSending(true);
    setError(null);
    if (confirmTimer.current) clearTimeout(confirmTimer.current);
    setConfirming(false);
    try {
      const res = await fetch("/api/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ replyId: reply.id, body: draftBody.trim() }),
      });
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string };
      if (!res.ok || !data.ok) {
        setError(data.error || `Send failed (${res.status})`);
        return;
      }
      setSentOk(true);
      onMarkHandled();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending(false);
    }
  }

  async function handleSchedule() {
    if (!draftBody.trim() || !dueAt || schedulingBusy) return;
    setSchedulingBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ replyId: reply.id, dueAt: `${dueAt}T12:00:00`, body: draftBody.trim() }),
      });
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string };
      if (!res.ok || !data.ok) {
        setError(data.error || `Schedule failed (${res.status})`);
        return;
      }
      setScheduledMsg(`Scheduled — auto-sends on ${dueAt} via ${channelLabel}.`);
      setScheduling(false);
      onMarkHandled();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Schedule failed");
    } finally {
      setSchedulingBusy(false);
    }
  }

  const fallback: ThreadMsg[] = [
    ...(original_message ? [{ from_me: true, text: original_message, at: null }] : []),
    { from_me: false, text: reply.body, at: reply.received_at },
  ];
  const done = sentOk || !!scheduledMsg;
  // Already handled in a prior session → show a collapsed bar, not the editable box, until reopened.
  const collapsed = !!reply.handled_at && !composerOpen && !done;
  const messages = threadState === "ready" && thread.length > 0 ? thread : fallback;

  return (
    <div>
      {/* Lead header */}
      <div className="mb-6 border-b border-neutral-800 pb-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{lead.name || "?"}</h1>
            <p className="mt-1 truncate text-sm text-neutral-400">{lead.headline}</p>
            <p className="mt-1 text-xs text-neutral-500">
              {lead.role} {lead.company ? `· ${lead.company}` : ""}
            </p>
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span
                className={clsx(
                  "rounded px-1.5 py-0.5 font-medium",
                  isLinkedIn ? "bg-sky-900/40 text-sky-300" : "bg-violet-900/40 text-violet-300",
                )}
              >
                {channelLabel}
              </span>
              {reply.handled_at && !done && (
                <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-neutral-400">handled</span>
              )}
              {lead.linkedin_url && (
                <a href={lead.linkedin_url} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">
                  profile ↗
                </a>
              )}
              {row.deal_id && (
                <a href={`/pipeline/${row.deal_id}`} className="text-emerald-400 hover:underline">
                  deal ↗
                </a>
              )}
            </div>
          </div>
          <div className={clsx("shrink-0 rounded-md border px-4 py-3 text-center font-mono", intentColor[intent])}>
            <div className="text-[10px] uppercase tracking-wide opacity-70">classified</div>
            <div className="mt-1 text-sm font-semibold uppercase">{intent === "oof" ? "OOO" : intent}</div>
            {reply.sentiment && <div className="mt-1 text-[10px] opacity-70">{reply.sentiment}</div>}
          </div>
        </div>
        {reply.summary && <p className="mt-3 text-sm italic text-neutral-400">&ldquo;{reply.summary}&rdquo;</p>}
      </div>

      {/* Full conversation thread */}
      <div>
        <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-neutral-500">
          Conversation
          {threadState === "loading" && <span className="text-neutral-600">· loading…</span>}
        </div>
        <div className="space-y-2.5">
          {messages.map((m, i) => (
            <MessageBubble key={i} msg={m} whoElse={firstName} />
          ))}
        </div>
      </div>

      {/* Reply composer — collapses to a confirmation once sent or scheduled */}
      <div className="mt-8 rounded-lg border border-neutral-800 bg-neutral-950">
        <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-2">
          <div className="text-xs uppercase tracking-wide text-neutral-400">
            {done || collapsed ? "Handled" : `Reply to ${lead.name || firstName} · ${channelLabel}`}
          </div>
          {!done && !collapsed && reply.next_action && (
            <span className="font-mono text-[10px] text-neutral-500">→ {reply.next_action.replaceAll("_", " ")}</span>
          )}
        </div>

        <div className="p-4">
          {collapsed ? (
            <div className="flex flex-col items-start gap-3">
              <p className="text-sm text-neutral-400">
                ✓ You&rsquo;ve handled this one — the full conversation is above. Reply again if you need to:
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    setDraftBody("");
                    setComposerOpen(true);
                  }}
                  className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-900"
                >
                  ✍ Write a reply
                </button>
                <button
                  onClick={() => {
                    setDraftBody(reply.suggested_reply ?? "");
                    setComposerOpen(true);
                  }}
                  className="rounded-md border border-sky-800 bg-sky-950/40 px-3 py-1.5 text-sm text-sky-200 hover:bg-sky-900/40"
                >
                  ✦ Draft with AI
                </button>
              </div>
            </div>
          ) : done ? (
            <div className="rounded-md border border-emerald-800 bg-emerald-950/30 px-4 py-4 text-center">
              <p className="text-sm text-emerald-300">
                {sentOk ? `Sent ✓ — delivered on ${channelLabel} and marked handled.` : scheduledMsg}
              </p>
              <p className="mt-1 text-xs text-neutral-500">This one’s done — the next reply is selected on the left.</p>
            </div>
          ) : (
            <>
              <textarea
                value={draftBody}
                onChange={(e) => setDraftBody(e.target.value)}
                placeholder={`Write a reply to ${firstName}…`}
                className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 font-sans text-sm leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
                rows={5}
              />

              {/* Regenerate with an operator steer */}
              <div className="mt-2 flex gap-2">
                <input
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleRegenerate();
                    }
                  }}
                  placeholder="Tell the AI what to change… e.g. “offer a case study”, “warmer, shorter”"
                  className="min-w-0 flex-1 rounded-md border border-neutral-800 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200 focus:border-sky-600 focus:outline-none"
                />
                <button
                  onClick={handleRegenerate}
                  disabled={!instruction.trim() || regenerating}
                  className="shrink-0 rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-200 hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {regenerating ? "Regenerating…" : "↻ Regenerate"}
                </button>
              </div>

              {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

              <div className="mt-4 flex flex-wrap items-center gap-2">
                {!confirming ? (
                  <button
                    onClick={armConfirm}
                    disabled={!draftBody.trim() || sending}
                    className={clsx(
                      "rounded-md px-4 py-1.5 text-sm font-medium",
                      !draftBody.trim() || sending
                        ? "cursor-not-allowed bg-neutral-900 text-neutral-600"
                        : "bg-sky-600 text-white hover:bg-sky-500",
                    )}
                  >
                    {sending ? "Sending…" : `Send on ${channelLabel}`}
                  </button>
                ) : (
                  <>
                    <button
                      onClick={handleSend}
                      disabled={sending}
                      className="rounded-md bg-amber-600 px-4 py-1.5 text-sm font-semibold text-white hover:bg-amber-500"
                    >
                      Confirm — send to {firstName}
                    </button>
                    <button
                      onClick={() => setConfirming(false)}
                      className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-900"
                    >
                      Cancel
                    </button>
                  </>
                )}
                <button
                  onClick={() => setScheduling((v) => !v)}
                  className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-900"
                >
                  Schedule…
                </button>
                <button
                  onClick={handleCopy}
                  disabled={!draftBody}
                  className={clsx(
                    "rounded-md border px-3 py-1.5 text-sm",
                    copied
                      ? "border-emerald-700 bg-emerald-900/40 text-emerald-300"
                      : "border-neutral-700 text-neutral-300 hover:bg-neutral-900",
                  )}
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>

              {/* Schedule-for-later panel */}
              {scheduling && (
                <div className="mt-3 rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
                  <div className="text-xs text-neutral-400">Auto-send this reply on:</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      type="date"
                      value={dueAt}
                      min={minDate}
                      onChange={(e) => setDueAt(e.target.value)}
                      className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-sm text-neutral-200"
                    />
                    <button
                      onClick={() => setDueAt(sep1)}
                      className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-400 hover:bg-neutral-800"
                    >
                      Sep 1
                    </button>
                    <button
                      onClick={handleSchedule}
                      disabled={!dueAt || schedulingBusy}
                      className="rounded-md bg-sky-700 px-3 py-1.5 text-sm text-white hover:bg-sky-600 disabled:opacity-50"
                    >
                      {schedulingBusy ? "Scheduling…" : "Schedule auto-send"}
                    </button>
                  </div>
                  <p className="mt-2 text-[11px] text-neutral-500">
                    Sends automatically on the chosen date (this exact text), then shows in “Scheduled” on the left where
                    you can cancel it. This is different from Send, which goes out now.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between gap-3 border-t border-neutral-800 pt-4">
        <div className="text-xs text-neutral-500">
          Press <span className="kbd">x</span> to mark handled · <span className="kbd">j/k</span> to navigate
        </div>
        <button
          onClick={onMarkHandled}
          disabled={!!reply.handled_at || done}
          className={clsx(
            "rounded-md px-4 py-2 text-sm font-medium",
            reply.handled_at || done
              ? "cursor-not-allowed bg-neutral-900 text-neutral-600"
              : "bg-emerald-900/60 text-emerald-300 hover:bg-emerald-900",
          )}
        >
          {reply.handled_at || done ? "Handled" : "Mark handled"}
        </button>
      </div>
    </div>
  );
}

function MessageBubble({ msg, whoElse }: { msg: ThreadMsg; whoElse: string }) {
  return (
    <div className={clsx("flex", msg.from_me ? "justify-end" : "justify-start")}>
      <div
        className={clsx(
          "max-w-[85%] rounded-lg border px-3.5 py-2.5",
          msg.from_me ? "border-neutral-800 bg-neutral-900" : "border-sky-900/50 bg-sky-950/20",
        )}
      >
        <div className="mb-1 flex items-center justify-between gap-4 text-[10px] uppercase tracking-wide">
          <span className={msg.from_me ? "text-neutral-500" : "text-sky-400/80"}>{msg.from_me ? "You" : whoElse}</span>
          {msg.at && <span className="text-neutral-600">{new Date(msg.at).toLocaleString()}</span>}
        </div>
        <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-neutral-200">{msg.text}</pre>
      </div>
    </div>
  );
}
