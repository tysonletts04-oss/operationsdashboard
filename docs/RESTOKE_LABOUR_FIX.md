# Restoke labour fix — venue attribution

**For:** whoever administers Restoke for Yo-Chi (and/or the Restoke ↔ DataSights
integration owner).
**Impact:** Labour % is missing for **14 of 23 NSW venues** on the operations
dashboard, because their staff labour is not recorded against the right venue in
Restoke.
**Nothing to change on the dashboard** — once Restoke attributes labour correctly,
the numbers flow through DataSights and appear automatically.

## The problem

Restoke's labour data (`RestokeLaborCost` in DataSights) is pooling many venues'
staff into two "catch-all" venue buckets instead of each venue. Over 8 days
(1–8 Jul 2026), deduplicated:

| Restoke venue | Distinct "employees" | Labour cost | Expected |
|---|---|---|---|
| **Yo-Chi Randwick** | **474** | **$830,834** | ~15–50 staff, ~$8–20k |
| **Yo-Chi Prospect** | **316** | **$823,197** | ~15–50 staff, ~$8–20k |
| Yo-Chi Top Ryde | 46 | $22,496 | plausibility-flagged (~50% labour) |

474 and 316 distinct employees under one store is impossible (a Yo-Chi venue runs
~15–50 staff). These two buckets are absorbing the staff that should sit against
the venues below.

## Proof it's a pooling problem (not real headcount)

Cross-referencing the **employees inside the "Yo-Chi Randwick" labour bucket**
against where each person actually works (OpCentral `workplace_name`) shows the
bucket is full of *other venues'* staff — **only 8 of the ~474 actually work at
Randwick**:

| Where they actually work | Staff mis-filed into "Yo-Chi Randwick" |
|---|---|
| Rouse Hill | 32 |
| George Street | 30 |
| Barangaroo | 25 |
| Circular Quay | 22 |
| Castle Towers | 22 |
| Manly | 20 |
| Chatswood | 19 |
| Macquarie Park | 18 |
| Burwood / Penrith / Top Ryde | 16 each |
| Cronulla 14 · Newtown 13 · Coogee 11 · Bondi 11 · Surry Hills 10 · Lane Cove 8 | … |
| **Randwick (actually Randwick)** | **8** |

Consequence: the missing venues' labour is trapped here, **and** the venues that
*do* report (George St, Barangaroo, Chatswood…) are **understated**, because some
of their staff are split into this bucket too. Fixing attribution corrects both.

Reproduce:
```sql
SELECT p.workplace_name AS actual_venue, COUNT(DISTINCT l.employee_name) staff
FROM (SELECT DISTINCT employee_name FROM RestokeLaborCost
      WHERE venue='Yo-Chi Randwick' AND date >= DATEADD(day,-8,GETDATE())) l
JOIN (SELECT DISTINCT full_name, workplace_name FROM OpCentralPolicySignoffs) p
  ON p.full_name = l.employee_name
GROUP BY p.workplace_name ORDER BY staff DESC;
```

## Affected venues (Labour % currently "—")

Erina Fair · Wollongong · Charlestown · Rouse Hill · Circular Quay · Macquarie ·
Castle Towers · Burwood · Penrith · Manly · Surry Hills · Top Ryde · Randwick ·
Lane Cove

(The 9 venues that *do* report correctly — George St, Barangaroo, Chatswood,
Cronulla, Newtown, Bondi, Coogee, Bondi Junction, Double Bay — show Labour %
fine, which is how we know the pipeline works.)

## What to fix in Restoke

1. Confirm every NSW venue exists as its **own location / cost centre** in Restoke
   (the 14 above may be missing, or merged into "Randwick"/"Prospect").
2. **Reassign employees to their correct home venue** so their rostered/timesheet
   labour is booked against the venue they actually work at — not pooled into
   "Yo-Chi Randwick" or "Yo-Chi Prospect".
3. Re-run / re-sync the labour feed so DataSights picks up the corrected mapping.

## How to confirm it's fixed

Run this in DataSights — every venue should have a **sane headcount (~15–50)** and
**no venue over ~120**:

```sql
SELECT venue, COUNT(DISTINCT employee_name) emps, CAST(SUM(total) AS decimal(12,0)) cost
FROM (SELECT DISTINCT venue, date, employee_name, hours, rate, TRY_CAST(total AS float) total
      FROM RestokeLaborCost
      WHERE date >= DATEADD(day,-8,GETDATE())) x
WHERE venue LIKE '%Yo-Chi%'
GROUP BY venue
ORDER BY emps DESC;
```

- **Before:** "Yo-Chi Randwick" 474, "Yo-Chi Prospect" 316 at the top.
- **After (fixed):** no venue over ~120; the 14 venues above each appear with a
  realistic headcount.

Once that's true, the dashboard's Labour % for those venues populates on the next
daily refresh — **no dashboard change required** (the pipeline computes
labour cost ÷ net sales per venue and only excludes venues with >120 staff or an
implausible % ; corrected data clears both filters).

## Contact

Dashboard side: the pipeline is ready and waiting — as soon as `RestokeLaborCost`
attributes labour per venue, coverage goes from 9/23 toward 23/23 automatically.
