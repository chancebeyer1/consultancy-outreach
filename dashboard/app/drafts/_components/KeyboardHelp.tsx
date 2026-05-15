"use client";

interface Props {
  onClose: () => void;
}

const shortcuts = [
  ["j  ↓", "Next lead"],
  ["k  ↑", "Previous lead"],
  ["a", "Approve all drafts for current lead"],
  ["r", "Reject all drafts for current lead"],
  ["? /", "Toggle this help"],
  ["Esc", "Close help / cancel edit"],
];

export function KeyboardHelp({ onClose }: Props) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-96 rounded-lg border border-neutral-700 bg-neutral-950 p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-neutral-400">
          Keyboard shortcuts
        </h2>
        <ul className="space-y-2">
          {shortcuts.map(([keys, desc]) => (
            <li key={keys} className="flex items-center justify-between text-sm">
              <span className="kbd">{keys}</span>
              <span className="text-neutral-400">{desc}</span>
            </li>
          ))}
        </ul>
        <button
          onClick={onClose}
          className="mt-5 w-full rounded-md border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-900"
        >
          Close
        </button>
      </div>
    </div>
  );
}
