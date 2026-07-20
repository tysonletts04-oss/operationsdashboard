// Starts the Auth0 login (OAuth2 Authorization Code flow).
//
// We generate a random `state`, remember it (plus where the user was heading) in a
// short signed cookie, then redirect the browser to Auth0's Universal Login page.
// Auth0 sends the user back to /api/callback with a one-time code.

import { SignJWT } from "jose";
import { baseUrl, setCookie, safePath, randomString } from "../lib/http.js";

export default async function handler(req, res) {
  const domain = process.env.AUTH0_DOMAIN;
  const clientId = process.env.AUTH0_CLIENT_ID;
  const secret = new TextEncoder().encode(process.env.AUTH0_SECRET);
  const base = baseUrl(req);

  const returnTo = safePath(req.query && req.query.returnTo);
  const state = randomString();

  // Bind the state + return path into a signed, 10-minute cookie (stateless CSRF guard).
  const stateJwt = await new SignJWT({ s: state, r: returnTo })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("10m")
    .sign(secret);

  const authorize = new URL(`https://${domain}/authorize`);
  authorize.searchParams.set("response_type", "code");
  authorize.searchParams.set("client_id", clientId);
  authorize.searchParams.set("redirect_uri", `${base}/api/callback`);
  authorize.searchParams.set("scope", "openid profile email");
  authorize.searchParams.set("state", state);

  res.setHeader("Set-Cookie", setCookie("__state", stateJwt, 600));
  res.statusCode = 302;
  res.setHeader("Location", authorize.toString());
  res.end();
}
