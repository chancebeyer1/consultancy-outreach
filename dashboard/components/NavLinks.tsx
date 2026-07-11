"use client";

import clsx from "clsx";
import Link from "next/link";
import { usePathname } from "next/navigation";

// Client child of the (server) Nav so we can highlight the active route. Active = current path
// or a sub-route of it (e.g. /leads matches /leads/123).
export function NavLinks({ links }: { links: { href: string; label: string }[] }) {
  const pathname = usePathname();
  return (
    <>
      {links.map((l) => {
        const active = pathname === l.href || pathname.startsWith(`${l.href}/`);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors",
              active
                ? "border-sky-400 text-white"
                : "border-transparent text-neutral-400 hover:border-neutral-700 hover:text-neutral-100",
            )}
          >
            {l.label}
          </Link>
        );
      })}
    </>
  );
}
