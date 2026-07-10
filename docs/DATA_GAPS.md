# Data gaps & how to close them

*Current as at report date **8 Jul 2026**, 23 NSW venues.*

The dashboard shows a metric only when its data is in DataSights **and**
trustworthy; otherwise it shows **"—"** — by design, no guessed numbers. This is
the complete picture of what's populated and what isn't, with exactly what's
needed to close each gap.

## Current coverage (every metric)

| System | Metric | Coverage | State |
|---|---|---|---|
| Sales | Sales (actual) | **23/23** | ✅ live |
| Sales | **Budget** (Sales v Budget) | 0/23 | ❌ empty |
| Review Tracker | Google Reviews | **23/23** | ✅ live |
| Celsi | Hopper Temps | **23/23** | ✅ live |
| Celsi | Calibrations | **23/23** | ✅ live |
| Celsi | Corrective Actions | **23/23** | ✅ live |
| Chi Central | Policy sign-off % | **23/23** | ✅ live |
| Chi Central | Comms read % | **23/23** | ✅ live |
| Chi Central | Training | **23/23** | ✅ live |
| Tanda | **Labour %** | 9/23 | ⚠️ partial |
| Restoke | **Cake Logs** | 0/23 | ❌ empty |
| Restoke | **Litter Pickup** | 0/23 | ❌ empty |
| Restoke | **Daily Waste Log** | 0/23 | ❌ empty |
| Restoke | **Delivery Temps** | 0/23 | ❌ empty |
| Restoke | **Open/Close** | 0/23 | ❌ empty |

**8 metrics fully live · 1 partial (Tanda) · 6 empty (Budget + ×5 Restoke).**
The whole **Restoke** system is empty; **Tanda** is empty for 14 of 23 venues.
(Chi Central **Training** is now live — bridged to venue by name.)

---

## ⚠️ Partial — Tanda: Labour % (9 of 23 venues)

- **Populated (9):** George St, Barangaroo, Chatswood, Cronulla, Newtown, Bondi,
  Coogee, Bondi Junction, Double Bay.
- **Empty (14):** Erina Fair, Wollongong, Charlestown, Rouse Hill, Circular Quay,
  Macquarie, Castle Towers, Burwood, Penrith, Manly, Surry Hills, Top Ryde,
  Randwick, Lane Cove.
- **Why:** Restoke's labour data mis-attributes venues. 12 of the empty venues
  have **no labour rows at all** — their staff are dumped into aggregate buckets
  ("Yo-Chi Randwick" = 474 "employees"; "Yo-Chi Prospect"). "Randwick" itself is
  that dump (excluded); Top Ryde (~50%) is excluded as implausible. The board
  shows "—" rather than a wrong number.
- **How to integrate:** fix Restoke's labour export so each venue's staff file
  under **that** venue, not an aggregate. Source-side, in Restoke / the
  integration. The pipeline auto-includes the venues once attributed correctly —
  no dashboard change needed.
- **Owner:** Restoke integration. **Blocker:** source data.
- **Ready-to-hand ticket:** see [`RESTOKE_LABOUR_FIX.md`](RESTOKE_LABOUR_FIX.md)
  — exact broken buckets, affected venues, the fix, and a verification query.

---

## ❌ Empty — whole Restoke system (5 metrics, 0/23)

Cake Logs · Litter Pickup · Daily Waste Log · Delivery Temps · Open/Close.

- **Why:** these operational checklists are **not exposed in DataSights at all.**
  Restoke's DataSights views cover ordering / sales / invoices / labour only;
  there is no checklist/form-submission view. (`OpCentralForms` holds form
  *definitions*, not per-venue submissions.)
- **How to integrate:** DataSights — with Restoke / OpCentral — must publish the
  checklist submissions as a queryable view: **per venue, per date, completion.**
  Once a view exists, each of the 5 metrics is one query + one rule (Low effort
  each).
- **Owner:** DataSights / Restoke integration. **Blocker:** source not exposed —
  nothing to query yet.

---

## ✅ Done — Chi Central: Training (23/23)

- **Now live.** Average programme completion % per venue, from
  `OpCentralTrainingAllResultPrograms`.
- **How it was closed:** training has no venue column, so it's bridged by name —
  `user_id` → `user_full_name` → policy-signoff `workplace_name`. Rule: ≥90% green
  · ≥75% yellow · else red. Built entirely on our side, no source change.
- Chi Central is now fully live (policy + comms + training, 23/23).

---

## ❌ Empty — Sales: Budget (0/23)

- **Why:** the Xero budget exists (`XeroConsolidationBudgetGroupReportViewWithFX`,
  per venue via the "Location" tracking category, e.g. `48. GEOR.NSW`) but
  (a) only runs **monthly through Jun 2026**, and (b) its "Revenue" line
  reconciles to **~2× POS net sales** — a different basis (likely GST-inclusive
  and/or includes non-POS revenue). Comparing as-is would show every venue ~50%
  under budget (false).
- **How to integrate:** Finance confirms what the Xero "Revenue" budget represents
  vs POS net sales and the adjustment (GST, catering/delivery); ensure current
  months are loaded; then wire the budget view per venue into the sales rule.
- **Owner:** Finance (decision), then Dashboard. **Blocker:** the decision, not data.

---

## Who closes what

| Gap | Blocker type | Owner | We can do it? |
|---|---|---|---|
| Tanda Labour % (14 venues) | Source data (Restoke attribution) | Restoke integration | No — upstream |
| Restoke checklists (×5) | Source not exposed in DataSights | DataSights / Restoke | No — upstream |
| Chi Central Training | ~~Build (name-bridge)~~ | Dashboard | ✅ **done** |
| Sales Budget | A finance decision | Finance → Dashboard | After the decision |

None are dashboard *bugs* — every "—" is upstream data availability or a pending
decision. The board is correctly showing everything it can trust today (8 of the
9 non-Restoke metrics fully populated).
