import Link from "next/link";

import { NAV, SITE } from "@/lib/site";

import { NewsletterSignup } from "./NewsletterSignup";

export function SiteFooter() {
  return (
    <footer className="border-t border-neutral-800/80">
      <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8">
        <NewsletterSignup />
      </div>
      <div className="mx-auto flex max-w-5xl flex-col gap-8 border-t border-neutral-900 px-5 py-12 sm:flex-row sm:items-start sm:justify-between sm:px-8">
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
      </div>
      <div className="border-t border-neutral-900 py-5 text-center text-[11px] text-neutral-600">
        © {SITE.name} — built with the same stack we ship for clients.
      </div>
    </footer>
  );
}
