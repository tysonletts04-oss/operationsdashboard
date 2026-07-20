// Vercel Routing (Edge) Middleware — the security gate for the whole dashboard.
//
// It runs at Vercel's edge BEFORE any file is served (index.html, data.json,
// everything), so nothing is public without a valid Auth0 login. This is real
// server-side protection: even a direct fetch of /data.json is blocked.
//
// A request is allowed through only if it carries a valid __sess cookie — a short
// JWT we mint in api/callback.js after Auth0 verifies the user, signed with
// AUTH0_SECRET. No cookie (or an expired/tampered one) => redirect to /api/login,
// which starts the Auth0 login flow.
//
// The matcher runs on every path except the auth endpoints themselves and a couple
// of static odds and ends (so login can't loop on itself).

import { next } from "@vercel/functions";
import { jwtVerify } from "jose";

export const config = {
  matcher: ["/((?!api/|favicon.ico|robots.txt).*)"],
};

export default async function middleware(request) {
  const secret = process.env.AUTH0_SECRET;
  // Fail closed: if the app isn't configured, let nobody in rather than everybody.
  if (!secret) {
    return new Response("Auth is not configured (AUTH0_SECRET missing).", {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }

  const token = readCookie(request.headers.get("cookie"), "__sess");
  if (token) {
    try {
      await jwtVerify(token, new TextEncoder().encode(secret), { algorithms: ["HS256"] });
      return next(); // valid session -> serve the requested file
    } catch {
      /* invalid/expired -> fall through to login */
    }
  }

  const url = new URL(request.url);
  const login = new URL("/api/login", url.origin);
  login.searchParams.set("returnTo", url.pathname + url.search);
  return Response.redirect(login, 302);
}

function readCookie(header, name) {
  for (const part of (header || "").split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === name) return decodeURIComponent(part.slice(eq + 1).trim());
  }
  return null;
}
