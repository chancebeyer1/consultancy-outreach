import clsx from "clsx";

import { requireAdmin } from "../../lib/auth";
import { PageHeader } from "../../components/PageHeader";
import { getSelectedCampaignId } from "../../lib/campaign-filter";
import { getSequenceRows } from "../../lib/queries";

const CHANNEL_LABEL: Record<string, string> = {
  linkedin_connect: "Connect",
  linkedin_dm: "DM",
  linkedin_followup_1: "Follow-up 1",
  linkedin_followup_2: "Follow-up 2",
  email: "Email",
  email_followup_1: "Email follow-up 1",
  email_followup_2: "Email follow-up 2",
};

export default async function SequencesPage() {
  await requireAdmin();
  const campaignId = await getSelectedCampaignId();
  const rows = await getSequenceRows(campaignId);

  if (rows.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center text-neutral-500">
        <h1 className="text-2xl font-semibold text-neutral-200">Sequences</h1>
        <p className="mt-3">
          No leads in a sequence yet. Once connection requests go out, each lead appears here with
          its step-by-step progress and what fires next.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <PageHeader
        title="Sequences"
        description={`${rows.length} lead${rows.length === 1 ? "" : "s"} in flight — each one's outbound steps and what fires next. Pause a campaign to halt its sequences.`}
      />

      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.lead.id} className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <a
                  href={r.lead.linkedin_url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-neutral-100 hover:text-sky-400 hover:underline"
                >
                  {r.lead.name ?? "—"}
                </a>
                <div className="truncate text-xs text-neutral-500">
                  {r.lead.company ?? ""}
                  {r.lead.role ? ` · ${r.lead.role}` : ""}
                </div>
              </div>
              <span
                className={clsx(
                  "shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium",
                  r.has_reply
                    ? "bg-emerald-900/50 text-emerald-300"
                    : "bg-neutral-800 text-neutral-300",
                )}
              >
                {r.awaiting}
              </span>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {r.steps.map((s, i) => (
                <div key={i} className="flex items-center gap-1.5">
                  {i > 0 && <span className="text-neutral-600">→</span>}
                  <span className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs">
                    <span className="text-neutral-300">{CHANNEL_LABEL[s.channel] ?? s.channel}</span>
                    <span className="ml-2 font-mono text-neutral-500">
                      {new Date(s.sent_at).toISOString().slice(0, 10)}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
