import Link from "next/link";

// Shared server/client pagination control. Renders Newer/Older links that set `?page=N` on the
// given path (preserving any other query params passed in `extraParams`). Works in both server
// components and client components. Returns null for single-page result sets.
export function Pager({
  basePath,
  page,
  totalPages,
  total,
  pageSize,
  unit = "items",
  scroll = true,
  extraParams,
}: {
  basePath: string;
  page: number;
  totalPages: number;
  total?: number;
  pageSize?: number;
  unit?: string;
  scroll?: boolean;
  extraParams?: Record<string, string | undefined>;
}) {
  if (totalPages <= 1) return null;

  const href = (p: number) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(extraParams ?? {})) if (v) params.set(k, v);
    if (p > 1) params.set("page", String(p));
    const qs = params.toString();
    return qs ? `${basePath}?${qs}` : basePath;
  };

  const rangeLabel =
    total != null && pageSize != null
      ? `${((page - 1) * pageSize + 1).toLocaleString()}–${Math.min(page * pageSize, total).toLocaleString()} of ${total.toLocaleString()} ${unit}`
      : `Page ${page} of ${totalPages}`;

  const btn = "rounded-md border px-3 py-1.5 text-xs transition";
  const enabled = "border-neutral-700 text-neutral-200 hover:bg-neutral-900";
  const disabled = "border-neutral-800 text-neutral-600 pointer-events-none";

  return (
    <div className="mt-4 flex items-center justify-between gap-3 text-sm text-neutral-400">
      <span className="text-xs text-neutral-500">{rangeLabel}</span>
      <div className="flex items-center gap-2">
        {page > 1 ? (
          <Link href={href(page - 1)} scroll={scroll} className={`${btn} ${enabled}`}>
            ← Newer
          </Link>
        ) : (
          <span className={`${btn} ${disabled}`}>← Newer</span>
        )}
        <span className="text-xs text-neutral-500">
          {page} / {totalPages}
        </span>
        {page < totalPages ? (
          <Link href={href(page + 1)} scroll={scroll} className={`${btn} ${enabled}`}>
            Older →
          </Link>
        ) : (
          <span className={`${btn} ${disabled}`}>Older →</span>
        )}
      </div>
    </div>
  );
}
