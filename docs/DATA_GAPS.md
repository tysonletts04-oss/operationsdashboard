# Data gaps & how to close them

*Current as at report date **13 Jul 2026**, 27 NSW venues (23 company-owned + 4
franchise).*

The dashboard shows a metric only when its data is in DataSights **and**
trustworthy; otherwise it shows **"—"** — by design, no guessed numbers. This is
the complete picture of what's populated and what isn't, with exactly what's
needed to close each gap.

## Current coverage (every metric)

| System | Metric | Coverage | State |
|---|---|---|---|
| Sales | Sales (actual) | **27/27** | ✅ live |
| Sales | **Budget** (Sales v Budget) | 0/27 | ❌ empty |
| Review Tracker | Google Reviews | **27/27** | ✅ live |
| Celsi | Hopper Temps | **27/27** | ✅ live |
| Celsi | Calibrations | **27/27** | ✅ live |
| Celsi | Corrective Actions | **27/27** | ✅ live |
| Chi Central | Policy sign-off % | **27/27** | ✅ live |
| Chi Central | Comms read % | **27/27** | ✅ live |
| Chi Central | Training | **27/27** | ✅ live |
| Tanda | **Labour %** | **23/27** | ✅ live (23 company venues; 4 franchises N/A) |
| Restoke | **Cake Logs** | 0/27 | ❌ empty |
| Restoke | **Litter Pickup** | 0/27 | ❌ empty |
| Restoke | **Daily Waste Log** | 0/27 | ❌ empty |
| Restoke | **Delivery Temps** | 0/27 | ❌ empty |
| Restoke | **Open/Close** | 0/27 | ❌ empty |

**9 metrics fully live · 6 empty (Budget + ×5 Restoke checklists).**
The whole **Restoke** checklist system is still empty; everything else the
dashboard measures is live.

---

## ✅ Done — Tanda: Labour % (23/27, all company venues)

- **Now live** for every company-owned venue, sourced from **Tanda timesheets**
  (`TandaTimesheetShifts`, award-interpreted cost ÷ net sales, MTD).
- **How it was closed:** the labour metric was repointed from Restoke (which
  mis-attributed venues) to Tanda, the payroll / rostering system of record. A
  shift's `department_id` → team → venue location gives clean per-venue cost.
  Built entirely on our side, no source change. Details in
  [`RESTOKE_LABOUR_FIX.md`](RESTOKE_LABOUR_FIX.md).
- **The 4 franchise venues** (Erina Fair, Wollongong, Charlestown, Green Hills)
  run their own payroll and are not in the company Tanda org, so Labour % shows
  "—" for them by design — a scope boundary, not a gap.

---

## ❌ Empty — whole Restoke checklist system (5 metrics, 0/27)

Cake Logs · Litter Pickup · Daily Waste Log · Delivery Temps · Open/Close.

- **Why:** these operational checklists are **not exposed in DataSights at all.**
  Restoke's DataSights views cover ordering / sales / invoices only; there is no
  checklist/form-submission view. (`OpCentralForms` holds form *definitions*, not
  per-venue submissions.)
- **How to integrate:** DataSights — with Restoke / OpCentral — must publish the
  checklist submissions as a queryable view: **per venue, per date, completion.**
  Once a view exists, each of the 5 metrics is one query + one rule (Low effort
  each).
- **Owner:** DataSights / Restoke integration. **Blocker:** source not exposed —
  nothing to query yet.

---

## ✅ Done — Chi Central: Training (27/27)

- **Now live.** Average programme completion % per venue, from
  `OpCentralTrainingAllResultPrograms`.
- **How it was closed:** training has no venue column, so it's bridged by name —
  `user_id` → `user_full_name` → policy-signoff `workplace_name`. Rule: ≥90% green
  · ≥75% yellow · else red. Built entirely on our side, no source change.
- Chi Central is fully live (policy + comms + training, 27/27).

---

## ❌ Empty — Sales: Budget (0/27)

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
| Tanda Labour % | ~~Source data (Restoke attribution)~~ | Dashboard | ✅ **done** (moved to Tanda) |
| Chi Central Training | ~~Build (name-bridge)~~ | Dashboard | ✅ **done** |
| Restoke checklists (×5) | Source not exposed in DataSights | DataSights / Restoke | No — upstream |
| Sales Budget | A finance decision | Finance → Dashboard | After the decision |

None are dashboard *bugs* — every remaining "—" is upstream data availability (the
Restoke checklists) or a pending decision (the Sales budget). The board is
correctly showing everything it can trust today.
