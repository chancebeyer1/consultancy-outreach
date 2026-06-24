import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

type CookieToSet = { name: string; value: string; options?: CookieOptions };

// Refreshes the Supabase auth session on every request so login persists. NOT enforcing yet
// (no redirect) — that's a one-line add once the accounts exist and per-user scoping (RLS) is
// wired, so the dashboard can't break in the meantime. In mock/file mode it's a no-op.
export async function middleware(request: NextRequest) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  let response = NextResponse.next({ request });
  if (!url || !anon) return response;

  const supabase = createServerClient(url, anon, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: (cookiesToSet: CookieToSet[]) => {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });

  // Touch the session so an expiring token gets refreshed into the response cookies.
  await supabase.auth.getUser();
  return response;
}

export const config = {
  // Run on app routes; skip static assets, the login page, and API routes.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|login|api).*)"],
};
