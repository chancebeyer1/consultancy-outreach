"use client";

import Link from "next/link";

import { browserClient } from "@/lib/supabase-browser";

export function AuthStatus({ email }: { email: string | null }) {
  if (!email) {
    return (
      <a href="/login" className="text-xs text-neutral-400 hover:text-white">
        Sign in
      </a>
    );
  }
  async function signOut() {
    await browserClient().auth.signOut();
    // Hard navigation: router.push would keep serving the cached signed-in Nav
    // (full admin tab bar) on /login. A full load renders the signed-out header.
    window.location.assign("/login");
  }
  return (
    <div className="flex items-center gap-2">
      {/* Email doubles as the profile / settings link (replaces the Settings nav tab). */}
      <Link
        href="/settings"
        title="Your profile & settings"
        className="max-w-[160px] truncate text-[11px] text-neutral-400 underline-offset-2 hover:text-white hover:underline"
      >
        {email}
      </Link>
      <button onClick={signOut} className="text-xs text-neutral-400 hover:text-white">
        Sign out
      </button>
    </div>
  );
}
