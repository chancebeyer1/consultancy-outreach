"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export type TeamMember = {
  id: string;
  email: string | null;
  name: string | null;
  unipile_account_id: string | null;
  unipile_email_account_id: string | null;
  is_admin: boolean;
  created_at: string | null;
};

const INPUT =
  "w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-sky-500 focus:outline-none";

export function TeamClient({ members }: { members: TeamMember[] }) {
  return (
    <div className="space-y-10">
      <CreateForm />
      <div>
        <h2 className="mb-3 text-sm font-semibold text-neutral-300">Team</h2>
        <div className="space-y-3">
          {members.map((m) => (
            <MemberCard key={m.id} member={m} />
          ))}
          {members.length === 0 && (
            <p className="text-sm italic text-neutral-600">No accounts yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function CreateForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/team", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password, isAdmin }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "failed");
      setMsg({ ok: true, text: `Created ${data.email}. They can sign in now.` });
      setName("");
      setEmail("");
      setPassword("");
      setIsAdmin(false);
      router.refresh();
    } catch (err) {
      setMsg({ ok: false, text: err instanceof Error ? err.message : "failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-neutral-800 bg-neutral-950 p-4 sm:p-5"
    >
      <h2 className="text-sm font-semibold text-neutral-300">Add a teammate</h2>
      <p className="mt-1 text-xs text-neutral-500">
        Creates their login. They can sign in immediately; connect their LinkedIn account-id
        below once they&apos;ve linked it in Unipile.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Jordan"
            className={INPUT}
          />
        </Field>
        <Field label="Email">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="jordan@example.com"
            autoComplete="off"
            className={INPUT}
          />
        </Field>
        <Field label="Temporary password (8+ chars)">
          <input
            type="text"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="share this with them"
            autoComplete="off"
            className={INPUT}
          />
        </Field>
        <label className="flex items-end gap-2 pb-2 text-sm text-neutral-300">
          <input
            type="checkbox"
            checked={isAdmin}
            onChange={(e) => setIsAdmin(e.target.checked)}
            className="h-4 w-4 rounded border-neutral-700 bg-neutral-900"
          />
          Admin (can manage team)
        </label>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-sky-600 px-3 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
        >
          {busy ? "Creating…" : "Create account"}
        </button>
        {msg && (
          <span className={`text-xs ${msg.ok ? "text-emerald-400" : "text-red-400"}`}>
            {msg.text}
          </span>
        )}
      </div>
    </form>
  );
}

function MemberCard({ member }: { member: TeamMember }) {
  const router = useRouter();
  const [li, setLi] = useState(member.unipile_account_id ?? "");
  const [em, setEm] = useState(member.unipile_email_account_id ?? "");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  const dirty = li !== (member.unipile_account_id ?? "") || em !== (member.unipile_email_account_id ?? "");

  async function save() {
    setBusy(true);
    setSaved(null);
    try {
      const res = await fetch("/api/team", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: member.id,
          unipile_account_id: li,
          unipile_email_account_id: em,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "failed");
      setSaved("Saved");
      router.refresh();
    } catch (err) {
      setSaved(err instanceof Error ? err.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-neutral-100">
            {member.name || member.email}{" "}
            {member.is_admin && (
              <span className="ml-1 rounded border border-sky-800 bg-sky-950 px-1.5 py-0.5 font-mono text-[10px] uppercase text-sky-300">
                admin
              </span>
            )}
          </div>
          <div className="font-mono text-[11px] text-neutral-500">{member.email}</div>
        </div>
        <div className="flex items-center gap-2">
          {!member.unipile_account_id && (
            <span className="rounded border border-amber-800 bg-amber-950 px-1.5 py-0.5 font-mono text-[10px] uppercase text-amber-300">
              LinkedIn not connected
            </span>
          )}
        </div>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-neutral-500">
            Unipile LinkedIn account-id
          </span>
          <input
            value={li}
            onChange={(e) => setLi(e.target.value)}
            placeholder="paste from Unipile after they connect"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 font-mono text-xs text-neutral-100 focus:border-sky-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-neutral-500">
            Unipile email account-id <span className="text-neutral-600">(optional)</span>
          </span>
          <input
            value={em}
            onChange={(e) => setEm(e.target.value)}
            placeholder="only if they run email outreach"
            className="mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 font-mono text-xs text-neutral-100 focus:border-sky-500 focus:outline-none"
          />
        </label>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={save}
          disabled={busy || !dirty}
          className="rounded-md border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
        >
          {busy ? "Saving…" : "Save"}
        </button>
        {saved && (
          <span className={`text-xs ${saved === "Saved" ? "text-emerald-400" : "text-red-400"}`}>
            {saved}
          </span>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
