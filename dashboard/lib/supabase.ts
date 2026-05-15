import { createBrowserClient, createServerClient } from "@supabase/ssr";
import { createClient } from "@supabase/supabase-js";
import { cookies } from "next/headers";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const serviceRole = process.env.SUPABASE_SERVICE_ROLE_KEY;

// Data source resolution. Defaults sensibly:
//   - explicit override:        NEXT_PUBLIC_DATA_SOURCE = "mock" | "file" | "supabase"
//   - legacy mock flag:         NEXT_PUBLIC_USE_MOCK_DATA = "1"
//   - else if Supabase env set: "supabase"
//   - else:                     "mock"
export type DataSource = "mock" | "file" | "supabase";

export const dataSource: DataSource = (() => {
  const explicit = process.env.NEXT_PUBLIC_DATA_SOURCE as DataSource | undefined;
  if (explicit) return explicit;
  if (process.env.NEXT_PUBLIC_USE_MOCK_DATA === "1") return "mock";
  if (url && anon) return "supabase";
  return "mock";
})();

// Back-compat with earlier usage.
export const useMockData = dataSource === "mock";

export function browserClient() {
  if (dataSource !== "supabase") {
    throw new Error(`Don't call browserClient() in data source mode "${dataSource}".`);
  }
  return createBrowserClient(url!, anon!);
}

export async function serverClient() {
  if (dataSource !== "supabase") {
    throw new Error(`Don't call serverClient() in data source mode "${dataSource}".`);
  }
  const cookieStore = await cookies();
  return createServerClient(url!, anon!, {
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: () => {
        /* read-only in server components */
      },
    },
  });
}

/**
 * Server-side admin client (service role key, bypasses RLS).
 *
 * Use ONLY in route handlers / server actions for mutations the operator
 * (you) triggers from the dashboard. Never expose this to the browser.
 * If you ever add real auth, swap this for a user-scoped client.
 */
export function serverAdminClient() {
  if (dataSource !== "supabase") {
    throw new Error(`Don't call serverAdminClient() in data source mode "${dataSource}".`);
  }
  if (!serviceRole) {
    throw new Error(
      "SUPABASE_SERVICE_ROLE_KEY not set. Required for dashboard writes against Supabase.",
    );
  }
  return createClient(url!, serviceRole, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
