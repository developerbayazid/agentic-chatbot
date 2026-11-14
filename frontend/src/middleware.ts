import { NextResponse, type NextRequest } from "next/server";

import { readSession, SESSION_COOKIE, isExpired } from "@/lib/auth/session";

const PUBLIC_PATHS = ["/login"];

/**
 * Route protection.
 *
 * This is a UX gate, not a security boundary: the cookie is only a hint about
 * whether a token exists, and the backend re-validates every request anyway.
 * An unauthenticated request never renders the dashboard shell.
 */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const session = readSession(request.cookies.get(SESSION_COOKIE)?.value);
  const authenticated = session !== null && !isExpired(session);

  if (PUBLIC_PATHS.includes(pathname)) {
    if (authenticated) {
      return NextResponse.redirect(new URL("/chat", request.url));
    }

    return NextResponse.next();
  }

  if (!authenticated) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  // Everything except Next internals, the BFF routes, and static assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\..*).*)"],
};
