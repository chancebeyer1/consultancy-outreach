import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

type CookieToSet = { name: string; value: string; options?: CookieOptions };

// Refreshes the Supabase auth session on every request so login persists, AND enforces auth:
// any unauthenticated request to an app route is redirected to /login. In mock/file mode
// (no Supabase env) it's a no-op, so local/offline dev is unaffected. The matcher below
// already exempts /login, /api, and static assets.
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

  // getUser() both refreshes an expiring token (into response cookies) and tells us whether
  // anyone is signed in. No user → bounce to /login, remembering where they were headed.
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }
  return response;
}

export const config = {
  // Run on app routes; skip static assets, the login page, and API routes.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|login|api).*)"],
};
