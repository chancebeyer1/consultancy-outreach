// File-mode loader for replies. Reads runs/replies.jsonl (written by
// backend/scripts/pull_replies.py) and maps each record into a
// ReplyReviewRow the UI can consume.
//
// Server-side only (uses fs). Triggered when NEXT_PUBLIC_DATA_SOURCE=file.

import "server-only";

import fs from "node:fs/promises";
import path from "node:path";

import type { Channel, Intent, Lead, Reply, ReplyReviewRow } from "./types";

const ROOT = process.env.PIPELINE_OUTPUT_DIR ?? path.resolve(process.cwd(), "../backend/runs");
const REPLIES_PATH = path.join(ROOT, "replies.jsonl");

interface RepliesJsonlRecord {
  message_id: string;
  conversation_id?: string;
  linkedin_url?: string | null;
  lead_name?: string | null;
  lead_company?: string | null;
  campaign_id?: string | null;
  channel?: Channel;
  body: string;
  original_message?: string | null;
  received_at: string;
  classified_at?: string;
  intent?: Intent | null;
  sentiment?: Reply["sentiment"];
  summary?: string | null;
  suggested_reply?: string | null;
  next_action?: Reply["next_action"];
}

function syntheticLead(rec: RepliesJsonlRecord): Lead {
  return {
    id: `reply-${rec.message_id}`,
    linkedin_url: rec.linkedin_url ?? "",
    name: rec.lead_name ?? null,
    headline: null,
    company: rec.lead_company ?? null,
    company_domain: null,
    role: null,
    location: null,
    segment: null,
    source: null,
    trigger: null,
    status: "replied",
    notes: null,
    created_at: rec.received_at,
    updated_at: rec.received_at,
  };
}

function mapRecord(rec: RepliesJsonlRecord): ReplyReviewRow {
  const reply: Reply = {
    id: rec.message_id,
    lead_id: `reply-${rec.message_id}`,
    channel: rec.channel ?? "linkedin_dm",
    body: rec.body,
    sentiment: rec.sentiment ?? null,
    intent: rec.intent ?? null,
    summary: rec.summary ?? null,
    suggested_reply: rec.suggested_reply ?? null,
    next_action: rec.next_action ?? null,
    handled_at: null,
    received_at: rec.received_at,
  };
  return {
    reply,
    lead: syntheticLead(rec),
    original_message: rec.original_message ?? null,
  };
}

export async function loadReplyRowsFromFile(): Promise<ReplyReviewRow[]> {
  try {
    const text = await fs.readFile(REPLIES_PATH, "utf-8");
    const rows: ReplyReviewRow[] = [];
    for (const line of text.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        rows.push(mapRecord(JSON.parse(trimmed) as RepliesJsonlRecord));
      } catch {
        // skip malformed lines
      }
    }
    // Sort: newest received first; unhandled before handled.
    rows.sort((a, b) => {
      if (!a.reply.handled_at && b.reply.handled_at) return -1;
      if (a.reply.handled_at && !b.reply.handled_at) return 1;
      return b.reply.received_at.localeCompare(a.reply.received_at);
    });
    return rows;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}
