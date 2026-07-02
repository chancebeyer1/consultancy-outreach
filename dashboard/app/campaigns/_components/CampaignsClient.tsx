"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import type { Campaign } from "@/lib/types";

interface Props {
  initialCampaigns: Campaign[];
  writable: boolean;
  mode: "mock" | "file" | "supabase";
}

type FormState = {
  id: string | null;
  name: string;
  slug: string;
  status: "active" | "paused" | "archived";
  is_default: boolean;
  auto_send: boolean;
  inmail_min_fit: number | null;
  landing_url: string;
  calcom_url: string;
  icp_md: string;
  offer_md: string;
  style_md: string;
  voice_md: string;
};

const BLANK: FormState = {
  id: null,
  name: "",
  slug: "",
  status: "active",
  is_default: false,
  auto_send: false,
  inmail_min_fit: null,
  landing_url: "",
  calcom_url: "",
  icp_md: "",
  offer_md: "",
  style_md: "",
  voice_md: "",
};

function toForm(c: Campaign): FormState {
  return {
    id: c.id,
    name: c.name ?? "",
    slug: c.slug ?? "",
    status: c.status ?? "active",
    is_default: c.is_default ?? false,
    auto_send: c.auto_send ?? false,
    inmail_min_fit: c.inmail_min_fit ?? null,
    landing_url: c.landing_url ?? "",
    calcom_url: c.calcom_url ?? "",
    icp_md: c.icp_md ?? "",
    offer_md: c.offer_md ?? "",
    style_md: c.style_md ?? "",
    voice_md: c.voice_md ?? "",
  };
}

