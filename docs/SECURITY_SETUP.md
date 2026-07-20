# Make the dashboard private with Auth0 (per-user logins)

Hosting moves to **Vercel**, which runs a security gate at the edge before serving
anything. Login is handled by **Auth0**, so every person signs in with their own
account (not a shared password). The gate protects the page **and** `data.json` —
a direct link to the raw data is blocked too.

Everything needed is already in the repo:

| File | Role |
| --- | --- |
| `middleware.js` | The gate. Runs on every request; no valid session -> redirect to login. |
| `api/login.js` | Starts the Auth0 login. |
| `api/callback.js` | Handles the Auth0 redirect, verifies the user, sets the session cookie. |
| `api/logout.js` | Logs the user out (link to `/api/logout`). |
| `lib/http.js` | Small shared helpers. |
| `package.json` | Declares the two dependencies (`jose`, `@vercel/functions`). |

You only need to (1) create an Auth0 application, (2) create a Vercel project,
(3) paste five environment variables. ~15 minutes.

---

## 1. Create the Auth0 application

1. In the Auth0 dashboard: **Applications -> Applications -> Create Application**.
2. Name it (e.g. `Yo-Chi Ops Dashboard`), type **Regular Web Application**, Create.
3. Open its **Settings** and copy the **Domain**, **Client ID** and **Client Secret**
   (you will paste these into Vercel in step 3).
4. Leave this tab open — you will fill in the two URL fields in step 4, once you know
   your Vercel URL.

## 2. Create the Vercel project

1. Sign up / in at https://vercel.com (choose **Continue with GitHub**).
2. **Add New… -> Project**, import **`tysonletts04-oss/operationsdashboard`**.
3. Framework preset **Other**. Leave Build Command and Output Directory empty.
   (Vercel serves the static files and builds `api/*` + `middleware.js` for you.)
4. Don't deploy yet — add the environment variables first (next step), or deploy
   and then add them and redeploy.

## 3. Add the environment variables (Vercel -> Project -> Settings -> Environment Variables)

Add all five to **Production** (and Preview if you want protected preview builds):

| Name | Value |
| --- | --- |
| `AUTH0_DOMAIN` | your Auth0 domain, e.g. `dev-abc123.us.auth0.com` (no `https://`) |
| `AUTH0_CLIENT_ID` | from the Auth0 app settings |
| `AUTH0_CLIENT_SECRET` | from the Auth0 app settings |
| `AUTH0_SECRET` | a random 32+ byte secret to sign session cookies (see below) |
| `AUTH0_BASE_URL` | your site URL, e.g. `https://operationsdashboard.vercel.app` (no trailing slash) |

Generate `AUTH0_SECRET` locally with:

```bash
openssl rand -hex 32
```

Then **Deploy** (or **Deployments -> Redeploy** so the new variables take effect).

## 4. Point Auth0 at your Vercel URL

Back in the Auth0 application **Settings**, set (use your real Vercel URL):

- **Allowed Callback URLs:** `https://operationsdashboard.vercel.app/api/callback`
- **Allowed Logout URLs:** `https://operationsdashboard.vercel.app`

Save. (If you later add a custom domain, add its `/api/callback` and root URL here too.)

## 5. Add the people who should have access

Auth0 **User Management -> Users -> Create User**, or turn on a social/email
connection. Only users that exist in your Auth0 tenant can get in.

## 6. Test

Open your Vercel URL. You should be redirected to the Auth0 login, and after signing
in, land on the dashboard. Try opening `…/data.json` directly in a private window —
it should redirect to login, not download.

## 7. Close the public back door — disable GitHub Pages *(important)*

Repo **Settings -> Pages -> Source -> None** (Save). Otherwise the old
`…github.io/…` URL stays public and unprotected.

---

## Good to know

- **Auto-refresh still works.** The scheduled job commits `data.json` to `main`;
  Vercel redeploys on every push, same as before. The data stays behind the gate.
- **Everything is protected** — the page and `data.json` — because the gate runs
  before any file is served.
- **Add a log-out link** anywhere in the dashboard: `<a href="/api/logout">Log out</a>`.
- **Sessions last 8 hours**, then users log in again. Change the `8h` in
  `api/callback.js` (and the cookie `Max-Age`) to adjust.
- **Nothing secret is in the repo.** The client secret and signing key live only in
  Vercel's environment variables.
- **Per-venue access (later).** Auth0 can carry roles/permissions per user; the gate
  could then show each manager only their venues. That is a larger Phase-2 build.

## The Auth0 MCP server (optional, unrelated to the gate above)

The Auth0 **MCP server** lets an AI assistant manage your Auth0 tenant by chat
(create apps, users, view logs). It is a convenience for *configuring* Auth0 — it is
**not** what secures the dashboard, and it is not required for any of the steps above.
If you want it, run:

```bash
npx @auth0/auth0-mcp-server init
```

and follow the browser prompt to authorise your tenant.
