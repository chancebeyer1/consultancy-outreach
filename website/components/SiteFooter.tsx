import Link from "next/link";

import { NAV, SITE } from "@/lib/site";
import { VERTICALS } from "@/lib/verticals";

export function SiteFooter() {
  return (
    <footer className="border-t border-neutral-800/80">
      <div className="mx-auto flex max-w-5xl flex-col gap-8 px-5 py-12 sm:flex-row sm:items-start sm:justify-between sm:px-8">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <span className="h-2 w-2 rounded-full bg-sky-400" />
            {SITE.name}
          </div>
          <p className="mt-2 max-w-xs text-xs leading-relaxed text-neutral-500">{SITE.tagline}</p>
        </div>
        <div className="flex flex-col gap-2 text-sm text-neutral-400">
          {NAV.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-white">
              {l.label}
            </Link>
          ))}
          <a href={`mailto:${SITE.email}`} className="hover:text-white">
            {SITE.email}
          </a>
        </div>
        {/* Industries column — the crawl path into the programmatic vertical pages. */}
        <div className="flex flex-col gap-2 text-sm text-neutral-400">
          <span className="text-xs font-semibold uppercase tracking-wide text-neutral-600">
            AI agents for
          </span>
          {VERTICALS.slice(0, 6).map((v) => (
            <Link key={v.slug} href={`/ai-agents-for/${v.slug}`} className="hover:text-white">
              {v.title.replace(/^AI Agents for /, "")}
            </Link>
          ))}
          <Link href="/ai-agents-for" className="text-sky-400 hover:text-sky-300">
            all industries →
          </Link>
        </div>
      </div>
      <div className="border-t border-neutral-900 py-5 text-center text-[11px] text-neutral-600">
        © {SITE.name} — built with the same stack we ship for clients.
      </div>
    </footer>
  );
}
