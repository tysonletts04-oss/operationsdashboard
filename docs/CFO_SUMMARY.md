# NSW Operations Reporting Dashboard — Phase 1 summary

*A live, self-updating operations dashboard built on our existing DataSights
(Azure) database — replacing per-venue external reporting (Power BI) at a
fraction of the cost.*

**Status: live in production.** https://tysonletts04-oss.github.io/operationsdashboard/

---

## What's delivered (Phase 1)

- A **live dashboard** covering 23 NSW venues across the operating systems:
  Sales, Google Reviews, Celsi food-safety, Labour %, and Chi Central.
- **Real data from DataSights** — 5 of the 6 systems, refreshed **automatically
  every morning** with no manual entry.
- **Traceable & auditable** — every number on the board shows its exact DataSights
  source and rule ("Data & definitions" section). Independently verified to match
  the source to the dollar.
- Built, deployed and documented on tools we already run (GitHub, Python, Azure).

## Why it matters

| | |
|---|---|
| **Cost** | Runs for effectively $0/month. Directly offsets per-venue Power BI licences and external reporting spend. |
| **Speed** | Numbers are current to the last trading day, every day, automatically. |
| **Ownership** | We own the code and the pipeline — no external per-seat dependency. |
| **Trust** | Every figure traces back to DataSights; nothing is hand-keyed. Gaps are shown honestly as "—", not guessed. |
| **Scalable** | Other Yo-Chi teams can be stood up from the same codebase via config — not a rebuild. |

## Phase 2 (scoped, needs inputs — not blockers to Phase 1)

- **Sales vs Budget** — pending a finance decision on the Xero "Revenue" basis
  (it currently reconciles to ~2× POS net sales, so a like-for-like needs sign-off).
- **Restoke checklists** — pending a DataSights connection (not yet exposed).
- **Labour %** for 14 venues — pending a Restoke venue-attribution fix (source-side).
- **Access control** — put the site behind a login (Cloudflare Access, free) before
  wider distribution.
- **Failure alerting** and **metric sign-off** with ops/finance.

## The ask

A **progress payment** for Phase 1: a working, live, automated, auditable
reporting product — delivered on our own low-cost stack.

See **[`ROI.md`](ROI.md)** for the value case: ~$20k–45k/year in hard savings
(manual reporting + tooling) at ≈$0 running cost, scaling to every other team —
with the assumptions laid out so they can be pressure-tested.

---

## 3-minute demo script

1. **Open the link.** "This is live and rebuilds itself every morning from
   DataSights — no one touches it."
2. **KPIs + grid.** "Real numbers across 23 NSW venues — sales, reviews,
   food-safety, labour, compliance."
3. **Toggle Daily / WTD / MTD and 'By venue'.** "Same data, however you want to cut it."
4. **Scroll to 'Data & definitions'.** "This is the important part — every number
   names its DataSights source and rule. Nothing is hand-entered; anyone can trace
   it back and reproduce it."
5. **Point at the '—' cells.** "Where we can't yet verify a number — the budget
   comparison, some checklists — we show a dash and say why, rather than
   guess. That's Phase 2."
6. **Close on value.** "It runs for effectively nothing, replaces per-venue Power BI,
   and we own it. Phase 1 is live today; Phase 2 is scoped and waiting on a couple of
   data decisions."

## Likely questions — quick answers

- **"Are these numbers real?"** Yes — traceable on-screen to DataSights; verified
  to match the source exactly. Rebuilt by an automated job, not by hand.
- **"Who can see it?"** Right now it's an unlisted link (kept off search engines).
  Before we share it widely we'll put it behind a company login (Cloudflare Access,
  free). *(Do this before broad distribution.)*
- **"What does it cost to run?"** Effectively nothing — a scheduled job + static
  hosting, on infrastructure we already have.
- **"What's missing?"** The budget comparison and two data sources — deliberately
  shown as "—" until confirmed. That honesty is by design.
