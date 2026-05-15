"use client";

import { useState } from "react";
import clsx from "clsx";
import type { Draft, Hook } from "../../../lib/types";

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

interface Props {
  draft: Draft;
  hook: Hook | null;
  onApprove: (edited?: string) => void;
  onReject: () => void;
}

const channelLabel: Record<string, string> = {
  linkedin_connect: "LinkedIn connect note",
  linkedin_dm: "LinkedIn DM (post-accept)",
  linkedin_followup_1: "LinkedIn follow-up #1",
  linkedin_followup_2: "LinkedIn follow-up #2",
  email: "Email (cold)",
  email_followup_1: "Email follow-up #1",
  email_followup_2: "Email follow-up #2",
};

const channelLimit: Record<string, number> = {
  linkedin_connect: 280,
  linkedin_dm: 500,
  email: 1000,
};

export function DraftCard({ draft, hook, onApprove, onReject }: Props) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft.edited_body ?? draft.body);
  const [copied, setCopied] = useState(false);
  const limit = channelLimit[draft.channel] ?? 1000;
  const over = text.length > limit;

  async function handleCopy() {
    const ok = await copyToClipboard(text);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950">
      <div className="flex items-center justify-between border-b border-neutral-800 px-4 py-2">
        <div className="text-xs uppercase tracking-wide text-neutral-400">
          {channelLabel[draft.channel] ?? draft.channel}
        </div>
        <div className="flex items-center gap-3 text-xs text-neutral-500">
          {hook && (
            <span className="font-mono">
              hook · {hook.type} · {hook.signal_strength}/5
            </span>
          )}
          <span
            className={clsx(
              "font-mono",
              over ? "text-red-400" : "text-neutral-500",
            )}
          >
            {text.length} / {limit}
          </span>
        </div>
      </div>

      <div className="p-4">
        {editing ? (
          <textarea
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 font-mono text-sm leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
            rows={6}
          />
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-neutral-200">
            {text}
          </pre>
        )}

        {hook && (
          <div className="mt-3 rounded-md bg-neutral-900 px-3 py-2 text-xs text-neutral-400">
            <span className="text-neutral-500">↳ anchored on </span>
            <span className="italic">"{hook.reference}"</span>
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          {editing ? (
            <>
              <button
                onClick={() => {
                  onApprove(text);
                  setEditing(false);
                }}
                className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium hover:bg-emerald-600"
              >
                Save + approve
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setText(draft.edited_body ?? draft.body);
                }}
                className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-900"
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => onApprove(text)}
                className="rounded-md bg-emerald-900/60 px-3 py-1.5 text-sm font-medium text-emerald-300 hover:bg-emerald-900"
              >
                Approve
              </button>
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
                onClick={() => setEditing(true)}
                className="rounded-md border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-900"
              >
                Edit
              </button>
              <button
                onClick={onReject}
                className="rounded-md bg-red-900/30 px-3 py-1.5 text-sm font-medium text-red-300 hover:bg-red-900/50"
              >
                Reject
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
