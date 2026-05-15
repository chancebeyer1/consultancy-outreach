export default function RepliesPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold">Replies</h1>
      <p className="mt-2 text-neutral-500">
        Inbound triage. LLM-classified intent + suggested response drafts to approve.
      </p>
      <div className="mt-8 rounded-md border border-dashed border-neutral-800 p-6 text-sm text-neutral-500">
        TODO Phase 2: stream from Heyreach + Smartlead reply webhooks.
      </div>
    </div>
  );
}
