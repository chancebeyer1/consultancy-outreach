"use client";

import { useRef, useState } from "react";

import { SITE } from "@/lib/site";

type Opportunity = {
  title: string;
  today: string;
  agent: string;
  time_saved: string;
  complexity: string;
};
type Report = {
  company: string;
  summary: string;
  opportunities: Opportunity[];
  first_build: string;
  note: string;
};

const STEPS = [
  "Reading your website",
  "Researching your company",
  "Spotting manual workflows",
  "Designing the agents",
  "Writing your audit",
];

const PRIMARY =
  "inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300";
const SECONDARY =
  "inline-flex items-center justify-center rounded-full border border-neutral-700 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500 hover:text-white";
const INPUT =
  "w-full rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-3 text-[15px] text-white placeholder-neutral-600 focus:border-sky-500 focus:outline-none";

export function AuditClient() {
  const [website, setWebsite] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [error, setError] = useState("");
  const [report, setReport] = useState<Report | null>(null);
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
    if (!website.trim() || !email.trim()) {
      setError("Add your website and a work email.");
      return;
    }
    setStatus("loading");
    setStep(0);
    timer.current = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 4500);
    try {
      const res = await fetch("/api/audit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ website, email, name }),
      });
      const data = await res.json();
      stopTimer();
      if (!data.ok) {
        setError(data.error || "Could not complete the audit.");
        setStatus("error");
        return;
      }
      setReport(data.report);
      setResultId(data.id ?? null);
      setStatus("done");
    } catch {
      stopTimer();
      setError("Something went wrong. Try again, or book a call.");
      setStatus("error");
    }
  }

  function reset() {
    setReport(null);
    setStatus("idle");
    setError("");
    setWebsite("");
    setName("");
  }

  if (status === "loading") {
    return (
      <div className="rounded-2xl border border-neutral-800 bg-neutral-950 p-8">
        <div className="flex items-center gap-3">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-sky-400" />
          <span className="text-sm font-medium text-neutral-300">An agent is auditing {website}</span>
        </div>
        <ul className="mt-6 space-y-2.5">
          {STEPS.map((s, i) => (
            <li key={s} className="flex items-center gap-3 text-[15px]">
              <span
                className={
                  i < step
                    ? "text-sky-400"
                    : i === step
                      ? "animate-pulse text-sky-400"
                      : "text-neutral-700"
                }
              >
                {i < step ? "✓" : i === step ? "•" : "•"}
              </span>
              <span className={i <= step ? "text-neutral-200" : "text-neutral-600"}>{s}</span>
            </li>
          ))}
        </ul>
        <p className="mt-6 text-xs text-neutral-600">This takes about 30 seconds. Hang tight.</p>
      </div>
    );
  }

  if (status === "done" && report) {
    return <ReportView report={report} id={resultId} onReset={reset} />;
  }

  return (
    <form onSubmit={submit} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6 sm:p-8">
      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-neutral-500">
            Your website
          </label>
          <input
            className={INPUT}
            placeholder="acme.com"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            autoComplete="url"
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-neutral-500">
              Work email
            </label>
            <input
              className={INPUT}
              placeholder="you@acme.com"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-neutral-500">
              Name <span className="text-neutral-700">(optional)</span>
            </label>
            <input
              className={INPUT}
              placeholder="Jordan"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          </div>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      <button type="submit" className={`${PRIMARY} mt-5 w-full sm:w-auto`}>
        Run my free audit →
      </button>
      <p className="mt-3 text-xs text-neutral-600">
        No sales call required. We&apos;ll email you a copy and send The Agent Brief now and then
        (unsubscribe anytime). Takes ~30 seconds.
      </p>
    </form>
  );
}

function Badge({ children, tone }: { children: React.ReactNode; tone?: "sky" | "muted" }) {
  const cls =
    tone === "sky"
      ? "border-sky-800 bg-sky-950/50 text-sky-300"
      : "border-neutral-700 bg-neutral-900 text-neutral-400";
  return (
    <span className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${cls}`}>
      {children}
    </span>
  );
}

function ReportView({ report, id, onReset }: { report: Report; id: string | null; onReset: () => void }) {
  const [shared, setShared] = useState(false);
  async function share() {
    if (!id) return;
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/audit/r/${id}`);
      setShared(true);
      setTimeout(() => setShared(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
        AI Opportunity Audit
      </div>
      <h2 className="mt-2 text-3xl font-semibold tracking-tight text-white">{report.company}</h2>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-neutral-400">{report.summary}</p>

      <div className="mt-8 space-y-4">
        {report.opportunities?.map((o, i) => (
          <div key={i} className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-lg font-semibold text-white">
                {i + 1}. {o.title}
              </h3>
              <div className="flex flex-wrap justify-end gap-2">
                <Badge tone="sky">{o.time_saved}</Badge>
                <Badge tone="muted">{o.complexity}</Badge>
              </div>
            </div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <div className="text-[11px] font-medium uppercase tracking-wide text-neutral-600">
                  Today
                </div>
                <p className="mt-1 text-[14px] leading-relaxed text-neutral-400">{o.today}</p>
              </div>
              <div>
                <div className="text-[11px] font-medium uppercase tracking-wide text-sky-400/80">
                  With an agent
                </div>
                <p className="mt-1 text-[14px] leading-relaxed text-neutral-300">{o.agent}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {report.first_build && (
        <div className="mt-5 rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6">
          <div className="text-[11px] font-medium uppercase tracking-wide text-sky-400">
            Where we&apos;d start
          </div>
          <p className="mt-2 text-[15px] leading-relaxed text-neutral-200">{report.first_build}</p>
        </div>
      )}
      {report.note && <p className="mt-4 max-w-2xl text-sm italic leading-relaxed text-neutral-500">{report.note}</p>}

      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-neutral-900 pt-8">
        <a href={SITE.calUrl} target="_blank" rel="noreferrer" className={PRIMARY}>
          Book a call to scope it →
        </a>
        <button onClick={onReset} className={SECONDARY}>
          Audit another site
        </button>
        {id && (
          <button onClick={share} className={SECONDARY}>
            {shared ? "Link copied" : "Share this audit"}
          </button>
        )}
      </div>
      <p className="mt-3 text-xs text-neutral-600">
        These aren&apos;t hypotheticals. Each one is a build we ship in weeks.
      </p>
    </div>
  );
}
