"use client";

import { useEffect, useState } from "react";

import { SITE } from "@/lib/site";

const PRIMARY =
  "inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300";
const SECONDARY =
  "inline-flex items-center justify-center rounded-full border border-neutral-700 px-5 py-2.5 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-500 hover:text-white";

// Hours in a working year per full-time person (40h/week × 48 weeks, allowing for PTO/holidays).
// Used both to annualize savings and to express the result as full-time-equivalents freed.
const WORK_WEEKS = 48;
const FTE_HOURS = 40 * WORK_WEEKS;

const usd = (n: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(
    Math.round(n),
  );
const num = (n: number) => new Intl.NumberFormat("en-US").format(Math.round(n));

export function RoiClient() {
  const [people, setPeople] = useState(3);
  const [hours, setHours] = useState(10); // hours/person/week on repetitive, automatable work
  const [cost, setCost] = useState(55); // fully-loaded cost per hour
  const [rate, setRate] = useState(0.7); // share of that work an agent can take over
  const [copied, setCopied] = useState(false);

  // Lightweight shareable state: numbers live in the URL query, so a copied link reproduces the
  // exact scenario without any backend. Read once on mount (window, not useSearchParams, to avoid
  // a Suspense boundary), and offer a "copy link" that writes them back.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const n = (k: string, d: number, min: number, max: number) => {
      const v = Number(q.get(k));
      return Number.isFinite(v) && v >= min && v <= max ? v : d;
    };
    setPeople(n("p", 3, 1, 1000));
    setHours(n("h", 10, 1, 60));
    setCost(n("c", 55, 10, 500));
    setRate(n("r", 0.7, 0.2, 0.95));
  }, []);

  const weeklyHoursSaved = people * hours * rate;
  const annualHoursSaved = weeklyHoursSaved * WORK_WEEKS;
  const annualCostSaved = annualHoursSaved * cost;
  const fte = annualHoursSaved / FTE_HOURS;

  async function copyLink() {
    const q = new URLSearchParams({ p: String(people), h: String(hours), c: String(cost), r: String(rate) });
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/roi-calculator?${q.toString()}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.1fr]">
      {/* Inputs */}
      <form className="rounded-2xl border border-neutral-800 bg-neutral-950 p-6 sm:p-8" onSubmit={(e) => e.preventDefault()}>
        <Field
          label="People doing the repetitive work"
          hint="Anyone spending real time on manual, rules-based tasks."
        >
          <Stepper value={people} setValue={setPeople} min={1} max={1000} step={1} />
        </Field>
        <Field
          label="Hours per person, per week"
          hint="On work that's repetitive enough to hand to an agent."
        >
          <Stepper value={hours} setValue={setHours} min={1} max={60} step={1} suffix="hrs" />
        </Field>
        <Field label="Fully-loaded cost per hour" hint="Salary + overhead, roughly. $55 ≈ a $90k role.">
          <Stepper value={cost} setValue={setCost} min={10} max={500} step={5} prefix="$" />
        </Field>
        <Field
          label={`How much an agent can take over — ${Math.round(rate * 100)}%`}
          hint="60–75% is typical once a manual workflow is well scoped."
        >
          <input
            type="range"
            min={0.2}
            max={0.95}
            step={0.05}
            value={rate}
            onChange={(e) => setRate(Number(e.target.value))}
            className="mt-2 w-full accent-sky-400"
          />
        </Field>
      </form>

      {/* Result */}
      <div className="rounded-2xl border border-sky-900/50 bg-sky-950/20 p-6 sm:p-8">
        <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
          Estimated annual savings
        </div>
        <div className="mt-2 text-5xl font-semibold tracking-tight text-white tabular-nums sm:text-6xl">
          {usd(annualCostSaved)}
        </div>
        <p className="mt-2 text-[13px] text-neutral-400">per year, once the agents are running</p>

        <div className="mt-7 grid grid-cols-3 gap-3">
          <Stat value={num(annualHoursSaved)} label="hours reclaimed / yr" />
          <Stat value={num(weeklyHoursSaved)} label="hours back / week" />
          <Stat value={fte.toFixed(1)} label="full-time roles freed" />
        </div>

        <div className="mt-7 flex flex-wrap items-center gap-3 border-t border-sky-900/40 pt-6">
          <a href={SITE.calUrl} target="_blank" rel="noreferrer" className={PRIMARY}>
            Book a call to scope it →
          </a>
          <button type="button" onClick={copyLink} className={SECONDARY}>
            {copied ? "Link copied" : "Share these numbers"}
          </button>
        </div>
        <p className="mt-5 text-[13px] leading-relaxed text-neutral-500">
          Not sure which tasks qualify?{" "}
          <a href="/audit" className="text-sky-400 underline-offset-2 hover:underline">
            Run the free AI audit
          </a>{" "}
          — an agent reads your site and names the 3 highest-impact ones.
        </p>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-6 last:mb-0">
      <label className="block text-sm font-medium text-white">{label}</label>
      {children}
      <p className="mt-1.5 text-[12px] leading-relaxed text-neutral-500">{hint}</p>
    </div>
  );
}

function Stepper({
  value,
  setValue,
  min,
  max,
  step,
  prefix,
  suffix,
}: {
  value: number;
  setValue: (n: number) => void;
  min: number;
  max: number;
  step: number;
  prefix?: string;
  suffix?: string;
}) {
  const clamp = (n: number) => Math.min(max, Math.max(min, n));
  const btn =
    "h-9 w-9 shrink-0 rounded-lg border border-neutral-800 bg-neutral-900 text-lg text-neutral-300 transition-colors hover:border-neutral-600 hover:text-white";
  return (
    <div className="mt-2 flex items-center gap-2">
      <button type="button" aria-label="decrease" className={btn} onClick={() => setValue(clamp(value - step))}>
        −
      </button>
      <div className="flex flex-1 items-center justify-center rounded-lg border border-neutral-800 bg-neutral-950 px-3 py-2 text-[15px] font-medium tabular-nums text-white">
        {prefix}
        {num(value)}
        {suffix ? <span className="ml-1 text-neutral-500">{suffix}</span> : null}
      </div>
      <button type="button" aria-label="increase" className={btn} onClick={() => setValue(clamp(value + step))}>
        +
      </button>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3 text-center">
      <div className="text-xl font-semibold tabular-nums text-white">{value}</div>
      <div className="mt-0.5 text-[11px] leading-tight text-neutral-500">{label}</div>
    </div>
  );
}
