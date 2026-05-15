import { createBrowserClient, createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const useMockData =
  !url || !anon || process.env.NEXT_PUBLIC_USE_MOCK_DATA === "1";

export function browserClient() {
  if (useMockData) {
    throw new Error(
      "Mock data mode: don't call browserClient(). Use the mock-data layer instead.",
    );
  }
  return createBrowserClient(url!, anon!);
}

export async function serverClient() {
  if (useMockData) {
    throw new Error(
      "Mock data mode: don't call serverClient(). Use the mock-data layer instead.",
    );
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
