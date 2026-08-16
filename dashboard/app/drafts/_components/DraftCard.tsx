"use client";

import { useState } from "react";
import clsx from "clsx";
import type { Draft, Hook, Lead } from "../../../lib/types";

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
  lead?: Lead;
  onApprove: (edited?: string) => void;
  onReject: () => void;
  // Manual channels only (manual_ig / manual_email): the operator sent the
  // message personally; this records it (status 'sent' + provider='manual').
  onMarkSent?: (edited?: string) => void;
}

const channelLabel: Record<string, string> = {
  linkedin_connect: "LinkedIn connect note",
  linkedin_inmail: "LinkedIn InMail (cold, direct)",
  linkedin_dm: "LinkedIn DM (post-accept)",
  linkedin_followup_1: "LinkedIn follow-up #1",
  linkedin_followup_2: "LinkedIn follow-up #2",
  email: "Email (cold)",
  email_followup_1: "Email follow-up #1",
  email_followup_2: "Email follow-up #2",
  manual_ig: "IG DM — send from your personal IG",
  manual_email: "Email — send from your personal address",
};

const channelLimit: Record<string, number> = {
  linkedin_connect: 280,
  linkedin_inmail: 700,
  linkedin_dm: 500,
  email: 1000,
};

function igHandle(url: string | null | undefined): string | null {
  if (!url) return null;
  const m = url.match(/instagram\.com\/([^/?#]+)/i);
  return m ? m[1] : null;
}

export function DraftCard({ draft, hook, lead, onApprove, onReject, onMarkSent }: Props) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(draft.edited_body ?? draft.body);
  const [copied, setCopied] = useState(false);
  const manual = draft.channel.startsWith("manual_");
  const limit = channelLimit[draft.channel] ?? 1000;
  const over = !manual && text.length > limit;
  const handle = manual ? igHandle(lead?.linkedin_url) : null;
  const subject = draft.hook?.subject ?? hook?.subject ?? null;

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
          {hook && !manual && (
            <span className="font-mono">
              hook · {hook.type} · {hook.signal_strength}/5
            </span>
          )}
          {!manual && (
            <span
              className={clsx(
                "font-mono",
                over ? "text-red-400" : "text-neutral-500",
              )}
            >
              {text.length} / {limit}
            </span>
          )}
        </div>
      </div>

      {manual && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-neutral-800 bg-neutral-900/60 px-4 py-2 text-xs">
          {draft.channel === "manual_ig" && lead?.linkedin_url && (
            <a
              href={lead.linkedin_url}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-sky-400 hover:underline"
            >
              DM → @{handle ?? "instagram"} ↗
            </a>
          )}
          {draft.channel === "manual_email" && lead?.email && (
            <a
              href={`mailto:${lead.email}?subject=${encodeURIComponent(subject ?? "")}&body=${encodeURIComponent(text)}`}
              className="font-mono text-sky-400 hover:underline"
            >
              To → {lead.email} ↗
            </a>
          )}
          {subject && (
            <span className="font-mono text-neutral-400">
              Subject: <span className="text-neutral-300">{subject}</span>
            </span>
          )}
        </div>
      )}

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
            <span className="text-neutral-500">↳ {manual ? "venue context: " : "anchored on "}</span>
            <span className="italic">"{hook.reference}"</span>
            {manual && hook.why_it_matters && hook.why_it_matters !== "unknown" && (
              <span className="text-neutral-500"> · {hook.why_it_matters}</span>
            )}
          </div>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          {editing ? (
            <>
              <button
                onClick={() => {
                  if (manual && onMarkSent) {
                    setEditing(false);
                    return; // manual: saving the edit ≠ sent; keep reviewing
                  }
                  onApprove(text);
                  setEditing(false);
                }}
                className="rounded-md bg-emerald-700 px-3 py-1.5 text-sm font-medium hover:bg-emerald-600"
              >
                {manual ? "Done editing" : "Save + approve"}
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
              {manual && onMarkSent ? (
                <button
                  onClick={() => onMarkSent(text)}
                  className="rounded-md bg-emerald-900/60 px-3 py-1.5 text-sm font-medium text-emerald-300 hover:bg-emerald-900"
                >
                  Mark sent ✓
                </button>
              ) : (
                <button
                  onClick={() => onApprove(text)}
                  className="rounded-md bg-emerald-900/60 px-3 py-1.5 text-sm font-medium text-emerald-300 hover:bg-emerald-900"
                >
                  Approve
                </button>
              )}
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
                {manual ? "Skip venue" : "Reject"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
