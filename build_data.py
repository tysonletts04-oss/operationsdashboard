#!/usr/bin/env python3
"""
build_data.py — regenerate data.json for the NSW Operations Dashboard.

WHAT THIS IS
------------
The dashboard (index.html) is a static shell that fetches ./data.json at load.
This script is the *only* thing that runs each day: it queries DataSights,
normalises the results, validates them, and writes data.json. Run it on a
schedule (see .github/workflows/refresh.yml) and the dashboard refreshes itself.

The real IP is not the HTML — it's the normalisation logic below: the venue-name
mapping across six systems, the labour de-duplication, the Celsi weekly-bucket
handling, and the validation gates that stop bad data reaching the board.

RUNNING IT
----------
  python build_data.py --offline     # rebuild from the bundled snapshot (no DB)
  python build_data.py               # live: query DataSights, needs a credential

CREDENTIAL (live mode)
----------------------
A scheduled job cannot use the interactive DataSights/MCP login. It uses the
DataSights "Custom / API" connect flow: click *Generate Credentials* to get a
Client ID + Client Secret (OAuth2 client-credentials). Set these in the
environment (put the SECRET in GitHub Actions secrets, never in code):

  DATASIGHTS_TOKEN_URL     the /connect/token URL from the connect screen
  DATASIGHTS_QUERY_URL     the query endpoint (confirm the path with DataSights)
  DATASIGHTS_CLIENT_ID
  DATASIGHTS_CLIENT_SECRET
  DATASIGHTS_SCOPE         optional — only if DataSights requires a scope

datasights_query() already implements the token exchange + query POST; the only
things to confirm against a real response are the query endpoint URL, the request
field name ('sql' vs 'query'), and the response envelope (see the function).
"""

import argparse
import datetime as _dt
import json
import os
import sys

# ---------------------------------------------------------------------------
# 1. CONFIG — the reporting window. In live mode these derive from "today".
# ---------------------------------------------------------------------------
SNAPSHOT = {
    "reportDate": "2026-07-07",          # last complete trading day
    "dailyDate":  "2026-07-07",
    "weekStart":  "2026-07-06",          # Monday of the report week
    "monthStart": "2026-07-01",
    "windows": "daily = 7 Jul · WTD = 6–7 Jul · MTD = 1–7 Jul",
}

# Which systems carry real data vs. still-unwired. Drives the dashboard's
# per-source status strip.  snapshot = fully live | partial = live for some
# venues | nosource = not available in DataSights yet.
SOURCE_STATUS = {
    "Sales": "snapshot",
    "Review Tracker": "snapshot",
    "Celsi": "snapshot",
    "Tanda": "partial",          # Labour % — clean for ~10 of 23 venues
    "Chi Central": "partial",    # policies + comms live; training has no venue dim
    "Restoke": "nosource",       # cake/litter/waste/delivery/open-close not exposed
}

