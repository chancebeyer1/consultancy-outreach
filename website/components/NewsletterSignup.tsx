"use client";

import { useState } from "react";

export function NewsletterSignup() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("loading");
    setMsg("");
    try {
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!data.ok) {
        setStatus("error");
        setMsg(data.error || "Could not subscribe.");
        return;
      }
      setStatus("done");
      setEmail("");
    } catch {
      setStatus("error");
      setMsg("Something went wrong. Try again.");
    }
  }

  return (
    <div className="max-w-md">
      <div className="text-sm font-semibold text-white">The Agent Brief</div>
      <p className="mt-1 text-xs leading-relaxed text-neutral-500">
        A weekly read on what actually matters in AI agents. Written by an agent, curated by a
        human. No fluff.
      </p>
      {status === "done" ? (
        <p className="mt-3 text-sm text-sky-400">You are in. The next issue will hit your inbox.</p>
      ) : (
        <form onSubmit={submit} className="mt-3 flex gap-2">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            placeholder="you@company.com"
            autoComplete="email"
            className="min-w-0 flex-1 rounded-full border border-neutral-700 bg-neutral-950 px-4 py-2 text-sm text-white placeholder-neutral-600 focus:border-sky-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={status === "loading"}
            className="shrink-0 rounded-full bg-sky-400 px-4 py-2 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300 disabled:opacity-50"
          >
            {status === "loading" ? "…" : "Subscribe"}
          </button>
        </form>
      )}
      {msg && <p className="mt-1.5 text-xs text-red-400">{msg}</p>}
    </div>
  );
}
