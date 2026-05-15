export default function SequencesPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold">Sequences</h1>
      <p className="mt-2 text-neutral-500">
        Lead-by-lead view of which step they're on, when the next touch fires, pause toggles.
      </p>
      <div className="mt-8 rounded-md border border-dashed border-neutral-800 p-6 text-sm text-neutral-500">
        TODO Phase 3: state machine for connect → DM → email → break, signal-trigger overrides.
      </div>
    </div>
  );
}
