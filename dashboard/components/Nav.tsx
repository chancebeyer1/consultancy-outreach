import Link from "next/link";
import { dataSource } from "../lib/supabase";

const links = [
  { href: "/drafts", label: "Drafts" },
  { href: "/leads", label: "Leads" },
  { href: "/replies", label: "Replies" },
  { href: "/sequences", label: "Sequences" },
];

const sourceColor = {
  mock: "text-amber-400",
  file: "text-sky-400",
  supabase: "text-emerald-400",
} as const;

export function Nav() {
  return (
    <header className="border-b border-neutral-800">
      <div className="mx-auto flex max-w-7xl items-center gap-8 px-6 py-3">
        <Link href="/" className="font-mono text-sm font-bold tracking-wide">
          OUTREACH
        </Link>
        <nav className="flex gap-5 text-sm text-neutral-400">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-white">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className={`ml-auto font-mono text-[10px] uppercase tracking-wide ${sourceColor[dataSource]}`}>
          source · {dataSource}
        </div>
      </div>
    </header>
  );
}
