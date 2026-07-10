# Make the dashboard private (password: YOCHI)

Move hosting from **public** GitHub Pages to **Cloudflare Pages**, which enforces
a password at the edge before serving anything. Free, real security, ~15 minutes.
The password gate is already in the repo (`functions/_middleware.js`) — you just
connect Cloudflare and set the password.

## Steps

1. **Create a free Cloudflare account** — https://dash.cloudflare.com/sign-up

2. **Create the Pages project**
   - Dashboard → **Workers & Pages** → **Create** → **Pages** →
     **Connect to Git**.
   - Authorise GitHub, pick **`tysonletts04-oss/operationsdashboard`**, branch **`main`**.
   - Build settings: **Framework preset = None**, **Build command = (leave empty)**,
     **Build output directory = `/`**. → **Save and Deploy**.

3. **Set the password** (this is where "YOCHI" lives — never in the repo)
   - Open the new Pages project → **Settings → Environment variables**.
   - Add a variable: **`SITE_PASSWORD`** = **`YOCHI`** (Production).
   - Go to **Deployments** → **Retry deployment** (so the gate picks up the password).

4. **Test** your new private URL (e.g. `https://operationsdashboard.pages.dev`)
   - It should pop a login box. **Username: anything** (e.g. `yochi`),
     **Password: `YOCHI`**. Correct password → dashboard loads. Wrong/none → blocked.

5. **Close the public back door — disable GitHub Pages** *(important)*
   - Repo **Settings → Pages → Source → None** (Save).
   - Otherwise the old `…github.io/…` URL stays public and unprotected.

Done — the dashboard is now private behind the password, at your `pages.dev` URL.

## Good to know

- **Auto-refresh still works.** The daily job commits `data.json` to `main`;
  Cloudflare Pages redeploys on every push, same as before.
- **Everything is protected** — the page *and* `data.json` — because the gate runs
  before any file is served.
- **To change the password:** update `SITE_PASSWORD` in Cloudflare and redeploy.
  Nothing in the code changes.
- **This is a shared password (everyone types YOCHI).** If you later want each
  person to log in individually and see only their venues, that's the Phase-2
  per-user (RBAC) build — a bigger project.
- **Custom domain (optional):** Pages project → **Custom domains** to use e.g.
  `ops.yochi.com.au` instead of `pages.dev`.
