import type { Metadata } from "next";
import Link from "next/link";

import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "An autonomous outreach engine that runs a consulting pipeline",
  description:
    "How we built a multi-channel AI-agent system that sources, qualifies, writes, sends, and triages prospects — daily, unattended, in production.",
};

const DECISIONS = [
  {
    h: "Cost-engineered by design",
    p: "LLM scoring gates the expensive steps, so no credit is spent on a poor-fit lead. Email reveals are held to one credit each. Prompt caching keeps a campaign's context warm across a batch. The whole pipeline runs on free-tier compute, database, and hosting plus metered LLM spend.",
  },
  {
    h: "Account safety as a first-class constraint",
    p: "LinkedIn and email each carry rolling-window rate limits, per-mailbox warmup ramps, and per-campaign fair-share caps — because the failure mode that matters most isn't a bug, it's a banned account or a burned sending domain.",
  },
  {
    h: "Deliverability as engineering",
    p: "Plain-text bodies, one-tap unsubscribe headers, domain-aligned message IDs, mailbox warmup, automatic bounce-pausing, and a filter that recognizes and discards warmup-network traffic so it never pollutes the real inbox.",
  },
  {
    h: "Idempotent and durable",
    p: "Every send checks for a prior send; every contact is recorded in a database-backed ledger that survives ephemeral compute. Re-runs are safe by construction.",
  },
  {
    h: "Multi-tenant from the foundation",
    p: "Per-user account routing so a teammate's leads send from their own connected accounts, with row-level security on every table that holds credentials or personal data.",
  },
  {
    h: "Dynamic targeting",
    p: "Audience and offer are data, not code: a campaign carries its own profile, pitch, and voice, so pointing the whole machine at a new market is a config change, not a rewrite.",
  },
];

export default function CaseStudy() {
  return (
    <article className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
      <Link href="/writing" className="text-sm text-neutral-500 transition-colors hover:text-white">
        ← Writing
      </Link>

      <div className="mt-6 text-[11px] font-medium uppercase tracking-[0.18em] text-sky-400">
        Case study
      </div>
      <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight text-white sm:text-4xl">
        An autonomous outreach engine that runs a consulting pipeline
      </h1>
      <p className="mt-4 text-lg leading-relaxed text-neutral-400">
        A multi-channel AI-agent system that sources, qualifies, writes, sends, and triages —
        daily, unattended. Built in-house, in production.
      </p>

      <div className="mt-8 rounded-2xl border border-neutral-800 bg-neutral-950 p-6">
        <div className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">TL;DR</div>
        <p className="mt-2 text-[15px] leading-relaxed text-neutral-300">
          We built an autonomous system that runs our own consulting pipeline end to end: it sources
          prospects from LinkedIn and email, scores each one against a target profile with an LLM,
          writes a personalized opener, sends across channels under human-safe rate limits, detects
          and classifies replies, and drafts responses for us to approve. It runs on hourly crons
          with no human in the loop until a real prospect replies — and it&apos;s a working
          demonstration of exactly what we build for clients.
        </p>
      </div>

      <H2>The problem</H2>
      <P>
        Independent consultants live and die by pipeline, but cold outreach is a grind: find the
        right people, research each one, write something that doesn&apos;t read like a template,
        send it without torching your sender reputation or your LinkedIn account, then actually
        notice and respond when someone bites. Done by hand it&apos;s hours a day. Done by a generic
        SaaS tool it&apos;s spammy and converts poorly.
      </P>
      <P>
        We wanted a system that did the boring 95% autonomously and only surfaced the 5% that needs
        a human: a real reply from a real prospect.
      </P>

      <H2>What we built</H2>
      <P>A closed loop that runs on a schedule:</P>
      <p className="my-5 rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3 text-center font-mono text-[13px] text-sky-300">
        source → score → draft → send → detect reply → triage → follow up
      </p>
      <ul className="mt-4 space-y-3">
        <Bullet label="Sourcing">
          Structured LinkedIn Sales Navigator searches and a verified-email path, with a durable
          ledger so the system never re-scores or re-contacts anyone.
        </Bullet>
        <Bullet label="Scoring">
          Each prospect is scored against an ideal-customer profile by an LLM before any money is
          spent or any message goes out. Spend is gated behind fit.
        </Bullet>
        <Bullet label="Drafting">
          Personalized, per-channel copy generated from the prospect&apos;s profile and a
          campaign-specific offer and voice. Reader-first, plain-text, no template smell.
        </Bullet>
        <Bullet label="Sending">
          LinkedIn connects, DMs, and InMail plus cold email over a rotating mailbox fleet — all
          under caps that mirror the platforms&apos; own limits, so accounts stay safe.
        </Bullet>
        <Bullet label="Reply triage">
          A unified inbox sweeps every mailbox, filters noise, matches real replies to the lead,
          classifies intent with an LLM, and drafts a suggested response for approval.
        </Bullet>
        <Bullet label="Follow-ups">
          Multi-step cadences that fire on a timer, stop the instant someone replies, and back off
          automatically on a bounce.
        </Bullet>
      </ul>

      <H2>Engineering decisions worth calling out</H2>
      <P>What makes this a production system and not a script:</P>
      <div className="mt-5 space-y-5">
        {DECISIONS.map((d) => (
          <div key={d.h}>
            <h3 className="text-base font-semibold text-white">{d.h}</h3>
            <p className="mt-1.5 text-[15px] leading-relaxed text-neutral-400">{d.p}</p>
          </div>
        ))}
      </div>

      <H2>The stack</H2>
      <P>
        Python workers on scheduled serverless compute, Postgres, a Next.js dashboard on Vercel, the
        Anthropic API for scoring and drafting and reply triage, a unified LinkedIn + email API for
        sending and enrichment, and email verification and warmup tooling. One person, end to end.
      </P>

      <H2>Status &amp; what it demonstrates</H2>
      <P>
        The system is live and running daily — sourcing across multiple campaigns and sending across
        LinkedIn and email on autopilot, with email volume deliberately throttled while new domains
        finish warming. Reply results compound as that warmup completes and the funnel fills.
      </P>
      <P>
        More to the point: it&apos;s a working demonstration of exactly what we build for clients — a
        real, autonomous, multi-channel AI-agent system with the unglamorous production concerns
        handled, not hand-waved. Most people selling &ldquo;AI agents&rdquo; can show you a demo. We
        can show you one we trust enough to run our own business on.
      </P>

      <div className="mt-12 rounded-2xl border border-neutral-800 bg-neutral-950 p-6 text-center sm:p-8">
        <p className="text-lg font-medium text-white">Want one of these for your team?</p>
        <div className="mt-5">
          <a
            href={SITE.calUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center rounded-full bg-sky-400 px-5 py-2.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
          >
            Book a call
          </a>
        </div>
      </div>
    </article>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-12 text-xl font-semibold tracking-tight text-white">{children}</h2>;
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 text-[15px] leading-relaxed text-neutral-400">{children}</p>;
}

function Bullet({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-3 text-[15px] leading-relaxed text-neutral-400">
      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-sky-400" />
      <span>
        <span className="font-medium text-neutral-200">{label}.</span> {children}
      </span>
    </li>
  );
}
