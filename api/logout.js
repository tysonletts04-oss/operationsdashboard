// Clears the local session and bounces through Auth0's logout so the user is
// fully signed out (not silently re-logged-in on the next visit).
// Link to it from the dashboard with: <a href="/api/logout">Log out</a>

import { baseUrl, clearCookie } from "../lib/http.js";

export default function handler(req, res) {
  const domain = process.env.AUTH0_DOMAIN;
  const clientId = process.env.AUTH0_CLIENT_ID;
  const base = baseUrl(req);

  const url = new URL(`https://${domain}/v2/logout`);
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("returnTo", base);

  res.setHeader("Set-Cookie", clearCookie("__sess"));
  res.statusCode = 302;
  res.setHeader("Location", url.toString());
  res.end();
}
