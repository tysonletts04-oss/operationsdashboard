// Small helpers shared by the Auth0 serverless functions (api/*.js).
// No dependencies; runs in the Vercel Node runtime.

// The site's own origin, e.g. https://operationsdashboard.vercel.app.
// Prefer AUTH0_BASE_URL (must exactly match what you register in Auth0);
// otherwise derive it from the incoming request headers.
export function baseUrl(req) {
  if (process.env.AUTH0_BASE_URL) return process.env.AUTH0_BASE_URL.replace(/\/+$/, "");
  const proto = req.headers["x-forwarded-proto"] || "https";
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  return `${proto}://${host}`;
}

// Read one cookie value out of a raw Cookie header.
export function readCookie(header, name) {
  for (const part of (header || "").split(";")) {
    const eq = part.indexOf("=");
    if (eq === -1) continue;
    if (part.slice(0, eq).trim() === name) {
      return decodeURIComponent(part.slice(eq + 1).trim());
    }
  }
  return null;
}

// A hardened Set-Cookie string. HttpOnly keeps it out of JS; Secure forces
// HTTPS; SameSite=Lax still rides the top-level redirect back from Auth0.
export function setCookie(name, value, maxAgeSec) {
  return `${name}=${encodeURIComponent(value)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${maxAgeSec}`;
}

export function clearCookie(name) {
  return `${name}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;
}

// Only allow same-site relative return paths (blocks open-redirects like //evil.com).
export function safePath(p) {
  return typeof p === "string" && p.startsWith("/") && !p.startsWith("//") ? p : "/";
}

export function randomString() {
  return crypto.randomUUID().replace(/-/g, "");
}
