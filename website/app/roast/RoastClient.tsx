"use client";

import { useRef, useState } from "react";

import { SITE } from "@/lib/site";

type Roast = {
  grade: string;
  verdict: string;
  problems: Array<{ issue: string; fix: string }>;
  rewrite: string;
  why_it_works: string;
};

const STEPS = ["Reading your message", "Finding what kills replies", "Writing the rewrite"];

const PRIMARY =
  "inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300";
const SECONDARY =
  "inline-flex items-center justify-center rounded-full border border-neutral-700 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500 hover:text-white";
const INPUT =
  "w-full rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-3 text-[15px] text-white placeholder-neutral-600 focus:border-sky-500 focus:outline-none";

export function RoastClient() {
  const [text, setText] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [error, setError] = useState("");
  const [roast, setRoast] = useState<Roast | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopTimer() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (text.trim().length < 20 || !email.trim()) {
      setError("Paste your cold message and a work email.");
      return;
    }
    setStatus("loading");
    setStep(0);
    timer.current = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 4000);
    try {
      const res = await fetch("/api/roast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, email, name }),
      });
      const data = await res.json();
      stopTimer();
      if (!data.ok) {
        setError(data.error || "Could not complete the roast.");
        setStatus("error");
        return;
      }
      setRoast(data.roast);
      setResultId(data.id ?? null);
      setStatus("done");
    } catch {
      stopTimer();
      setError("Something went wrong. Try again.");
      setStatus("error");
    }
  }

  function reset() {
    setRoast(null);
    setStatus("idle");
    setError("");
    setText("");
  }

  if (status === "loading") {
    return (
      <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-8">
        <div className="flex items-center gap-3">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-sky-400" />
          <span className="text-sm font-medium text-neutral-300">An agent is roasting your message</span>
        </div>
        <ul className="mt-6 space-y-2.5">
          {STEPS.map((s, i) => (
            <li key={s} className="flex items-center gap-3 text-[15px]">
              <span className={i < step ? "text-sky-400" : i === step ? "animate-pulse text-sky-400" : "text-neutral-700"}>
                {i < step ? "✓" : "•"}
              </span>
              <span className={i <= step ? "text-neutral-200" : "text-neutral-600"}>{s}</span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (status === "done" && roast) {
    return <RoastView roast={roast} id={resultId} onReset={reset} />;
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6 sm:p-8">
      <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-neutral-500">
        Your cold email or LinkedIn message
      </label>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={7}
        placeholder="Paste the exact message you send to prospects..."
        className={`${INPUT} resize-y`}
      />
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-neutral-500">
            Work email
          </label>
          <input className={INPUT} type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-neutral-500">
            Name <span className="text-neutral-700">(optional)</span>
          </label>
          <input className={INPUT} placeholder="Jordan" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      <button type="submit" className={`${PRIMARY} mt-5 w-full sm:w-auto`}>
        Roast my outreach →
      </button>
      <p className="mt-3 text-xs text-neutral-600">
        Free, honest, and you get a sendable rewrite back. We&apos;ll email you a copy. About 20 seconds.
      </p>
    </form>
  );
}

function RoastView({ roast, id, onReset }: { roast: Roast; id: string | null; onReset: () => void }) {
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);
  async function share() {
    if (!id) return;
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/roast/r/${id}`);
      setShared(true);
      setTimeout(() => setShared(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(roast.rewrite);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div>
      <div className="flex items-center gap-4">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border border-neutral-800 bg-neutral-950 font-mono text-2xl font-semibold text-sky-400">
          {roast.grade}
        </div>
        <p className="text-lg font-medium leading-snug text-white">{roast.verdict}</p>
      </div>

      <div className="mt-8">
        <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
          What is killing your replies
        </div>
        <ul className="mt-4 space-y-4">
          {roast.problems?.map((p, i) => (
            <li key={i} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-5">
              <p className="text-[15px] leading-relaxed text-neutral-200">{p.issue}</p>
              <p className="mt-2 text-[14px] leading-relaxed text-neutral-400">
                <span className="font-medium text-sky-400/80">Fix:</span> {p.fix}
              </p>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-8">
        <div className="flex items-center justify-between">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
            The rewrite
          </div>
          <button onClick={copy} className="text-xs font-medium text-neutral-400 hover:text-white">
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <pre className="mt-3 whitespace-pre-wrap rounded-2xl border border-sky-900/50 bg-sky-950/20 p-5 font-sans text-[15px] leading-relaxed text-neutral-100">
          {roast.rewrite}
        </pre>
        {roast.why_it_works && (
          <p className="mt-3 text-[14px] leading-relaxed text-neutral-400">{roast.why_it_works}</p>
        )}
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-neutral-900 pt-8">
        <a href={SITE.calUrl} target="_blank" rel="noreferrer" className={PRIMARY}>
          Have an agent send these for you →
        </a>
        <button onClick={onReset} className={SECONDARY}>
          Roast another
        </button>
        {id && (
          <button onClick={share} className={SECONDARY}>
            {shared ? "Link copied" : "Share my grade"}
          </button>
        )}
      </div>
      <p className="mt-3 text-xs text-neutral-600">
        Agentry builds the autonomous outreach systems that write and send messages like the rewrite, at scale.
      </p>
    </div>
  );
}
