// Cloudflare Pages middleware — password gate for the whole site.
//
// Runs at Cloudflare's edge BEFORE any file (index.html, data.json, everything)
// is served, so nothing is public without the password. This is real server-side
// protection, unlike a client-side JS prompt.
//
// The password is NOT stored here (this repo is public). Set it as an environment
// variable in the Cloudflare Pages project:
//     Settings → Environment variables → SITE_PASSWORD = YOCHI
// Fail-closed: if SITE_PASSWORD isn't set, nobody gets in.
//
// Login: the browser shows a username + password prompt. Username can be anything;
// the password must equal SITE_PASSWORD.

export const onRequest = async (context) => {
  const { request, env, next } = context;
  const expected = env.SITE_PASSWORD;

  const header = request.headers.get("Authorization") || "";
  if (expected && header.startsWith("Basic ")) {
    try {
      const decoded = atob(header.slice(6));            // "username:password"
      const password = decoded.slice(decoded.indexOf(":") + 1);
      // constant-time-ish comparison
      if (password.length === expected.length) {
        let diff = 0;
        for (let i = 0; i < password.length; i++) diff |= password.charCodeAt(i) ^ expected.charCodeAt(i);
        if (diff === 0) return next();                  // correct → serve the site
      }
    } catch (_) { /* fall through to 401 */ }
  }

  return new Response("Authentication required.", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Yo-Chi Operations Dashboard", charset="UTF-8"',
      "Cache-Control": "no-store",
    },
  });
};
