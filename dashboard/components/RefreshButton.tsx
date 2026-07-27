"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

// Global "refresh all feeds" — router.refresh() re-runs every server component on the
// current route with fresh data (leads, replies, queues, analytics…) without losing
// client state like scroll or open panels. Lives in the header so it's on every page.
export function RefreshButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <button
      aria-label="Refresh all feeds"
      title="Refresh all feeds"
      disabled={pending}
      onClick={() => startTransition(() => router.refresh())}
      className="shrink-0 rounded border border-neutral-800 bg-neutral-950 p-1.5 text-neutral-400 transition-colors hover:border-neutral-600 hover:text-white disabled:opacity-60"
    >
      <svg
        className={`h-3.5 w-3.5 ${pending ? "animate-spin" : ""}`}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M21 12a9 9 0 1 1-2.64-6.36" />
        <path d="M21 3v6h-6" />
      </svg>
    </button>
  );
}
