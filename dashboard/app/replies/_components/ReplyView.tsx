"use client";

import clsx from "clsx";
import { useState } from "react";

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
  oof: "border-neutral-700 bg-neutral-900 text-neutral-400",
  unsubscribe: "border-red-700 bg-red-900/30 text-red-300",
  other: "border-neutral-700 bg-neutral-900 text-neutral-300",
};

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function ReplyView({ row, onMarkHandled }: Props) {
  const { reply, lead, original_message } = row;
  const intent = (reply.intent ?? "other") as keyof typeof intentColor;

  const [draftBody, setDraftBody] = useState(reply.suggested_reply ?? "");
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!draftBody) return;
    const ok = await copyToClipboard(draftBody);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  }

  return (
    <div>
      {/* Lead header */}
      <div className="mb-6 border-b border-neutral-800 pb-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {lead.name || "?"}
            </h1>
            <p className="mt-1 truncate text-sm text-neutral-400">{lead.headline}</p>
            <p className="mt-1 text-xs text-neutral-500">
              {lead.role} {lead.company ? `· ${lead.company}` : ""}
            </p>
            {lead.linkedin_url && (
              <a
                href={lead.linkedin_url}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-block text-xs text-sky-400 hover:underline"
              >
                {lead.linkedin_url} ↗
              </a>
            )}
          </div>
          <div
            className={clsx(
              "shrink-0 rounded-md border px-4 py-3 text-center font-mono",
              intentColor[intent],
            )}
          >
            <div className="text-[10px] uppercase tracking-wide opacity-70">classified</div>
            <div className="mt-1 text-sm font-semibold uppercase">{intent}</div>
            {reply.sentiment && (
              <div className="mt-1 text-[10px] opacity-70">{reply.sentiment}</div>
            )}
          </div>
        </div>
        {reply.summary && (
          <p className="mt-3 text-sm italic text-neutral-400">"{reply.summary}"</p>
        )}
      </div>

      {/* Outbound + inbound thread */}
      <div className="space-y-4">
        {original_message && (
          <ThreadBlock
            label="You sent"
            timestamp={null}
            body={original_message}
            tone="outbound"
          />
        )}
        <ThreadBlock
          label={`${lead.name?.split(" ")[0] ?? "They"} replied`}
          timestamp={reply.received_at}
          body={reply.body}
          tone="inbound"
        />
      </div>

      {/* Suggested reply */}
      <div className="mt-8 rounded-lg border border-neutral-800 bg-neutral-950">
        <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-2">
          <div className="text-xs uppercase tracking-wide text-neutral-400">
            Suggested reply
          </div>
          {reply.next_action && (
            <span className="font-mono text-[10px] text-neutral-500">
              → {reply.next_action.replaceAll("_", " ")}
            </span>
          )}
        </div>

        <div className="p-4">
          {!reply.suggested_reply && !draftBody && (
            <p className="text-sm italic text-neutral-500">
              No suggested reply for this intent.{" "}
              {reply.next_action === "wait_per_their_request" &&
                "Set a reminder; nothing to send right now."}
              {reply.next_action === "drop" && "Drop this lead from the sequence."}
            </p>
          )}

          {(reply.suggested_reply || draftBody) && (
            <>
              {editing ? (
                <textarea
                  autoFocus
                  value={draftBody}
                  onChange={(e) => setDraftBody(e.target.value)}
                  className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 font-mono text-sm leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
                  rows={5}
                />
              ) : (
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-neutral-200">
                  {draftBody}
                </pre>
              )}

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  onClick={handleCopy}
                  className={clsx(
                    "rounded-md border px-3 py-1.5 text-sm",
                    copied
                      ? "border-emerald-700 bg-emerald-900/40 text-emerald-300"
                      : "border-neutral-700 text-neutral-300 hover:bg-neutral-900",
                  )}
                >
                  {copied ? "Copied" : "Copy"}
                </button>
                <button
                  onClick={() => setEditing((v) => !v)}
                  className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-900"
                >
                  {editing ? "Done editing" : "Edit"}
                </button>
              </div>
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
          disabled={!!reply.handled_at}
          className={clsx(
            "rounded-md px-4 py-2 text-sm font-medium",
            reply.handled_at
              ? "cursor-not-allowed bg-neutral-900 text-neutral-600"
              : "bg-emerald-900/60 text-emerald-300 hover:bg-emerald-900",
          )}
        >
          {reply.handled_at ? "Handled" : "Mark handled"}
        </button>
      </div>
    </div>
  );
}

function ThreadBlock({
  label,
  timestamp,
  body,
  tone,
}: {
  label: string;
  timestamp: string | null;
  body: string;
  tone: "outbound" | "inbound";
}) {
  return (
    <div
      className={clsx(
        "rounded-lg border px-4 py-3",
        tone === "outbound"
          ? "border-neutral-800 bg-neutral-950"
          : "border-sky-900/50 bg-sky-950/20",
      )}
    >
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-mono uppercase tracking-wide text-neutral-500">
          {label}
        </span>
        {timestamp && (
          <span className="text-neutral-600">
            {new Date(timestamp).toLocaleString()}
          </span>
        )}
      </div>
      <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-neutral-200">
        {body}
      </pre>
    </div>
  );
}
