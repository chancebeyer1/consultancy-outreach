import type { ReactNode } from "react";

/**
 * Compact, consistent page header used across the dashboard. Smaller than the old per-page
 * text-2xl blocks so the content — not the title — leads. Pass `children` for right-aligned
 * actions (filters, buttons).
 */
export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-x-4 gap-y-2 border-b border-neutral-800/80 pb-3">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold tracking-tight text-neutral-100">{title}</h1>
        {description ? (
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-neutral-500">{description}</p>
        ) : null}
      </div>
      {children ? <div className="flex shrink-0 items-center gap-2">{children}</div> : null}
    </header>
  );
}