export function CampaignsClient({ initialCampaigns, writable, mode }: Props) {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(BLANK);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setOk(false);
  }

  // One-click pause/resume from the list — posts the full campaign with status
  // flipped so no other fields are touched. Paused campaigns stop sourcing + sending.
  async function toggleStatus(c: Campaign) {
    const next = c.status === "active" ? "paused" : "active";
    setError(null);
    try {
      const res = await fetch("/api/campaigns", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...toForm(c), status: next }),
      });
      const json = await res.json();
      if (!res.ok || json.persisted === false) {
        throw new Error(json.error ?? json.reason ?? `HTTP ${res.status}`);
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    setOk(false);
    try {
      const res = await fetch("/api/campaigns", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(form),
      });
      const json = await res.json();
      if (!res.ok || json.persisted === false) {
        throw new Error(json.error ?? json.reason ?? `HTTP ${res.status}`);
      }
      setOk(true);
      setForm((f) => ({ ...f, id: json.id ?? f.id }));
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <PageHeader
        title="Campaigns"
        description="A campaign is a persona bundle: audience (ICP) + offer, with optional voice/style overrides. The pipeline targets the selected campaign on its next run."
      />
      {!writable && (
        <p className="-mt-1 mb-5 rounded-md border border-amber-900/60 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          Read-only in <span className="font-mono">{mode}</span> mode. Set{" "}
          <code className="rounded bg-neutral-900 px-1 py-0.5">NEXT_PUBLIC_DATA_SOURCE=supabase</code>{" "}
          (with a service-role key) to create or edit campaigns. Files in{" "}
          <code className="rounded bg-neutral-900 px-1 py-0.5">backend/campaigns/</code> remain the
          versioned seed.
        </p>
      )}

      <div className="grid gap-8 lg:grid-cols-[260px_1fr]">
        {/* List */}
        <aside>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">
              All campaigns
            </h2>
            <button
              type="button"
              onClick={() => {
                setForm(BLANK);
                setOk(false);
                setError(null);
              }}
              className="rounded border border-neutral-700 px-2 py-0.5 text-xs text-neutral-300 hover:bg-neutral-800"
            >
              + New
            </button>
          </div>
          <ul className="space-y-1.5">
            {initialCampaigns.length === 0 && (
              <li className="text-xs italic text-neutral-600">none yet</li>
            )}
            {initialCampaigns.map((c) => (
              <li key={c.id} className="relative">
                <button
                  type="button"
                  onClick={() => {
                    setForm(toForm(c));
                    setOk(false);
                    setError(null);
                  }}
                  className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                    form.id === c.id
                      ? "border-neutral-600 bg-neutral-900"
                      : "border-neutral-800 bg-neutral-950 hover:border-neutral-700"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 pr-16">
                    <span className="truncate">{c.name}</span>
                    {c.is_default && <span className="text-amber-400">★</span>}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-neutral-500">
                    <span>{c.slug ?? "—"}</span>
                    <StatusBadge status={c.status} />
                  </div>
                </button>
                {writable && c.status !== "archived" && (
                  <button
                    type="button"
                    onClick={() => void toggleStatus(c)}
                    title={c.status === "active" ? "Pause — stops sourcing + sending" : "Resume"}
                    className={`absolute right-2 top-2 rounded border px-1.5 py-0.5 text-[10px] font-medium ${
                      c.status === "active"
                        ? "border-amber-800/60 text-amber-400 hover:bg-amber-950/40"
                        : "border-emerald-800/60 text-emerald-400 hover:bg-emerald-950/40"
                    }`}
                  >
                    {c.status === "active" ? "Pause" : "Resume"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </aside>

        {/* Editor */}
        <section>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Name">
              <input
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                placeholder="Real-estate listing agents"
                className={inputCls}
              />
            </Field>
            <Field label="Slug">
              <input
                value={form.slug}
                onChange={(e) => set("slug", e.target.value)}
                placeholder="real-estate-agents"
                className={`${inputCls} font-mono`}
              />
            </Field>
            <Field label="Status">
              <select
                value={form.status}
                onChange={(e) => set("status", e.target.value as FormState["status"])}
                className={inputCls}
              >
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="archived">Archived</option>
              </select>
            </Field>
            <Field label="Default campaign">
              <label className="flex h-9 items-center gap-2 text-sm text-neutral-300">
                <input
                  type="checkbox"
                  checked={form.is_default}
                  onChange={(e) => set("is_default", e.target.checked)}
                  className="h-4 w-4 accent-amber-500"
                />
                used when no <span className="font-mono text-xs">--campaign</span> is given
              </label>
            </Field>
            <Field label="Landing URL">
              <input
                value={form.landing_url}
                onChange={(e) => set("landing_url", e.target.value)}
                placeholder="blank → LANDING_URL from .env"
                className={`${inputCls} font-mono`}
              />
            </Field>
            <Field label="Cal.com URL">
              <input
                value={form.calcom_url}
                onChange={(e) => set("calcom_url", e.target.value)}
                placeholder="blank → CALCOM_URL from .env"
                className={`${inputCls} font-mono`}
              />
            </Field>
          </div>

          {/* Auto-send toggle — sends first contact without manual review. */}
          <div className="mt-4 rounded-md border border-neutral-800 bg-neutral-950 p-3">
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={form.auto_send}
                onChange={(e) => set("auto_send", e.target.checked)}
                className="mt-0.5 h-4 w-4 accent-emerald-500"
              />
              <span className="text-sm text-neutral-300">
                <span className="font-medium">Auto-send first contact</span>
                <span className="ml-2 rounded bg-amber-950/40 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-amber-400">
                  no manual review
                </span>
                <span className="mt-1 block text-xs text-neutral-500">
                  When on, newly sourced leads&apos; connection notes auto-approve and the sender
                  ships them (still capped at 20/day). Leave off until you trust this campaign&apos;s
                  messages, then flip it to run hands-off.
                </span>
              </span>
            </label>
          </div>

          {/* InMail routing — top-fit leads get a direct InMail instead of a connect. */}
          <div className="mt-3 rounded-md border border-neutral-800 bg-neutral-950 p-3">
            <label className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-neutral-300">
              <span className="font-medium">InMail for fit ≥</span>
              <input
                type="number"
                min={0}
                max={100}
                value={form.inmail_min_fit ?? ""}
                onChange={(e) =>
                  set("inmail_min_fit", e.target.value === "" ? null : Number(e.target.value))
                }
                placeholder="off"
                className="h-8 w-20 rounded-md border border-neutral-800 bg-neutral-950 px-2 text-sm text-neutral-100 outline-none focus:border-neutral-600"
              />
              <span className="text-xs text-neutral-500">
                top-fit leads get a direct InMail (Sales Nav credits) instead of a connection
                request. Blank = off.
              </span>
            </label>
          </div>

          <div className="mt-4 grid gap-4">
            <Field label="ICP — who we're targeting (markdown)">
              <textarea
                value={form.icp_md}
                onChange={(e) => set("icp_md", e.target.value)}
                rows={7}
                placeholder="# ICP&#10;&#10;Independent listing agents doing 20+ deals/yr…"
                className={`${textareaCls}`}
              />
            </Field>
            <Field label="Offer — what we're selling (markdown)">
              <textarea
                value={form.offer_md}
                onChange={(e) => set("offer_md", e.target.value)}
                rows={7}
                placeholder="# Offer&#10;&#10;AI assistant that drafts listing copy + buyer follow-ups…"
                className={`${textareaCls}`}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Style override (blank = global default)">
                <textarea
                  value={form.style_md}
                  onChange={(e) => set("style_md", e.target.value)}
                  rows={5}
                  className={textareaCls}
                />
              </Field>
              <Field label="Voice corpus override (blank = global default)">
                <textarea
                  value={form.voice_md}
                  onChange={(e) => set("voice_md", e.target.value)}
                  rows={5}
                  className={textareaCls}
                />
              </Field>
            </div>
          </div>

          <div className="mt-5 flex items-center gap-3">
            <button
              type="button"
              onClick={save}
              disabled={!writable || saving || form.name.trim().length === 0}
              className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving ? "Saving…" : form.id ? "Save changes" : "Create campaign"}
            </button>
            {ok && <span className="text-sm text-emerald-400">saved ✓</span>}
            {error && <span className="text-sm text-red-400">{error}</span>}
          </div>
        </section>
      </div>
    </div>
  );
}

const inputCls =
  "h-9 w-full rounded-md border border-neutral-800 bg-neutral-950 px-2.5 text-sm text-neutral-100 outline-none focus:border-neutral-600";
const textareaCls =
  "w-full rounded-md border border-neutral-800 bg-neutral-950 px-2.5 py-2 font-mono text-xs leading-relaxed text-neutral-100 outline-none focus:border-neutral-600";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] uppercase tracking-wide text-neutral-500">{label}</span>
      {children}
    </label>
  );
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "active"
      ? "text-emerald-400"
      : status === "paused"
        ? "text-amber-400"
        : "text-neutral-500";
  return <span className={tone}>{status.charAt(0).toUpperCase() + status.slice(1)}</span>;
}
