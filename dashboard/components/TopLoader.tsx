"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

// Global route-change progress bar. Every dashboard page is a `force-dynamic` server component, so
// clicking a nav tab kicks off a server round-trip with NO visual feedback until it finishes — which
// reads as "nothing happened, then the page jumped." This gives instant feedback: a thin bar starts
// creeping the moment you click an internal link (or hit back/forward), then snaps to 100% and fades
// the instant the new route commits (usePathname/useSearchParams update only once navigation lands).
//
// It's purely an overlay — it never blocks input and fails open (a safety timeout always clears it),
// so a hung navigation can't leave the bar stuck.
export function TopLoader() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [width, setWidth] = useState(0);
  const [visible, setVisible] = useState(false);

  const active = useRef(false);
  const trickle = useRef<ReturnType<typeof setInterval> | null>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  function clearTimers() {
    if (trickle.current) {
      clearInterval(trickle.current);
      trickle.current = null;
    }
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }

  function start() {
    if (active.current) return;
    active.current = true;
    clearTimers();
    setVisible(true);
    setWidth(8);
    // Creep toward ~90% while we wait — fast at first, then slower, so it always looks like progress
    // without ever reaching the end before the route actually commits.
    trickle.current = setInterval(() => {
      setWidth((w) => {
        if (w >= 90) return w;
        const step = w < 40 ? 9 : w < 65 ? 4 : w < 80 ? 2 : 0.5;
        return Math.min(90, w + step);
      });
    }, 350);
    // Fail open: never let the bar hang if a navigation stalls or errors.
    timers.current.push(setTimeout(finish, 20000));
  }

  function finish() {
    if (!active.current) return;
    active.current = false;
    clearTimers();
    setWidth(100);
    timers.current.push(
      setTimeout(() => {
        setVisible(false);
        timers.current.push(setTimeout(() => setWidth(0), 250));
      }, 250),
    );
  }

  // Start on any internal <a> navigation. Capture phase so we run before Next's Link handler (which
  // preventDefaults and takes over), and we skip new-tab / modified / external / same-URL clicks.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return;
      }
      const anchor = (e.target as HTMLElement | null)?.closest("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
      if (href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return;
      let url: URL;
      try {
        url = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) return;
      // Same page (or hash on the same page): no navigation to wait on.
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      start();
    }
    function onPopState() {
      start();
    }
    document.addEventListener("click", onClick, true);
    window.addEventListener("popstate", onPopState);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("popstate", onPopState);
      clearTimers();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The route committed (pathname/search changed) — the new page is on screen, so complete the bar.
  // Runs once on mount too, where finish() is a no-op because nothing is active.
  useEffect(() => {
    finish();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, searchParams]);

  if (!visible && width === 0) return null;

  return (
    <div
      aria-hidden
      data-top-loader
      className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-0.5"
      style={{ opacity: visible ? 1 : 0, transition: "opacity 250ms ease" }}
    >
      <div
        className="h-full bg-sky-400"
        style={{
          width: `${width}%`,
          transition: "width 350ms ease",
          boxShadow: "0 0 8px rgba(56,189,248,0.8), 0 0 4px rgba(56,189,248,0.6)",
        }}
      />
    </div>
  );
}