# ---------------------------------------------------------------------------
# 2. VENUE MAPPING — the same venue is named differently in every system.
#    This table is the join key. Add a row to onboard a venue; leave a field
#    None where that system has no match (metric renders "—").
#    (Codes match the [XXXX.NSW] suffix used by Celsi and the Xero Location tag.)
# ---------------------------------------------------------------------------
VENUES = [
    # display            sales_store             celsi/xero  opcentral_wp          labour_venue
    ("George St",        "Yo-Chi George St",     "GEOR",     "George Street",      "Yo-Chi George St"),
    ("Erina Fair",       "Yo-Chi Erina Fair",    "ERIN",     "Erina Fair",         None),
    ("Barangaroo",       "Yo-Chi Barangaroo",    "BARA",     "Barangaroo",         "Yo-Chi Barangaroo"),
    ("Wollongong",       "Yo-Chi Wollongong",    "WOLL",     "Wollongong",         None),
    ("Charlestown",      "Yo-Chi Charlestown",   "CHAR",     "Charlestown Square", None),
    ("Rouse Hill",       "Yo-Chi Rouse Hill",    "ROUS",     "Rouse Hill",         None),
    ("Circular Quay",    "Yo-Chi Circular Quay", "CIRC",     "Circular Quay",      None),
    ("Macquarie",        "Yo-Chi Macquarie",     "MACQ",     None,                 None),
    ("Castle Towers",    "Yo-Chi Castle Towers", "CAST",     "Castle Towers",      None),
    ("Burwood",          "Yo-Chi Burwood",       "BURW",     "Burwood",            None),
    ("Penrith",          "Yo-Chi Penrith",       "PENR",     "Penrith",            None),
    ("Manly",            "Yo-Chi Manly",         "MANL",     "Manly",              None),
    ("Chatswood",        "Yo-Chi Chatswood",     "CHAT",     "Chatswood",          "Yo-Chi Chatswood"),
    ("Cronulla",         "Yo-Chi Cronulla",      "CRON",     "Cronulla",           "Yo-Chi Cronulla"),
    ("Newtown",          "Yo-Chi Newtown",       "NEWT",     "Newtown",            "Yo-Chi Newtown [ETC HQ]"),
    ("Bondi",            "Yo-Chi Bondi",         "BOND",     "Bondi",              "Yo-Chi Bondi"),
    ("Coogee",           "Yo-Chi Coogee",        "COOG",     "Coogee",             "Yo-Chi Coogee"),
    ("Surry Hills",      "Yo-Chi Surry Hills",   "SURR",     "Surry Hills",        None),
    ("Top Ryde",         "Yo-Chi Top Ryde",      "TOPR",     "Top Ryde",           "Yo-Chi Top Ryde"),
    ("Randwick",         "Yo-Chi Randwick",      "RAND",     "Randwick",           None),   # labour = HQ-dump, excluded
    ("Bondi Junction",   "Yo-Chi Bondi Junction","BNDJ",     "Bondi Junction",     "Yo-Chi Bondi Junction"),
    ("Lane Cove",        "Yo-Chi Lane Cove",     "LANE",     "Lane Cove",          None),
    ("Double Bay",       "Yo-Chi Double Bay",    "DOUB",     "Double Bay",         "Yo-Chi Double Bay"),
]

# ---------------------------------------------------------------------------
# 3. SQL — the live queries (documented here; used when a credential is set).
#    Each returns the aggregates the transform needs, keyed by venue.
# ---------------------------------------------------------------------------
SQL = {
    "sales": """
        SELECT vm.Name venue, s.StoreName store,
          SUM(CASE WHEN s.TxnDate = :dailyDate THEN s.NetSales ELSE 0 END) d,
          SUM(CASE WHEN s.TxnDate >= :weekStart AND s.TxnDate <= :dailyDate THEN s.NetSales ELSE 0 END) w,
          SUM(CASE WHEN s.TxnDate >= :monthStart AND s.TxnDate <= :dailyDate THEN s.NetSales ELSE 0 END) m
        FROM PolygonRedcatNetSalesByStoreDailyView s
        JOIN Venue_Master vm ON vm.Store = s.StoreName
        WHERE vm.State = '2. NSW' AND vm.Reporting = 'Yes'
        GROUP BY vm.Name, s.StoreName""",
    "reviews": """
        SELECT LTRIM(RTRIM(location_name)) suburb,
          SUM(CASE WHEN CAST(published_on AS date) >= :monthStart
                    AND CAST(published_on AS date) <= :dailyDate THEN 1 ELSE 0 END) trailing_week
        FROM ReviewTrackersReviews
        WHERE location_state IN ('New South Wales','NSW')
        GROUP BY LTRIM(RTRIM(location_name))""",
    # Celsi is weekly-bucketed by Date; the latest full-week bucket is one week
    # of checks (~21). daily = week/7. calibrations/correctiveA = week status.
    "celsi": """
        SELECT SUBSTRING(Venue, CHARINDEX('[',Venue)+1, 4) code,
          SUM(CASE WHEN RecordType='TempCheck' AND Date >= :monthStart AND Date <= :dailyDate THEN 1 ELSE 0 END) temp_week,
          SUM(CASE WHEN RecordType IN ('HopperCalibration','ProbeCalibration') AND Date >= :monthStart AND Date <= :dailyDate THEN 1 ELSE 0 END) calib,
          SUM(CASE WHEN RecordType='CorrectiveAction' AND Date >= :monthStart AND Date <= :dailyDate THEN 1 ELSE 0 END) ca,
          SUM(CASE WHEN RecordType='CorrectiveAction' AND PassFail='0' AND Date >= :monthStart AND Date <= :dailyDate THEN 1 ELSE 0 END) ca_fail
        FROM CelsiVenueChecksView WHERE Venue LIKE '%.NSW]' GROUP BY SUBSTRING(Venue, CHARINDEX('[',Venue)+1, 4)""",
    # Labour: de-dupe exact-duplicate rows, then cost / net sales. HQ-dump venues
    # (hundreds of "employees") are excluded by the sanity gate downstream.
    "labour": """
        SELECT venue, SUM(total) labour_cost, COUNT(DISTINCT employee_name) emps
        FROM (SELECT DISTINCT venue, date, employee_name, hours, rate, TRY_CAST(total AS float) total
              FROM RestokeLaborCost WHERE date >= :monthStart AND date <= :dailyDate) x
        WHERE venue LIKE '%Yo-Chi%' GROUP BY venue""",
    "policies": """
        SELECT workplace_name, 100.0*SUM(CASE WHEN is_read=1 THEN 1 ELSE 0 END)/COUNT(*) read_pct
        FROM OpCentralPolicySignoffs GROUP BY workplace_name""",
    "comms": """
        SELECT workplace_name, 100.0*SUM(CASE WHEN is_read=1 THEN 1 ELSE 0 END)/COUNT(*) read_pct
        FROM OpCentralNewsSignoffs GROUP BY workplace_name""",
}


