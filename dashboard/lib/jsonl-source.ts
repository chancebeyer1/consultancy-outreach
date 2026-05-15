// Reads the latest `runs/*.jsonl` produced by backend/scripts/run_pipeline.py
// and maps each record into the dashboard's DraftReviewRow shape.
//
// Server-side only (uses fs). Triggered when NEXT_PUBLIC_DATA_SOURCE=file.

import "server-only";

import fs from "node:fs/promises";
import path from "node:path";
import type {
  Channel,
  Draft,
  DraftReviewRow,
  Hook,
  Lead,
  Score,
  Segment,
} from "./types";

const ROOT = process.env.PIPELINE_OUTPUT_DIR ?? path.resolve(process.cwd(), "../backend/runs");

interface PipelineHook {
  type: string;
  reference: string;
  why_it_matters: string;
  signal_strength: number;
}

interface PipelineScore {
  fit_score: number;
  segment?: Segment;
  rationale?: string;
  strong_signals?: string[];
  disqualifiers?: string[];
}

interface PipelineRecord {
  linkedin_url: string;
  processed_at: string;
  status?: "ok" | "failed";
  error?: string;
  enrichment?: {
    profile?: Record<string, unknown>;
    recent_posts?: Array<{ text?: string }>;
    company_signals?: Record<string, Array<{ title?: string }>>;
    github?: { top_repos?: Array<{ topics?: string[] }> };
    company?: string;
  };
  score?: PipelineScore;
  hooks?: PipelineHook[];
  chosen_hook?: PipelineHook | null;
  drafts?: Partial<Record<Channel, string>>;
}

async function findLatestJsonl(): Promise<string | null> {
  try {
    const entries = await fs.readdir(ROOT, { withFileTypes: true });
    const files = entries
      .filter((e) => e.isFile() && e.name.endsWith(".jsonl"))
      .map((e) => path.join(ROOT, e.name));
    if (files.length === 0) return null;
    // Pick most recently modified
    const stats = await Promise.all(files.map(async (f) => ({ f, mtime: (await fs.stat(f)).mtimeMs })));
    stats.sort((a, b) => b.mtime - a.mtime);
    return stats[0].f;
  } catch {
    return null;
  }
}

async function readJsonl(filepath: string): Promise<PipelineRecord[]> {
  const text = await fs.readFile(filepath, "utf-8");
  const out: PipelineRecord[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      out.push(JSON.parse(trimmed) as PipelineRecord);
    } catch {
      // skip malformed lines
    }
  }
  return out;
}

function mapRecord(rec: PipelineRecord, idx: number): DraftReviewRow | null {
  if (rec.status === "failed") return null;
  const profile = rec.enrichment?.profile ?? {};
  const company = rec.enrichment?.company ?? null;
  const id = String(idx);

  const lead: Lead = {
    id,
    linkedin_url: rec.linkedin_url,
    name: (profile.full_name as string) ?? null,
    headline: (profile.headline as string) ?? null,
    company,
    company_domain: null,
    role:
      (profile.occupation as string) ??
      ((profile.experiences as Array<{ title?: string }>)?.[0]?.title ?? null),
    location:
      ((profile.city as string) ?? "") +
        (profile.country_full_name ? `, ${profile.country_full_name as string}` : "") ||
      null,
    segment: rec.score?.segment ?? null,
    source: null,
    trigger: "list",
    status: "drafted",
    notes: null,
    created_at: rec.processed_at,
    updated_at: rec.processed_at,
  };

  const score: Score | null = rec.score
    ? {
        lead_id: id,
        fit_score: rec.score.fit_score,
        rationale: rec.score.rationale ?? null,
        model: null,
        scored_at: rec.processed_at,
        strong_signals: rec.score.strong_signals,
        disqualifiers: rec.score.disqualifiers,
      }
    : null;

  const hooks: Hook[] = (rec.hooks ?? []).map((h) => ({ ...h }));

  const drafts: Draft[] = Object.entries(rec.drafts ?? {}).map(([channel, body], i) => ({
    id: `${id}-${channel}`,
    lead_id: id,
    channel: channel as Channel,
    step_index: i,
    hook: null,
    body: body ?? "",
    edited_body: null,
    status: "draft",
    rejection_reason: null,
    variant: null,
    generated_at: rec.processed_at,
    decided_at: null,
  }));

  return {
    lead,
    score,
    drafts,
    hooks,
    enrichment_summary: {
      recent_post_excerpts: (rec.enrichment?.recent_posts ?? [])
        .map((p) => (p.text ?? "").trim())
        .filter((t) => t.length > 0)
        .slice(0, 5),
      company_signal_headlines: Object.values(rec.enrichment?.company_signals ?? {})
        .flatMap((arr) => arr.map((r) => r.title ?? ""))
        .filter((t) => t.length > 0)
        .slice(0, 6),
      github_topics: Array.from(
        new Set(
          (rec.enrichment?.github?.top_repos ?? []).flatMap((r) => r.topics ?? []),
        ),
      ).slice(0, 10),
    },
  };
}

export async function loadDraftReviewRowsFromFile(): Promise<DraftReviewRow[]> {
  const filepath = await findLatestJsonl();
  if (!filepath) {
    return [];
  }
  const records = await readJsonl(filepath);
  return records
    .map((r, i) => mapRecord(r, i))
    .filter((r): r is DraftReviewRow => r !== null);
}
