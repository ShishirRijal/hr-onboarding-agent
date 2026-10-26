import { NextResponse, type NextRequest } from "next/server";

// Set by the API on sign-in (HttpOnly, so only the server sees it).
const SESSION_COOKIE = "nordtech_hr_session";

// An optimistic check: pages need a session cookie, or the visitor goes to sign-in first, so
// nobody sees the app before signing in. The API decides whether the session is valid and
// what the user may see; a stale cookie is caught there and sent to sign-in too.
export function proxy(request: NextRequest) {
  if (request.cookies.has(SESSION_COOKIE)) return NextResponse.next();
  const signIn = new URL("/sign-in", request.url);
  if (request.nextUrl.pathname !== "/") signIn.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(signIn);
}

export const config = {
  matcher: ["/((?!api|sign-in|_next/static|_next/image|favicon.ico).*)"],
};