def _bind(sql, params):
    """Substitute :named date params as quoted literals (dates only — no user input)."""
    out = sql
    for k, v in (params or {}).items():
        out = out.replace(f":{k}", f"'{v}'")
    return out


_TOKEN = {}   # simple in-process cache: {"access_token": ..., "exp": epoch}


def _access_token():
    """OAuth2 client-credentials — exchange Client ID/Secret for a bearer token.

    Matches the DataSights "Custom / API" connect flow (Generate Credentials).
    Env vars (set the SECRET as a GitHub Actions secret, never in code):
        DATASIGHTS_TOKEN_URL      e.g. https://<your-datasights>/connect/token
        DATASIGHTS_CLIENT_ID
        DATASIGHTS_CLIENT_SECRET
        DATASIGHTS_SCOPE          (optional — only if DataSights requires one)
    """
    import time
    import requests
    tok = _TOKEN.get("t")
    if tok and tok["exp"] > time.time() + 30:
        return tok["access_token"]
    data = {
        "grant_type": "client_credentials",
        "client_id": os.environ["DATASIGHTS_CLIENT_ID"],
        "client_secret": os.environ["DATASIGHTS_CLIENT_SECRET"],
    }
    if os.environ.get("DATASIGHTS_SCOPE"):
        data["scope"] = os.environ["DATASIGHTS_SCOPE"]
    r = requests.post(os.environ["DATASIGHTS_TOKEN_URL"], data=data, timeout=60)
    r.raise_for_status()
    j = r.json()
    _TOKEN["t"] = {"access_token": j["access_token"], "exp": time.time() + j.get("expires_in", 3600)}
    return j["access_token"]


def datasights_query(sql, params):
    """Run one query against DataSights and return a list of dict rows.

    Uses the OAuth2 client-credentials token from _access_token(), then POSTs the
    SQL to the DataSights query endpoint. The only thing to confirm against a real
    response is the request field name and the response envelope (marked below) —
    everything else in this file is source-agnostic.

    Env: DATASIGHTS_QUERY_URL   the REST query endpoint (e.g. https://<host>/api/query)
    """
    import requests
    query_url = os.environ.get("DATASIGHTS_QUERY_URL")
    if not query_url:
        raise NotImplementedError(
            "Set DATASIGHTS_QUERY_URL + DATASIGHTS_TOKEN_URL + DATASIGHTS_CLIENT_ID/SECRET "
            "(from the DataSights 'Custom / API' tab), or run with --offline."
        )
    r = requests.post(
        query_url,
        headers={"Authorization": f"Bearer {_access_token()}", "Accept": "application/json"},
        json={"sql": _bind(sql, params)},          # <-- confirm the field name ('sql'/'query')
        timeout=120,
    )
    r.raise_for_status()
    body = r.json()
    # Tolerant to the exact envelope — DataSights returned {"Rows":[...]} in testing.
    if isinstance(body, list):
        return body
    return body.get("Rows") or body.get("rows") or body.get("data") or []


