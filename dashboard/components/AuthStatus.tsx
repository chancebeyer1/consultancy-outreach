"use client";

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
      <span className="hidden max-w-[140px] truncate text-[11px] text-neutral-500 md:inline">{email}</span>
      <button onClick={signOut} className="text-xs text-neutral-400 hover:text-white">
        Sign out
      </button>
    </div>
  );
}
