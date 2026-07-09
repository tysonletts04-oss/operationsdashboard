# NSW Operations Reporting Dashboard

A self-refreshing operations dashboard for Yo-Chi NSW venues, built on DataSights.
Traffic-light compliance across the six operating systems (Celsi, Chi Central,
Restoke, Review Tracker, Sales, Tanda), with per-venue and grid views.

It replaces per-venue Power BI reporting with a near-zero-cost static site that
refreshes itself daily from DataSights.

## How it works

The design deliberately separates **data** from **presentation**:

```
  GitHub Actions (daily cron)                     A static host you deploy once
  ─────────────────────────────                   ────────────────────────────
  build_data.py                                   index.html  (dumb shell)
    │  queries DataSights (Azure)                    │  fetch('data.json') on load
    │  normalises + validates          ── commit ──► │  renders grid / KPIs / cards
    ▼                                    data.json    │  falls back to embedded data
  data.json  ◄─────────────────────────────────────┘   if the fetch fails
```

- **`index.html`** — the whole UI, self-contained. Deploy it once; never touch it
  to refresh data. It fetches `data.json` at load and renders it. If the fetch
  fails (opened via `file://`, or the refresh job hasn't run), it falls back to a
  snapshot embedded in the file, so it always shows *something*.
- **`data.json`** — the daily data + metadata (`reportDate`, `generatedAt`,
  per-source status, coverage). The only file that changes day to day.
- **`build_data.py`** — queries DataSights, normalises, validates, writes
  `data.json`. This is the real logic (see below).
- **`.github/workflows/refresh.yml`** — runs `build_data.py` each morning and
  commits `data.json` back, which triggers a redeploy.

## The data is the hard part

Every metric had a trap that lives as documented logic in `build_data.py`:

| System | Metric | Reality handled in code |
|---|---|---|
| Sales | Net sales (actual) | joins POS to `Venue_Master`; NSW = `State='2. NSW'` |
| Review Tracker | Google Reviews | weekly metric; trailing-7-day count per venue |
| Celsi | Hopper temps / calibrations / corrective | **weekly-bucketed** by `Date`; daily = week ÷ 7 |
| Tanda | Labour % | Restoke labour cost ÷ net sales, **de-duplicated**; HQ-dump venues (100s of "staff") excluded by a sanity gate |
| Chi Central | Policy / comms read % | OpCentral sign-off completion rate (not raw unread counts) |

**Held back on purpose:**
- **Sales budget** — the only Xero budget is monthly to Jun 2026 and its "Revenue"
  basis reconciles to ~2× POS net sales. A like-for-like comparison needs the
  revenue definition confirmed. Wire it in `SQL`/`_venue_record` once agreed.
- **Chi Central training** — the source has no venue dimension.
- **Restoke checklists** (cake/litter/waste/delivery/open-close) — not exposed in
  DataSights yet.

These render as **"—"** and are labelled on the board's data-source strip.

## Running it

```bash
# Rebuild from the bundled 2026-07-07 snapshot — no database needed:
python build_data.py --offline

# Live refresh (needs a credential, see below):
python build_data.py
```

Then serve the folder (`python -m http.server`) and open `index.html`.

### The one thing to wire: an unattended credential

An interactive DataSights/MCP login can't be used by a 6am cron job — nobody's
logged in. Use the DataSights **"Custom / API"** connect screen → **Generate
Credentials** to get a **Client ID + Client Secret** (OAuth2 client-credentials).

`datasights_query()` already implements the token exchange + query call. Set:

| Env var | From |
|---|---|
| `DATASIGHTS_TOKEN_URL` | the `/connect/token` URL on the connect screen |
| `DATASIGHTS_QUERY_URL` | the query endpoint (confirm the path with DataSights) |
| `DATASIGHTS_CLIENT_ID` | Generate Credentials |
| `DATASIGHTS_CLIENT_SECRET` | Generate Credentials — **store as a secret, never in code** |
| `DATASIGHTS_SCOPE` | optional, only if required |

Add the **secret** under repo *Settings → Secrets and variables → Actions*. The
only things left to confirm against a real response are the query endpoint URL,
the request field name (`sql` vs `query`), and the response envelope — all flagged
in `datasights_query()`.

## Deploying

The site is a static folder — host it anywhere cheap:
- **Vercel / Azure Static Web Apps / GitHub Pages** — point it at this repo. Each
  `data.json` commit from the refresh job triggers a redeploy.

## Reliability

- **Validation gates** in `build_data.py` (`validate()`) refuse to publish
  nonsense (missing/negative sales, labour outside 5–45 %, invalid percentages).
  On failure the job exits non-zero and `data.json` is left untouched — the board
  keeps its last good copy rather than showing garbage.
- **Provenance on the board** — the data-source strip shows each system as
  *Live · DataSights* / *partial* / *awaiting source*, and the header badge shows
  the snapshot date, so a stale or partial board is obvious.
- **Coverage** is reported in `data.json` `meta.coverage` (e.g. labour `10/23`).

## Onboarding another venue or team

- **Another venue:** add a row to the `VENUES` table in `build_data.py` (its name
  in each system). Leave a field `None` where a system has no match.
- **Another team / state:** the pipeline is config-driven by that table and the
  NSW filter — fork the config, not the code. One codebase, one config per team.
