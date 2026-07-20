// Auth0 redirects here after the user logs in.
//
// Steps:
//   1. Verify the `state` matches the signed cookie we set in api/login.js.
//   2. Exchange the one-time `code` for tokens over a server-to-server call
//      (uses the client secret, never exposed to the browser).
//   3. Verify the ID token's signature against Auth0's JWKS, issuer and audience.
//   4. Mint our own 8-hour session cookie (__sess) and send the user back.

import { SignJWT, jwtVerify, createRemoteJWKSet } from "jose";
import { baseUrl, readCookie, setCookie, clearCookie, safePath } from "../lib/http.js";

export default async function handler(req, res) {
  const domain = process.env.AUTH0_DOMAIN;
  const clientId = process.env.AUTH0_CLIENT_ID;
  const clientSecret = process.env.AUTH0_CLIENT_SECRET;
  const secret = new TextEncoder().encode(process.env.AUTH0_SECRET);
  const base = baseUrl(req);

  const code = req.query && req.query.code;
  const state = req.query && req.query.state;

  // 1) State check.
  let returnTo = "/";
  try {
    const cookie = readCookie(req.headers.cookie, "__state");
    const { payload } = await jwtVerify(cookie, secret, { algorithms: ["HS256"] });
    if (!state || payload.s !== state) throw new Error("state mismatch");
    returnTo = safePath(payload.r);
  } catch {
    res.statusCode = 400;
    res.end("Login failed: invalid state. Please try again.");
    return;
  }

  // 2) Code -> tokens (back channel).
  let tokens;
  try {
    const r = await fetch(`https://${domain}/oauth/token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        grant_type: "authorization_code",
        client_id: clientId,
        client_secret: clientSecret,
        code,
        redirect_uri: `${base}/api/callback`,
      }),
    });
    if (!r.ok) throw new Error(`token endpoint ${r.status}`);
    tokens = await r.json();
  } catch {
    res.statusCode = 502;
    res.end("Login failed: could not complete the token exchange.");
    return;
  }

  // 3) Verify the ID token.
  let claims;
  try {
    const JWKS = createRemoteJWKSet(new URL(`https://${domain}/.well-known/jwks.json`));
    const { payload } = await jwtVerify(tokens.id_token, JWKS, {
      issuer: `https://${domain}/`,
      audience: clientId,
    });
    claims = payload;
  } catch {
    res.statusCode = 401;
    res.end("Login failed: the identity token could not be verified.");
    return;
  }

  // 4) Mint the session cookie and return the user to where they were headed.
  const sess = await new SignJWT({ sub: claims.sub, email: claims.email, name: claims.name })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("8h")
    .sign(secret);

  res.setHeader("Set-Cookie", [setCookie("__sess", sess, 8 * 3600), clearCookie("__state")]);
  res.statusCode = 302;
  res.setHeader("Location", returnTo);
  res.end();
}