# ---------------------------------------------------------------------------
# 4. OFFLINE SNAPSHOT — the real figures already pulled from DataSights
#    (2026-07-07). Lets the pipeline run and validate with no DB, and gives
#    the dashboard working data immediately. Live mode replaces this via SQL.
#    tuple: (sales_d, sales_w, sales_m, ht_daily, ht_week, calib, correctiveA,
#            reviews_week, labour_pct, policy_pct, comms_pct)
# ---------------------------------------------------------------------------
_N = None
FIXTURE = {
    "George St":      (19777, 35286, 132139, 3, 21, "complete", "none", 17, 15.1, 95.5, 81.1),
    "Erina Fair":     (15213, 30367, 108145, 3, 20, "complete", "none",  5,  _N, 92.7, 73.1),
    "Barangaroo":     (11015, 20588, 100751, 3, 21, "complete", "none", 16, 14.7, 95.2, 77.9),
    "Wollongong":     (12965, 24679,  97415, 3, 20, "complete", "none",  3,  _N, 95.0, 75.6),
    "Charlestown":    (13915, 27230,  96458, 3, 21, "complete", "none",  2,  _N, 93.3, 78.6),
    "Rouse Hill":     (12293, 22304,  93015, 3, 20, "complete", "none",  4,  _N, 97.3, 87.3),
    "Circular Quay":  (11186, 20497,  86270, 3, 24, "complete", "none", 12,  _N, 95.1, 75.4),
    "Macquarie":      (12222, 23603,  82619, 3, 20, "complete", "none",  5,  _N,  _N,  _N),
    "Castle Towers":  (11343, 20641,  82478, 3, 19, "complete", "ok",    8,  _N, 93.9, 77.3),
    "Burwood":        ( 9642, 19396,  78495, 4, 26, "complete", "none", 13,  _N, 98.1, 86.8),
    "Penrith":        ( 9889, 18814,  74877, 3, 20, "complete", "none",  1,  _N, 98.3, 82.9),
    "Manly":          ( 8658, 16555,  73836, 3, 21, "complete", "none",  9,  _N, 92.8, 68.3),
    "Chatswood":      ( 8697, 15954,  69139, 3, 20, "missed",   "none",  8, 12.4, 91.1, 67.2),
    "Cronulla":       ( 7374, 13486,  66725, 3, 21, "complete", "none",  7, 13.4, 97.2, 80.2),
    "Newtown":        ( 7505, 14302,  63813, 4, 26, "complete", "none", 26, 18.3, 92.4, 71.3),
    "Bondi":          ( 5646, 10541,  55241, 3, 20, "complete", "none",  9, 19.9, 87.1, 51.7),
    "Coogee":         ( 5286, 10013,  52745, 3, 20, "complete", "none", 10, 17.9, 95.9, 80.1),
    "Surry Hills":    ( 4955,  9242,  51564, 4, 26, "complete", "none",  5,  _N, 87.7, 69.7),
    "Top Ryde":       ( 5141,  8985,  40010, 3, 20, "complete", "none",  5, 49.5, 97.1, 82.3),
    "Randwick":       ( 4472,  8223,  38275, 4, 26, "complete", "none",  0,  _N, 87.5, 77.6),
    "Bondi Junction": ( 4759,  8909,  36889, 3, 21, "complete", "none", 17, 19.6, 94.1, 77.0),
    "Lane Cove":      ( 3527,  6349,  30458, 3, 20, "complete", "none",  0,  _N, 91.3, 63.5),
    "Double Bay":     ( 3404,  6494,  29482, 2, 17, "complete", "none",  6, 15.1, 86.2, 43.5),
}


