import Link from "next/link";

import { NAV, SITE } from "@/lib/site";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-neutral-800/80 bg-[#0a0a0a]/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-4 px-5 sm:px-8">
        <Link
          href="/"
          className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-white"
        >
          <span className="h-2.5 w-2.5 rounded-full bg-sky-400" />
          {SITE.name}
        </Link>
        <nav className="hidden items-center gap-7 text-sm text-neutral-400 sm:flex">
          {NAV.map((l) => (
            <Link key={l.href} href={l.href} className="transition-colors hover:text-white">
              {l.label}
            </Link>
          ))}
        </nav>
        <a
          href={SITE.calUrl}
          target="_blank"
          rel="noreferrer"
          className="rounded-full bg-sky-400 px-4 py-1.5 text-sm font-medium text-neutral-950 transition-colors hover:bg-sky-300"
        >
          Book a call
        </a>
      </div>
    </header>
  );
}
