// Client-only Supabase client. Kept separate from lib/supabase.ts because that module imports
// next/headers (server-only), which can't be pulled into a client component's bundle.
import { createBrowserClient } from "@supabase/ssr";

export function browserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) throw new Error("Supabase env not configured");
  return createBrowserClient(url, anon);
}
