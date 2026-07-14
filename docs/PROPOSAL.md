# Operations Reporting on DataSights — proposal

*A low-cost, self-refreshing reporting layer to replace per-venue Power BI, built
on the DataSights (Azure) database and the tooling we already run.*

## The opportunity

Almost all of our operational data now lives in one AI/SQL-queryable Azure
database (DataSights). We already run automated daily reports and processes on
GitHub, Render, Vercel, Python and Azure — cheaply and reliably. That means the
expensive per-venue external reporting (Power BI licences and similar) is now
duplicating something we can do ourselves, better and for a fraction of the cost.

This proposal turns that into a concrete, repeatable pattern: a **self-refreshing
operations dashboard** any team can stand up from the same codebase.

## What's been built (working today)

A NSW operations dashboard covering all six operating systems, live from
DataSights, across 23 NSW venues:

| System | Metric | Status |
|---|---|---|
| Sales | Net sales (actual) | ✅ Live |
| Review Tracker | Google Reviews | ✅ Live |
| Celsi | Hopper temps, calibrations, corrective actions | ✅ Live |
| Chi Central | Policy %, comms read %, training completion % | ✅ Live (23/23) |
| Tanda | Labour % | ✅ Live (23/27 — Tanda timesheets; 4 franchise venues run own payroll, N/A) |
| Sales | Budget comparison | ⛔ Held pending a definition decision |
| Restoke | Cake/litter/waste/delivery/open-close checklists | ⛔ Not yet exposed in DataSights |

It refreshes itself daily and costs effectively nothing to run.

## How it works

Data is separated from presentation, which is the whole trick:

- **A static page** (`index.html`) — the entire UI in one self-contained file.
  Deployed once to a CDN (Vercel / Azure Static Web Apps / GitHub Pages). No
  server, so near-zero cost and nothing to keep running.
- **A daily job** (`build_data.py`) — queries DataSights, normalises and
  validates the data, and writes `data.json`. Scheduled by GitHub Actions at 6am.
- The page fetches `data.json` on load. Update the data → the board updates. No
  one edits the page.

```
 GitHub Actions (6am) ─► build_data.py ─► queries DataSights ─► data.json ─► CDN ─► dashboard
```

Every piece is something we already operate. Nothing new to learn or pay for.

## Why this is more reliable than a black-box report

Trust is the real product. Three things build it in:

1. **Validation gates** — the daily job refuses to publish data that fails sanity
   checks (missing sales, labour outside a believable range, invalid percentages).
   On failure it keeps the last good copy rather than showing garbage.
2. **Visible provenance** — every system on the board is labelled *Live /
   partial / awaiting source*, with the snapshot date shown. Nobody has to guess
   whether a number is real or how fresh it is.
3. **Logic in version control** — the hard part is not the chart, it's the data.
   Venue names differ across all six systems; labour data double-counts and
   dumps several venues' staff into one bucket; the Celsi checks are weekly, not
   daily; the Xero budget is on a different revenue basis. All of that is now
   documented, tested Python — not tribal knowledge.

## Cost

- **Serving:** a static file on a CDN — free/negligible on every host we use.
- **Refresh:** a GitHub Actions cron — free at our volume.
- **Replaces:** per-venue Power BI licences and the external reporting spend.

## Scaling to other Yo-Chi teams

The pipeline is config-driven. Onboarding is not a rebuild:

- **Another venue** → one row in the venue-mapping table (its name in each system).
- **Another team or state** → a config fork (which venues, which metrics,
  thresholds). One codebase, one small config per team.

This is how we support the other teams that have reached out without multiplying
maintenance.

## Decisions / inputs needed to finish

1. **An unattended DataSights credential.** The interactive login can't be used by
   a scheduled job. DataSights needs to provide an API key or Azure SQL access for
   machine use. (~30 min to wire once we have it.)
2. **Sales budget definition.** The Xero "Revenue" budget reconciles to ~2× POS
   net sales and only runs monthly to June. We need finance to confirm what that
   line represents (GST? non-POS revenue?) before showing a Sales-vs-Budget number
   nobody will trust.
3. **Source gaps** worth prioritising: Restoke operational checklists and
   need their DataSights connection completed.
4. **Metric ownership.** A short, agreed definition per metric (thresholds, what
   "compliant" means) so teams don't argue about the numbers.

## Suggested next steps

1. Get the unattended credential → the board goes fully live and self-updating.
2. Pick a host and deploy the static page.
3. Agree the metric definitions and the budget basis.
4. Stand up a second team from the same repo as the template for the rest.
