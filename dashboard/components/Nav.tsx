import Link from "next/link";

const links = [
  { href: "/drafts", label: "Drafts" },
  { href: "/leads", label: "Leads" },
  { href: "/replies", label: "Replies" },
  { href: "/sequences", label: "Sequences" },
];

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
        <div className="ml-auto text-xs text-neutral-500">
          {process.env.NEXT_PUBLIC_USE_MOCK_DATA === "1" ? "MOCK DATA" : "LIVE"}
        </div>
      </div>
    </header>
  );
}
