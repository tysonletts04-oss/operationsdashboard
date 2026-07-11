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
# 1. CONFIG — the reporting window.
#    Live mode computes this each run via resolve_snapshot() (anchors to the
#    latest COMPLETE data day — data lags ~1 day, so it's not always "today").
#    This fixed block is only the reference window for --offline / the FIXTURE.
# ---------------------------------------------------------------------------
SNAPSHOT = {
    "reportDate": "2026-07-07",          # last complete trading day (offline reference)
    "dailyDate":  "2026-07-07",
    "weekStart":  "2026-07-06",          # Monday of the report week
    "monthStart": "2026-07-01",
    "weekAgo":    "2026-07-01",          # trailing-7-days start (reviews)
    "windows": "daily = 7 Jul · WTD = 6–7 Jul · MTD = 1–7 Jul",
}

# Which systems carry real data vs. still-unwired. Drives the dashboard's
# per-source status strip.  snapshot = fully live | partial = live for some
# venues | nosource = not available in DataSights yet.
SOURCE_STATUS = {
    "Sales": "snapshot",
    "Review Tracker": "snapshot",
    "Celsi": "snapshot",
    "Tanda": "partial",          # Labour % — clean for ~9 of 23 venues (Restoke attribution)
    "Chi Central": "snapshot",   # policies + comms + training all live (23/23)
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
    ("Macquarie",        "Yo-Chi Macquarie",     "MACQ",     "Macquarie Park",     None),
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
    # Anchor: the most recent day where (nearly) all NSW venues have sales —
    # i.e. the latest COMPLETE trading day. Data lags ~1 day behind "today".
    "anchor": """
        SELECT TOP 1 s.TxnDate anchor
        FROM PolygonRedcatNetSalesByStoreDailyView s
        JOIN Venue_Master vm ON vm.Store = s.StoreName
        WHERE vm.State = '2. NSW' AND vm.Reporting = 'Yes'
        GROUP BY s.TxnDate
        HAVING COUNT(DISTINCT s.StoreName) >= 18
        ORDER BY s.TxnDate DESC""",
    "sales": """
        SELECT vm.Name venue, s.StoreName store,
          SUM(CASE WHEN s.TxnDate = :dailyDate THEN s.NetSales ELSE 0 END) d,
          SUM(CASE WHEN s.TxnDate >= :weekStart AND s.TxnDate <= :dailyDate THEN s.NetSales ELSE 0 END) w,
          SUM(CASE WHEN s.TxnDate >= :monthStart AND s.TxnDate <= :dailyDate THEN s.NetSales ELSE 0 END) m
        FROM PolygonRedcatNetSalesByStoreDailyView s
        JOIN Venue_Master vm ON vm.Store = s.StoreName
        WHERE vm.State = '2. NSW' AND vm.Reporting = 'Yes'
        GROUP BY vm.Name, s.StoreName""",
    # Reviews: a true trailing 7 days (weekly metric, stable across the month).
    "reviews": """
        SELECT LTRIM(RTRIM(location_name)) suburb,
          SUM(CASE WHEN CAST(published_on AS date) >= :weekAgo
                    AND CAST(published_on AS date) <= :dailyDate THEN 1 ELSE 0 END) trailing_week
        FROM ReviewTrackersReviews
        WHERE location_state IN ('New South Wales','NSW')
        GROUP BY LTRIM(RTRIM(location_name))""",
    # Celsi is weekly-bucketed by Date. Anchor to the latest COMPLETE week bucket
    # (>=70% of the busiest recent week's checks) so the current in-progress week
    # doesn't undercount. daily = week/7; calibrations/correctiveA = that week.
    "celsi": """
        SELECT SUBSTRING(Venue, CHARINDEX('[',Venue)+1, 4) code,
          SUM(CASE WHEN RecordType='TempCheck' THEN 1 ELSE 0 END) temp_week,
          SUM(CASE WHEN RecordType IN ('HopperCalibration','ProbeCalibration') THEN 1 ELSE 0 END) calib,
          SUM(CASE WHEN RecordType='CorrectiveAction' THEN 1 ELSE 0 END) ca,
          SUM(CASE WHEN RecordType='CorrectiveAction' AND PassFail='0' THEN 1 ELSE 0 END) ca_fail
        FROM CelsiVenueChecksView
        WHERE Venue LIKE '%.NSW]' AND CAST(Date AS date) = (
          SELECT TOP 1 CAST(Date AS date) d FROM CelsiVenueChecksView
          WHERE Venue LIKE '%.NSW]' AND RecordType='TempCheck' AND CAST(Date AS date) <= :dailyDate
          GROUP BY CAST(Date AS date)
          HAVING COUNT(*) >= 0.7 * (SELECT MAX(c) FROM (
            SELECT COUNT(*) c FROM CelsiVenueChecksView
            WHERE Venue LIKE '%.NSW]' AND RecordType='TempCheck'
              AND CAST(Date AS date) BETWEEN DATEADD(day,-60,:dailyDate) AND :dailyDate
            GROUP BY CAST(Date AS date)) t)
          ORDER BY d DESC)
        GROUP BY SUBSTRING(Venue, CHARINDEX('[',Venue)+1, 4)""",
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
    # Training: avg programme completion % per venue. Training has no venue column,
    # so bridge user_id -> user_full_name -> policy-signoff workplace_name.
    "training": """
        SELECT p.workplace_name, CAST(AVG(tp.percentage) AS decimal(5,1)) train_pct
        FROM OpCentralTrainingAllResultPrograms tp
        JOIN (SELECT user_id, MIN(user_full_name) user_full_name FROM OpCentralTrainingAllResults GROUP BY user_id) u
          ON u.user_id = tp.user_id
        JOIN (SELECT full_name, MAX(workplace_name) workplace_name FROM OpCentralPolicySignoffs GROUP BY full_name) p
          ON p.full_name = u.user_full_name
        GROUP BY p.workplace_name""",
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
    import base64
    import requests
    tok = _TOKEN.get("t")
    if tok and tok["exp"] > time.time() + 30:
        return tok["access_token"]

    token_url = os.environ["DATASIGHTS_TOKEN_URL"]
    cid = os.environ["DATASIGHTS_CLIENT_ID"].strip()
    csec = os.environ["DATASIGHTS_CLIENT_SECRET"].strip()
    base = {"grant_type": "client_credentials"}
    if os.environ.get("DATASIGHTS_SCOPE"):
        base["scope"] = os.environ["DATASIGHTS_SCOPE"].strip()

    # OAuth2 servers accept client auth two ways; try both (Basic is required by
    # some IdentityServer configs). .strip() guards against copy-paste whitespace.
    attempts = [
        {"data": {**base, "client_id": cid, "client_secret": csec}},          # client_secret_post
        {"data": base,                                                        # client_secret_basic
         "headers": {"Authorization": "Basic " + base64.b64encode(f"{cid}:{csec}".encode()).decode()}},
    ]
    last = None
    for a in attempts:
        last = requests.post(token_url, timeout=60, **a)
        if last.status_code == 200:
            j = last.json()
            _TOKEN["t"] = {"access_token": j["access_token"], "exp": time.time() + j.get("expires_in", 3600)}
            return j["access_token"]

    try:
        detail = json.dumps(last.json())          # IdentityServer returns e.g. {"error":"invalid_client"}
    except Exception:
        detail = (last.text or "")[:300]
    raise SystemExit(
        f"Token request rejected ({last.status_code}): {detail}\n"
        "  invalid_client   -> Client ID/Secret wrong, or this token endpoint isn't the right URL\n"
        "  invalid_scope    -> set DATASIGHTS_SCOPE (ask DataSights which scope)\n"
        "  unauthorized_client -> the client_credentials grant isn't enabled for this client"
    )


_MCP = {}   # per-process MCP session cache


def _jsonrpc_result(resp):
    """Extract a JSON-RPC response from an application/json OR text/event-stream reply."""
    ctype = resp.headers.get("Content-Type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    obj = json.loads(data)
                    if isinstance(obj, dict) and ("result" in obj or "error" in obj):
                        return obj
        raise SystemExit(f"MCP: no JSON-RPC result in stream: {(resp.text or '')[:300]}")
    return resp.json()


def _mcp_post(mcp_url, token, method, params, msg_id):
    import requests
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if _MCP.get("session"):
        headers["Mcp-Session-Id"] = _MCP["session"]
    payload = {"jsonrpc": "2.0", "method": method, "params": params}
    if msg_id is not None:
        payload["id"] = msg_id
    r = requests.post(mcp_url, headers=headers, json=payload, timeout=120)
    sid = r.headers.get("Mcp-Session-Id")
    if sid:
        _MCP["session"] = sid
    if r.status_code >= 400:
        raise SystemExit(f"MCP {method} failed ({r.status_code}) at {mcp_url}: {(r.text or '')[:300]}")
    return None if msg_id is None else _jsonrpc_result(r)


def _mcp_query(mcp_url, token, sql):
    """Query DataSights through its MCP endpoint (JSON-RPC: initialize -> tools/call query)."""
    if not _MCP.get("init"):
        _mcp_post(mcp_url, token, "initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "yochi-dashboard", "version": "1.0"},
        }, 1)
        try:
            _mcp_post(mcp_url, token, "notifications/initialized", {}, None)
        except SystemExit:
            pass   # some servers don't require the initialized notification
        _MCP["init"] = True
    resp = _mcp_post(mcp_url, token, "tools/call",
                     {"name": os.environ.get("DATASIGHTS_MCP_TOOL", "query"), "arguments": {"sql": sql}}, 2)
    if "error" in resp:
        raise SystemExit(f"MCP query error: {json.dumps(resp['error'])[:300]}")
    result = resp.get("result", {})
    # Tool output text is JSON like {"Rows":[...]} (same as the interactive tool).
    text = next((c.get("text") for c in result.get("content", []) if c.get("text")), None)
    if text is None:
        sc = result.get("structuredContent") or {}
        return sc.get("Rows") or sc.get("rows") or []
    obj = json.loads(text)
    return obj.get("Rows") or obj.get("rows") or obj.get("data") or []


def datasights_query(sql, params):
    """Run one query against DataSights and return a list of dict rows.

    Two transports, picked by which env var is set:
      DATASIGHTS_MCP_URL    -> query via the MCP endpoint (JSON-RPC). Preferred:
                               this is what the "AI Connect via MCP" screen exposes.
      DATASIGHTS_QUERY_URL  -> POST {"sql": ...} to a REST query endpoint (if one exists).
    Both use the OAuth2 client-credentials bearer token from _access_token().
    """
    bound = _bind(sql, params)
    token = _access_token()
    mcp_url = os.environ.get("DATASIGHTS_MCP_URL")
    query_url = os.environ.get("DATASIGHTS_QUERY_URL")
    # Auto-detect: if the query URL points at the MCP endpoint, speak MCP.
    if not mcp_url and query_url and query_url.rstrip("/").endswith("/mcp"):
        mcp_url = query_url
    if mcp_url:
        return _mcp_query(mcp_url, token, bound)

    import requests
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
    if r.status_code != 200:
        try:
            detail = json.dumps(r.json())
        except Exception:
            detail = (r.text or "")[:300]
        raise SystemExit(
            f"Query request failed ({r.status_code}) at {query_url}: {detail}\n"
            "Confirm DATASIGHTS_QUERY_URL is the SQL query endpoint and the request field "
            "name ('sql' vs 'query')."
        )
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
# tuple: (sales_d, sales_w, sales_m, ht_daily, ht_week, calib, correctiveA,
#         reviews_week, labour_pct, policy_pct, comms_pct, training_pct)
FIXTURE = {
    "George St":      (19777, 35286, 132139, 3, 21, "complete", "none", 17, 15.1, 95.5, 81.1, 83.7),
    "Erina Fair":     (15213, 30367, 108145, 3, 20, "complete", "none",  5,  _N, 92.7, 73.1, 84.1),
    "Barangaroo":     (11015, 20588, 100751, 3, 21, "complete", "none", 16, 14.7, 95.2, 77.9, 77.5),
    "Wollongong":     (12965, 24679,  97415, 3, 20, "complete", "none",  3,  _N, 95.0, 75.6, 79.9),
    "Charlestown":    (13915, 27230,  96458, 3, 21, "complete", "none",  2,  _N, 93.3, 78.6, 88.6),
    "Rouse Hill":     (12293, 22304,  93015, 3, 20, "complete", "none",  4,  _N, 97.3, 87.3, 92.0),
    "Circular Quay":  (11186, 20497,  86270, 3, 24, "complete", "none", 12,  _N, 95.1, 75.4, 79.8),
    "Macquarie":      (12222, 23603,  82619, 3, 20, "complete", "none",  5,  _N, 94.4, 77.3, 83.5),
    "Castle Towers":  (11343, 20641,  82478, 3, 19, "complete", "ok",    8,  _N, 93.9, 77.3, 87.3),
    "Burwood":        ( 9642, 19396,  78495, 4, 26, "complete", "none", 13,  _N, 98.1, 86.8, 87.2),
    "Penrith":        ( 9889, 18814,  74877, 3, 20, "complete", "none",  1,  _N, 98.3, 82.9, 92.1),
    "Manly":          ( 8658, 16555,  73836, 3, 21, "complete", "none",  9,  _N, 92.8, 68.3, 77.0),
    "Chatswood":      ( 8697, 15954,  69139, 3, 20, "missed",   "none",  8, 12.4, 91.1, 67.2, 78.4),
    "Cronulla":       ( 7374, 13486,  66725, 3, 21, "complete", "none",  7, 13.4, 97.2, 80.2, 85.2),
    "Newtown":        ( 7505, 14302,  63813, 4, 26, "complete", "none", 26, 18.3, 92.4, 71.3, 85.0),
    "Bondi":          ( 5646, 10541,  55241, 3, 20, "complete", "none",  9, 19.9, 87.1, 51.7, 65.3),
    "Coogee":         ( 5286, 10013,  52745, 3, 20, "complete", "none", 10, 17.9, 95.9, 80.1, 92.4),
    "Surry Hills":    ( 4955,  9242,  51564, 4, 26, "complete", "none",  5,  _N, 87.7, 69.7, 80.7),
    "Top Ryde":       ( 5141,  8985,  40010, 3, 20, "complete", "none",  5, 49.5, 97.1, 82.3, 89.1),
    "Randwick":       ( 4472,  8223,  38275, 4, 26, "complete", "none",  0,  _N, 87.5, 77.6, 67.9),
    "Bondi Junction": ( 4759,  8909,  36889, 3, 21, "complete", "none", 17, 19.6, 94.1, 77.0, 87.0),
    "Lane Cove":      ( 3527,  6349,  30458, 3, 20, "complete", "none",  0,  _N, 91.3, 63.5, 76.2),
    "Double Bay":     ( 3404,  6494,  29482, 2, 17, "complete", "none",  6, 15.1, 86.2, 43.5, 71.4),
}


def _venue_record(period, row):
    """Assemble one venue's per-period record in the shape the dashboard reads."""
    sd, sw, sm, ht_d, ht_w, calib, ca, rev, lab, pol, comms, train = row
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
    if train is not None:
        rec["training"] = train
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
    coverage = {k: f"{cov(k)}/{len(venues)}" for k in ("labour", "policies", "comms", "training")}
    return errors, warnings, coverage


# ---------------------------------------------------------------------------
# 6. LIVE EXTRACT — shape SQL results into the FIXTURE tuple form.
#    (Stub wiring: run each SQL, map by venue via the VENUES table, then reuse
#    the exact same transform/validation as offline. Fill in once the query
#    function works — the mapping keys are already defined above.)
# ---------------------------------------------------------------------------
def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _index(rows, key):
    return {r[key]: r for r in (rows or []) if isinstance(r, dict) and r.get(key) is not None}


# Reviews name a few venues differently from their display name.
REVIEW_ALIAS = {"George St": "George Street", "Rouse Hill": "Rouse Hill Town Centre"}


def resolve_snapshot():
    """Discover the reporting window dynamically each run: anchor to the latest
    COMPLETE NSW sales day (data lags ~1 day behind 'today'), then derive the
    week/month boundaries from it. This is what makes the report date advance."""
    rows = datasights_query(SQL["anchor"], {})
    if not rows:
        raise SystemExit("resolve_snapshot(): no complete sales day found")
    anchor = str(rows[0]["anchor"])[:10]
    d = _dt.date.fromisoformat(anchor)
    month_start = d.replace(day=1)
    week_start = d - _dt.timedelta(days=d.weekday())      # Monday of the report week
    week_ago = d - _dt.timedelta(days=6)                  # trailing 7 days (inclusive)
    ws = f"{week_start.day} {week_start:%b}" if week_start.month != d.month else f"{week_start.day}"
    windows = f"daily = {d.day} {d:%b} · WTD = {ws}–{d.day} {d:%b} · MTD = 1–{d.day} {d:%b}"
    return {
        "reportDate": anchor, "dailyDate": anchor,
        "weekStart": week_start.isoformat(), "monthStart": month_start.isoformat(),
        "weekAgo": week_ago.isoformat(), "windows": windows,
    }


def live_extract(snap):
    """Query DataSights live and shape the results into the FIXTURE tuple form,
    applying the same normalisation the offline snapshot encodes."""
    p = {k: snap[k] for k in ("dailyDate", "weekStart", "monthStart", "weekAgo")}
    sales_by_store = _index(datasights_query(SQL["sales"], p), "store")
    reviews_by_sub = _index(datasights_query(SQL["reviews"], p), "suburb")
    celsi_by_code  = _index(datasights_query(SQL["celsi"], p), "code")
    labour_by_venue = _index(datasights_query(SQL["labour"], p), "venue")
    policy_by_wp   = _index(datasights_query(SQL["policies"], p), "workplace_name")
    comms_by_wp    = _index(datasights_query(SQL["comms"], p), "workplace_name")
    train_by_wp    = _index(datasights_query(SQL["training"], p), "workplace_name")

    fixture = {}
    for display, sales_store, code, opcentral_wp, labour_venue in VENUES:
        s = sales_by_store.get(sales_store)
        if not s:
            print(f"WARN  no sales row for {display} (store={sales_store})", file=sys.stderr)
            continue
        sd, sw, sm = round(_num(s["d"])), round(_num(s["w"])), round(_num(s["m"]))

        # Celsi (weekly-bucketed): count -> daily rate; status from calib/corrective.
        c = celsi_by_code.get(code, {})
        temp_week = int(_num(c.get("temp_week")))
        ht_daily = round(temp_week / 7) if temp_week else 0
        calib = "complete" if _num(c.get("calib")) > 0 else "missed"
        ca_n, ca_fail = _num(c.get("ca")), _num(c.get("ca_fail"))
        correctiveA = "issue" if ca_fail > 0 else ("ok" if ca_n > 0 else "none")

        rv = reviews_by_sub.get(REVIEW_ALIAS.get(display, display))
        reviews_week = int(_num(rv["trailing_week"])) if rv else 0

        # Labour %: cost / net sales, with the HQ-dump + plausibility guards.
        labour_pct = None
        if labour_venue:
            lr = labour_by_venue.get(labour_venue)
            if lr and _num(lr.get("emps")) <= 120 and sm > 0:
                pct = round(100.0 * _num(lr.get("labour_cost")) / sm, 1)
                if 5 <= pct <= 45:
                    labour_pct = pct

        pol = policy_by_wp.get(opcentral_wp) if opcentral_wp else None
        cm = comms_by_wp.get(opcentral_wp) if opcentral_wp else None
        tr = train_by_wp.get(opcentral_wp) if opcentral_wp else None
        policy_pct = round(_num(pol["read_pct"]), 1) if pol else None
        comms_pct = round(_num(cm["read_pct"]), 1) if cm else None
        training_pct = round(_num(tr["train_pct"]), 1) if tr else None

        fixture[display] = (sd, sw, sm, ht_daily, temp_week, calib, correctiveA,
                            reviews_week, labour_pct, policy_pct, comms_pct, training_pct)
    return fixture


def main():
    ap = argparse.ArgumentParser(description="Rebuild data.json for the NSW Operations Dashboard")
    ap.add_argument("--offline", action="store_true", help="rebuild from the bundled snapshot (no DB)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data.json"))
    args = ap.parse_args()

    if args.offline:
        snap, fixture = SNAPSHOT, FIXTURE
    else:
        snap = resolve_snapshot()
        print(f"Resolved window: {snap['reportDate']} ({snap['windows']})", file=sys.stderr)
        fixture = live_extract(snap)
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
            "reportDate": snap["reportDate"],
            "generatedAt": generated,
            "windows": snap["windows"],
            "venues": len(periods["daily"]),
            "sources": SOURCE_STATUS,
            "coverage": coverage,
        },
        "periods": periods,
    }

    # Only rewrite (and therefore commit/redeploy) when the DATA actually changed
    # — ignore the generatedAt timestamp. Lets the job run every few hours to catch
    # new data promptly without spamming commits when nothing has moved.
    def _without_ts(p):
        import copy
        c = copy.deepcopy(p)
        c.get("meta", {}).pop("generatedAt", None)
        return c
    try:
        with open(args.out) as f:
            if _without_ts(json.load(f)) == _without_ts(payload):
                print(f"No change (report {snap['reportDate']}); data.json left as-is.")
                return
    except (FileNotFoundError, ValueError):
        pass

    with open(args.out, "w") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)
    print(f"Wrote {args.out}: report {snap['reportDate']}, coverage={coverage}, generatedAt={generated}")


if __name__ == "__main__":
    main()