def _venue_record(period, row):
    """Assemble one venue's per-period record in the shape the dashboard reads."""
    sd, sw, sm, ht_d, ht_w, calib, ca, rev, lab, pol, comms = row
    sales_actual = {"daily": sd, "wtd": sw, "mtd": sm}[period]
    hopper = ht_d if period == "daily" else ht_w   # daily rate vs weekly count
    rec = {
        "hopperTemps": hopper,
        "calibrations": calib,
        "correctiveA": ca,
        "reviews": rev,                        # weekly metric — same across periods
        "sales": {"actual": sales_actual, "budget": None},   # budget: basis needs sign-off
    }
    if lab is not None:
        rec["labour"] = {"pct": lab, "budgetPct": None}      # no labour budget source
    if pol is not None:
        rec["policies"] = pol
    if comms is not None:
        rec["comms"] = comms
    return rec


def build_periods(fixture):
    return {p: {v: _venue_record(p, row) for v, row in fixture.items()}
            for p in ("daily", "wtd", "mtd")}


# ---------------------------------------------------------------------------
# 5. VALIDATION GATES — refuse to publish nonsense. Extend as trust grows.
# ---------------------------------------------------------------------------
def validate(periods):
    errors, warnings = [], []
    venues = list(periods["daily"].keys())
    if not venues:
        errors.append("no venues produced")

    for p in ("daily", "wtd", "mtd"):
        for v, rec in periods[p].items():
            sa = rec.get("sales", {}).get("actual")
            if sa is None or sa < 0:
                errors.append(f"{p}/{v}: missing or negative sales")
            lab = rec.get("labour")
            if lab and not (5 <= lab["pct"] <= 45):
                warnings.append(f"{p}/{v}: labour {lab['pct']}% outside 5-45% — check for HQ-dump/mismatch")
            for k in ("policies", "comms"):
                if k in rec and not (0 <= rec[k] <= 100):
                    errors.append(f"{p}/{v}: {k} {rec[k]} not a valid %")

    # coverage report (not fatal — surfaced on the board as "—")
    cov = lambda key: sum(1 for r in periods["mtd"].values() if key in r)
    coverage = {k: f"{cov(k)}/{len(venues)}" for k in ("labour", "policies", "comms")}
    return errors, warnings, coverage


# ---------------------------------------------------------------------------
# 6. LIVE EXTRACT — shape SQL results into the FIXTURE tuple form.
#    (Stub wiring: run each SQL, map by venue via the VENUES table, then reuse
#    the exact same transform/validation as offline. Fill in once the query
#    function works — the mapping keys are already defined above.)
# ---------------------------------------------------------------------------
def live_extract():
    p = {k: SNAPSHOT[k] for k in ("dailyDate", "weekStart", "monthStart")}
    sales    = datasights_query(SQL["sales"], p)
    reviews  = datasights_query(SQL["reviews"], p)
    celsi    = datasights_query(SQL["celsi"], p)
    labour   = datasights_query(SQL["labour"], p)
    policies = datasights_query(SQL["policies"], p)
    comms    = datasights_query(SQL["comms"], p)
    # TODO: join these by the VENUES mapping into the FIXTURE tuple shape,
    #       applying the labour HQ-dump guard (drop venues with emps > ~120)
    #       and hopper daily = round(temp_week / 7). The offline FIXTURE above
    #       is the reference output for 2026-07-07 to test this against.
    raise NotImplementedError("live_extract(): map query rows to FIXTURE shape once datasights_query() is wired")


def main():
    ap = argparse.ArgumentParser(description="Rebuild data.json for the NSW Operations Dashboard")
    ap.add_argument("--offline", action="store_true", help="rebuild from the bundled snapshot (no DB)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data.json"))
    args = ap.parse_args()

    fixture = FIXTURE if args.offline else live_extract()
    periods = build_periods(fixture)
    errors, warnings, coverage = validate(periods)

    for w in warnings:
        print(f"WARN  {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR {e}", file=sys.stderr)
        print("Validation failed — data.json NOT written (dashboard keeps last good copy).", file=sys.stderr)
        sys.exit(1)

    generated = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "meta": {
            "reportDate": SNAPSHOT["reportDate"],
            "generatedAt": generated,
            "windows": SNAPSHOT["windows"],
            "venues": len(periods["daily"]),
            "sources": SOURCE_STATUS,
            "coverage": coverage,
        },
        "periods": periods,
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"Wrote {args.out}: {len(periods['daily'])} venues, coverage={coverage}, generatedAt={generated}")


if __name__ == "__main__":
    main()
