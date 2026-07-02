"use client";

import { useState } from "react";

export function SettingsClient({ operatorBio }: { operatorBio: string }) {
  const [bio, setBio] = useState(operatorBio);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operatorBio: bio }),
      });
      const data = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string };
      if (!res.ok || !data.ok) {
        setError(data.error || `Save failed (${res.status})`);
        return;
      }
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-5">
      <label className="text-sm font-medium text-neutral-200">About you (AI context)</label>
      <p className="mt-1 text-xs leading-relaxed text-neutral-500">
        Facts the AI treats as <span className="text-neutral-300">true</span> about you — name, school, work history,
        expertise. It uses these to ground replies and outreach so it responds authentically (e.g. engaging a fellow
        Cal Lutheran alum instead of denying the connection). Add anything worth referencing: your degree, past roles,
        notable projects, how you like to come across.
      </p>
      <textarea
        value={bio}
        onChange={(e) => {
          setBio(e.target.value);
          setSaved(false);
        }}
        rows={11}
        className="mt-3 w-full resize-y rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm leading-relaxed text-neutral-100 focus:border-sky-500 focus:outline-none"
        placeholder="e.g. Chance Beyer — founder & software engineer, Santa Monica. Attended Cal Lutheran University (CLU). Builds production AI agents for clients…"
      />
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {saved && <span className="text-sm text-emerald-400">Saved ✓ — the AI uses this on the next draft.</span>}
        {error && <span className="text-sm text-red-400">{error}</span>}
      </div>
    </div>
  );
}
