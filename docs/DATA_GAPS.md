# Data gaps & how to close them

The dashboard shows a metric only when its data is in DataSights **and**
trustworthy; otherwise it shows **"—"** — by design, no guessed numbers. This
is the complete list of every gap, why it exists, and exactly what's needed to
close it.

## Summary

| # | Metric | Coverage | What's blocking it | Owner |
|---|---|---|---|---|
| 1 | Sales **v Budget** | 0/23 | A decision on the Xero revenue basis | Finance |
| 2 | Chi Central **Training %** | 0/23 | Build work (name-bridge to venue) | Dashboard |
| 3 | Restoke **checklists** (×5) | 0/23 | Not exposed in DataSights | DataSights / Restoke |
| 4 | Tanda **Labour %** | 9/23 | Restoke mis-attributes venues | Restoke integration |
| 5 | Policy/Comms — **Macquarie** | fixed ✅ | Name mismatch (resolved) | — |

Everything **already live**: Sales (actual), Google Reviews, Celsi (hopper
temps / calibrations / corrective actions), Policy & Comms read %, Labour % for
9 venues.

---

## A. Whole metrics not yet shown

### 1. Sales v Budget — *needs a finance decision, not data*
- **Now:** sales actual is live; the budget side shows "—".
- **Why:** the Xero budget exists (`XeroConsolidationBudgetGroupReportViewWithFX`,
  per venue via the "Location" tracking category, e.g. `48. GEOR.NSW`), but
  (a) it only runs **monthly through Jun 2026**, and (b) its "Revenue" line
  reconciles to **~2× POS net sales** — a different basis (likely GST-inclusive
  and/or includes non-POS revenue). Comparing as-is would show every venue ~50%
  under budget, which is false.
- **To integrate:**
  1. Finance confirms what the Xero "Revenue" budget represents vs POS net sales,
     and the adjustment (e.g. ÷1.1 for GST, include/exclude catering/delivery).
  2. Ensure budgets are loaded for current months (not just to June).
  3. Wire the budget view per venue into the sales rule (map Location code → venue).
- **Effort:** Low once the basis is agreed. **Blocker is the decision.**

### 2. Chi Central — Training % — *buildable, no source change needed*
- **Now:** "—" all venues.
- **Why:** training completion lives in `OpCentralTrainingAllResultPrograms`
  (has % + user), but has **no direct venue column**.
- **To integrate:** bridge by name —
  `OpCentralTrainingAllResults.user_full_name` →
  `OpCentralPolicySignoffs.full_name` → `workplace_name` attributes each user to a
  venue; then compute completion % per venue. Name matching is fuzzy (handle
  duplicate names / leavers), but workable in `build_data.py`.
- **Effort:** Medium. Can be built on our side — **no DataSights change required.**

### 3. Restoke checklists — Cake Logs · Litter Pickup · Daily Waste Log · Delivery Temps · Open/Close
- **Now:** "—" all venues (5 metrics).
- **Why:** **not exposed in DataSights.** Restoke's DataSights views cover
  ordering / sales / invoices / labour only; the operational checklists aren't
  published as a view. `OpCentralForms` holds form *definitions*, not per-venue
  submissions.
- **To integrate:** DataSights (with Restoke/OpCentral) must expose the
  checklist/form-submission data — **per venue, per date, completion** — as a
  queryable view. Once a view exists, each metric is one query + one rule.
- **Effort:** **Blocked on the source** adding the view. Then Low per metric.

---

## B. Per-venue coverage gaps in a live metric

### 4. Tanda — Labour % (9 of 23 venues)
- **Why:** Restoke's labour data mis-attributes venues. **12 venues have no
  labour rows at all** — their staff are dumped into aggregate buckets
  ("Yo-Chi Randwick" = 474 "employees"; "Yo-Chi Prospect"). "Randwick" itself is
  that dump (excluded), and Top Ryde (~50%) is excluded as implausible. The
  dashboard shows "—" rather than a wrong number.
- **To integrate:** fix Restoke's labour export so each venue's staff file under
  **that** venue, not an aggregate. Source-side (Restoke / the integration).
- **Effort:** **Blocked on the source.** The pipeline auto-includes the venues
  once the data is attributed correctly — no dashboard change needed.

### 5. Chi Central Policy/Comms — Macquarie — *fixed ✅*
- **Why:** OpCentral names the venue "Macquarie Park"; the venue mapping had it
  unset, so policy/comms showed "—" for Macquarie only.
- **Fix:** added "Macquarie Park" to the mapping — populates on the next refresh.

---

## Who does what

- **Finance:** decide the budget basis (#1).
- **DataSights / Restoke integration:** expose the checklist views (#3); fix the
  labour venue attribution (#4).
- **Dashboard:** build the training name-bridge (#2) on request; Macquarie fixed (#5).

None of these are dashboard *bugs* — they're upstream data availability or a
pending decision. The board is correctly showing everything it can trust today.
