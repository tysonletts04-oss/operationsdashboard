# Labour attribution — RESOLVED (moved to Tanda)

**Status:** ✅ Resolved. Labour % is now sourced from **Tanda**, the payroll /
rostering system of record. The Restoke attribution problem described below is no
longer relevant to the dashboard — **no Restoke fix is required.**

**Result:** Labour % is now live for **all 23 company venues** (coverage `23/27`).
The four franchise venues (Erina Fair, Wollongong, Charlestown, Green Hills) run
their own payroll and are not in the company Tanda org, so they intentionally
show "—".

## What changed

- Labour was previously computed from `RestokeLaborCost`, which only attributed
  cleanly for ~9–10 venues and produced some impossible figures (e.g. Top Ryde
  reading ~50%).
- The labour query now reads **`TandaTimesheetShifts`**: a shift's `department_id`
  → `TandaTeams.team_id` → `TandaLocations.name` gives the venue, and `SUM(cost)`
  (award-interpreted) is the real spend. NSW company venues only.
- Tanda attributes labour cleanly per venue, so the old de-dup / HQ-dump gymnastics
  are gone. Corrected figures land in a tight, believable 13–25% band.

See the pipeline in `build_data.py` (`SQL["labour"]` and `live_extract`).

## How to confirm

In DataSights, every company venue returns a sane headcount and cost:

```sql
SELECT loc.name venue, COUNT(DISTINCT ts.user_id) emps,
       CAST(SUM(ts.cost) AS decimal(12,0)) cost
FROM TandaTimesheetShifts ts
JOIN TandaTeams tm      ON tm.team_id      = ts.department_id
JOIN TandaLocations loc ON loc.location_id = tm.location_id
WHERE CAST(ts.date AS date) >= DATEADD(day,-12,GETDATE())
  AND loc.public_holiday_regions LIKE '%au_nsw%'
GROUP BY loc.name
ORDER BY cost DESC;
```

Every NSW company venue appears with ~8–45 staff and a plausible cost; the shared
Support Office ($0 shift cost, HQ) maps to no dashboard venue and drops out.

---

## Historical context — why Restoke was abandoned for labour

Restoke's `RestokeLaborCost` pooled many venues' staff into two catch-all buckets
("Yo-Chi Randwick" showed 474 distinct "employees", "Yo-Chi Prospect" 316), so 14
of the venues had their labour trapped in an aggregate rather than booked against
the venue where staff actually worked. Cross-referencing the "Yo-Chi Randwick"
bucket against OpCentral `workplace_name` showed only ~8 of the ~474 actually
worked at Randwick — the rest belonged to Rouse Hill, George St, Barangaroo, etc.

Rather than wait on a source-side Restoke re-attribution, the labour metric was
repointed at Tanda (which already attributes correctly), resolving the gap for all
company venues at once. Restoke remains the intended source only for the
operational checklists (cake/litter/waste/delivery/open-close), which are still not
exposed in DataSights — see [`DATA_GAPS.md`](DATA_GAPS.md).
