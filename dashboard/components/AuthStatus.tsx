"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { browserClient } from "@/lib/supabase-browser";

export function AuthStatus({ email }: { email: string | null }) {
  const router = useRouter();
  if (!email) {
    return (
      <a href="/login" className="text-xs text-neutral-400 hover:text-white">
        Sign in
      </a>
    );
  }
  async function signOut() {
    await browserClient().auth.signOut();
    router.push("/login");
    router.refresh();
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
