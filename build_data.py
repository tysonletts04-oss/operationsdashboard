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
mapping across six systems, the Tanda department->location labour attribution, the
Celsi weekly-bucket handling, and the validation gates that stop bad data reaching
the board.

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
    "weekStart":  "2026-07-06",          # Monday of the report week (also the reviews week start)
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
    "Tanda": "snapshot",         # Labour % — real timesheet cost, all 23 company venues (franchises excl.)
    "Chi Central": "snapshot",   # policies + comms + training all live (23/23)
    "Restoke": "nosource",       # cake/litter/waste/delivery/open-close not exposed
}

# ---------------------------------------------------------------------------
# 2. VENUE MAPPING — the same venue is named differently in every system.
#    This table is the join key. Add a row to onboard a venue; leave a field
#    None where that system has no match (metric renders "—").
#    (Codes match the [XXXX.NSW] suffix used by Celsi and the Xero Location tag.)
# ---------------------------------------------------------------------------
#    labour_venue = the Tanda *location* name (TandaLocations.name). Labour comes
#    from Tanda timesheets now, so this is the join key into the labour query.
#    Franchise venues (the four "F." Celsi codes) run their own payroll and are
#    NOT in the company Tanda org, so they carry None and render labour as "—".
VENUES = [
    # display            sales_store             celsi/xero  opcentral_wp          tanda_location
    ("George St",        "Yo-Chi George St",     "GEOR",     "George Street",      "GeorgeST"),
    ("Erina Fair",       "Yo-Chi Erina Fair",    "F.ERIN",   "Erina Fair",         None),          # franchise — not in Tanda
    ("Barangaroo",       "Yo-Chi Barangaroo",    "BARA",     "Barangaroo",         "Barangaroo"),
    ("Wollongong",       "Yo-Chi Wollongong",    "F.WOLL",   "Wollongong",         None),          # franchise — not in Tanda
    ("Charlestown",      "Yo-Chi Charlestown",   "F.CSQU",   "Charlestown Square", None),          # franchise — not in Tanda
    ("Rouse Hill",       "Yo-Chi Rouse Hill",    "ROUS",     "Rouse Hill",         "Rouse Hill"),
    ("Circular Quay",    "Yo-Chi Circular Quay", "CRLQ",     "Circular Quay",      "Circular Quay"),
    ("Macquarie",        "Yo-Chi Macquarie",     "MACQ",     "Macquarie Park",     "Macquarie Park"),
    ("Castle Towers",    "Yo-Chi Castle Towers", "CAST",     "Castle Towers",      "Castle Towers"),
    ("Burwood",          "Yo-Chi Burwood",       "BURW",     "Burwood",            "Burwood"),
    ("Penrith",          "Yo-Chi Penrith",       "PENR",     "Penrith",            "Penrith"),
    ("Manly",            "Yo-Chi Manly",         "MANL",     "Manly",              "Manly Yo-Chi"),
    ("Chatswood",        "Yo-Chi Chatswood",     "CHAT",     "Chatswood",          "Chatswood"),
    ("Cronulla",         "Yo-Chi Cronulla",      "CRON",     "Cronulla",           "Cronulla"),
    ("Newtown",          "Yo-Chi Newtown",       "NEWT",     "Newtown",            "Newtown"),
    ("Bondi",            "Yo-Chi Bondi",         "BOND",     "Bondi",              "Bondi"),
    ("Coogee",           "Yo-Chi Coogee",        "COOG",     "Coogee",             "Coogee"),
    ("Surry Hills",      "Yo-Chi Surry Hills",   "SURR",     "Surry Hills",        "Surry Hills"),
    ("Top Ryde",         "Yo-Chi Top Ryde",      "TOPR",     "Top Ryde",           "Top Ryde"),
    ("Randwick",         "Yo-Chi Randwick",      "RAND",     "Randwick",           "Randwick"),
    ("Bondi Junction",   "Yo-Chi Bondi Junction","BNDJ",     "Bondi Junction",     "Bondi Junction"),
    ("Lane Cove",        "Yo-Chi Lane Cove",     "LANE",     "Lane Cove",          "Lane Cove"),
    ("Double Bay",       "Yo-Chi Double Bay",    "DOUB",     "Double Bay",         "Double Bay"),
    # Newly-onboarded NSW venues (added Jul 2026).
    ("Chippendale",      "Yo-Chi Chippendale",   "CHIP",     "Chippendale",        "Chippendale"),
    ("Crows Nest",       "Yo-Chi Crows Nest",    "CN",       "Crows Nest",         "Crows Nest"),
    ("Fish Market",      "Yo-Chi Fish Market",   "FISH",     "Fish Market",        "Fish Market"),
    ("Green Hills",      "Yo-Chi Greenhills",    "F.GREE",   "Greenhills",         None),          # franchise — not in Tanda
]

# ---------------------------------------------------------------------------
# 3. SQL — the live queries (documented here; used when a credential is set).
#    Each returns the aggregates the transform needs, keyed by venue.
# ---------------------------------------------------------------------------
# NSW store names (the sales-view StoreName for every venue) built from VENUES —
# our own NSW allow-list, so the anchor scopes to NSW without Venue_Master. A
# permission change on that table then can't stall the whole refresh.
_NSW_STORE_IN = ", ".join("'" + v[1].replace("'", "''") + "'" for v in VENUES)

# Reusable-bowl discount compliance (Polygon line items). A sale that rings up any of
# these bowl tares should carry the "Reusable 10% Off" discount line. Mitch's official
# Polygon report only counts a sale as a MISS when it carried NO discount of any kind:
# a bowl sale that was comped or discounted another way (Team Free Yo-Chi, Free Yo-Chi,
# any LAM tier, vouchers, loyalty redemptions) is excluded, because a different discount
# was legitimately applied instead of the 10%. Every discount line in Polygon lives in
# the "POS Discounts" category, so that category is how we catch "any discount" without
# hard-coding each promo name.
REUSABLE_ITEMS = ("Go Bowl Tare", "RG Bowl Tare", "Icy Go Bowl Tare", "Co-Chi Bowl Tare")
REUSABLE_DISCOUNT = "Reusable 10% Off"
DISCOUNT_CATEGORY = "POS Discounts"
_BOWLS_IN = ", ".join("'" + i.replace("'", "''") + "'" for i in REUSABLE_ITEMS)

SQL = {
    # Anchor: the most recent day where (nearly) all NSW venues have sales —
    # i.e. the latest COMPLETE trading day. Data lags ~1 day behind "today".
    # Scoped by our own NSW store list (no Venue_Master dependency).
    "anchor": f"""
        SELECT TOP 1 s.TxnDate anchor
        FROM PolygonRedcatNetSalesByStoreDailyView s
        WHERE s.StoreName IN ({_NSW_STORE_IN})
        GROUP BY s.TxnDate
        HAVING COUNT(DISTINCT s.StoreName) >= 18
        ORDER BY s.TxnDate DESC""",
    # Latest day that has ANY sales — including today's in-progress day. Powers the Live
    # tab's window (current calendar week through the freshest data), whereas the anchor
    # above deliberately lags to the last COMPLETE day for the main board. We read the
    # RAW sales report here (not the daily aggregate view, which trails it by ~a day),
    # bounded to the last few days so the MAX stays a fast, indexed scan.
    "live_date": """
        SELECT MAX(TxnDate) live_date
        FROM PolygonRedcatSalesReport
        WHERE TxnDate >= :recent""",
    # Reusable-discount compliance: one row per reusable-bowl sale in the window, with
    # the bowl used, whether the 10% reusable discount was applied, and whether ANY POS
    # discount was applied. We keep only lines that are either a reusable bowl or a POS
    # discount, group by sale, and keep sales that contain a bowl — so each sale is
    # classified as got-10% / other-discount / no-discount. Queried per venue (StoreName
    # is the only fast filter on this huge line-item view — a multi-store scan times
    # out). live_extract loops venues; each call stays well under 120s.
    "discount_detail": f"""
        SELECT SaleID,
          MIN(TxnDate) txn_date, MIN(TxnTime) txn_time,
          MAX(CASE WHEN PLUItem IN ({_BOWLS_IN}) THEN PLUItem END) bowl,
          MAX(CASE WHEN PLUItem = '{REUSABLE_DISCOUNT}' THEN 1 ELSE 0 END) got_10,
          MAX(CASE WHEN CategoryName = '{DISCOUNT_CATEGORY}' THEN 1 ELSE 0 END) any_disc,
          STRING_AGG(CASE WHEN CategoryName = '{DISCOUNT_CATEGORY}' THEN PLUItem END, ', ') disc_names
        FROM PolygonRedcatSalesReport
        WHERE StoreName = :store AND TxnDate >= :winStart AND TxnDate <= :dailyDate
          AND ( PLUItem IN ({_BOWLS_IN}) OR CategoryName = '{DISCOUNT_CATEGORY}' )
        GROUP BY SaleID
        HAVING MAX(CASE WHEN PLUItem IN ({_BOWLS_IN}) THEN 1 ELSE 0 END) = 1""",
    # Net sales per store, keyed by StoreName only. The VENUES table below is the
    # authoritative NSW allow-list (live_extract picks the stores it needs), so we don't
    # depend on Venue_Master.Reporting here — that flag isn't set for newly-onboarded
    # venues (Chippendale, Crows Nest, Fish Market, Green Hills), which would otherwise
    # be silently dropped. The query returns every store; live_extract keeps ours.
    "sales": """
        SELECT s.StoreName store,
          SUM(CASE WHEN s.TxnDate = :dailyDate THEN s.NetSales ELSE 0 END) d,
          SUM(CASE WHEN s.TxnDate >= :weekStart AND s.TxnDate <= :dailyDate THEN s.NetSales ELSE 0 END) w,
          SUM(CASE WHEN s.TxnDate >= :monthStart AND s.TxnDate <= :dailyDate THEN s.NetSales ELSE 0 END) m
        FROM PolygonRedcatNetSalesByStoreDailyView s
        GROUP BY s.StoreName""",
    # Reviews: count published from the Monday of the current calendar week through the
    # report day (calendar-week-to-date). Venues are KPI'd on Google Reviews per calendar
    # week (Mon–Sun), so this resets each Monday rather than being a rolling 7-day figure.
    "reviews": """
        SELECT LTRIM(RTRIM(location_name)) suburb,
          SUM(CASE WHEN CAST(published_on AS date) >= :weekStart
                    AND CAST(published_on AS date) <= :dailyDate THEN 1 ELSE 0 END) week_count
        FROM ReviewTrackersReviews
        WHERE location_state IN ('New South Wales','NSW')
        GROUP BY LTRIM(RTRIM(location_name))""",
    # Celsi is weekly-bucketed by Date. Anchor to the latest COMPLETE week bucket
    # (>=70% of the busiest recent week's checks) so the current in-progress week
    # doesn't undercount. daily = week/7; calibrations/correctiveA = that week.
    # Venue codes vary in length ("GEOR", "CN", "F.WOLL"), so extract everything
    # between '[' and '.NSW]' rather than a fixed 4 chars (a fixed slice mangled
    # codes like CN/F.WOLL/CRLQ and dropped those venues' food-safety data).
    "celsi": """
        SELECT SUBSTRING(Venue, CHARINDEX('[',Venue)+1, CHARINDEX('.NSW]',Venue)-CHARINDEX('[',Venue)-1) code,
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
        GROUP BY SUBSTRING(Venue, CHARINDEX('[',Venue)+1, CHARINDEX('.NSW]',Venue)-CHARINDEX('[',Venue)-1)""",
    # Labour: actual timesheet cost per venue, straight from Tanda (the payroll/
    # rostering system of record). A shift's department_id -> TandaTeams.team_id
    # gives the team's location_id -> TandaLocations.name (the venue). 'cost' is the
    # award-interpreted shift cost (award + allowances), so SUM(cost) is real spend.
    # NSW only (public_holiday_regions carries the state); the shared Support Office
    # ($0 shift cost, HQ) maps to no venue row and drops out. Restoke's dirty
    # attribution and the de-dup/HQ-dump gymnastics are gone — Tanda is clean per venue.
    "labour": """
        SELECT loc.name venue, SUM(ts.cost) labour_cost, COUNT(DISTINCT ts.user_id) emps
        FROM TandaTimesheetShifts ts
        JOIN TandaTeams tm ON tm.team_id = ts.department_id
        JOIN TandaLocations loc ON loc.location_id = tm.location_id
        WHERE CAST(ts.date AS date) >= :monthStart AND CAST(ts.date AS date) <= :dailyDate
          AND loc.public_holiday_regions LIKE '%au_nsw%'
        GROUP BY loc.name""",
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
#         reviews_week is calendar-week-to-date (Mon 6 – Tue 7 Jul for this snapshot).
FIXTURE = {
    "George St":      (19777, 35286, 132139, 3, 21, "complete", "none",  6, 16.0, 95.5, 81.1, 83.7),
    "Erina Fair":     (15213, 30367, 108145, 3, 20, "complete", "none",  0,  _N, 92.7, 73.1, 84.1),
    "Barangaroo":     (11015, 20588, 100751, 3, 21, "complete", "none",  0, 16.6, 95.2, 77.9, 77.5),
    "Wollongong":     (12965, 24679,  97415, 3, 20, "complete", "none",  1,  _N, 95.0, 75.6, 79.9),
    "Charlestown":    (13915, 27230,  96458, 3, 21, "complete", "none",  1,  _N, 93.3, 78.6, 88.6),
    "Rouse Hill":     (12293, 22304,  93015, 3, 20, "complete", "none",  1, 14.4, 97.3, 87.3, 92.0),
    "Circular Quay":  (11186, 20497,  86270, 3, 24, "complete", "none",  1, 15.0, 95.1, 75.4, 79.8),
    "Macquarie":      (12222, 23603,  82619, 3, 20, "complete", "none",  0, 13.0, 94.4, 77.3, 83.5),
    "Castle Towers":  (11343, 20641,  82478, 3, 19, "complete", "ok",    0, 14.4, 93.9, 77.3, 87.3),
    "Burwood":        ( 9642, 19396,  78495, 4, 26, "complete", "none",  0, 15.8, 98.1, 86.8, 87.2),
    "Penrith":        ( 9889, 18814,  74877, 3, 20, "complete", "none",  0, 14.4, 98.3, 82.9, 92.1),
    "Manly":          ( 8658, 16555,  73836, 3, 21, "complete", "none",  1, 16.6, 92.8, 68.3, 77.0),
    "Chatswood":      ( 8697, 15954,  69139, 3, 20, "missed",   "none",  1, 15.5, 91.1, 67.2, 78.4),
    "Cronulla":       ( 7374, 13486,  66725, 3, 21, "complete", "none",  0, 16.8, 97.2, 80.2, 85.2),
    "Newtown":        ( 7505, 14302,  63813, 4, 26, "complete", "none", 13, 19.3, 92.4, 71.3, 85.0),
    "Bondi":          ( 5646, 10541,  55241, 3, 20, "complete", "none",  0, 19.4, 87.1, 51.7, 65.3),
    "Coogee":         ( 5286, 10013,  52745, 3, 20, "complete", "none",  3, 19.4, 95.9, 80.1, 92.4),
    "Surry Hills":    ( 4955,  9242,  51564, 4, 26, "complete", "none",  2, 19.0, 87.7, 69.7, 80.7),
    "Top Ryde":       ( 5141,  8985,  40010, 3, 20, "complete", "none",  3, 19.3, 97.1, 82.3, 89.1),
    "Randwick":       ( 4472,  8223,  38275, 4, 26, "complete", "none",  0, 18.4, 87.5, 77.6, 67.9),
    "Bondi Junction": ( 4759,  8909,  36889, 3, 21, "complete", "none",  7, 18.2, 94.1, 77.0, 87.0),
    "Lane Cove":      ( 3527,  6349,  30458, 3, 20, "complete", "none",  2, 21.3, 91.3, 63.5, 76.2),
    "Double Bay":     ( 3404,  6494,  29482, 2, 17, "complete", "none",  2, 20.0, 86.2, 43.5, 71.4),
    "Chippendale":    ( 4844,  8892,  31227, 4, 25, "complete", "none",  0, 20.4, 95.5, 76.2, 72.2),
    "Crows Nest":     ( 4616,  8447,  42854, 3, 21, "missed",   "none",  1, 19.7, 93.1, 72.0, 77.4),
    "Fish Market":    ( 3844,  7193,  30308, 3, 24, "complete", "none",  0, 25.2, 84.1, 39.0, 61.2),
    "Green Hills":    (12764, 25154,  95969, 3, 18, "complete", "none",  1,  _N, 94.3, 64.1, 84.7),
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
REVIEW_ALIAS = {"George St": "George Street", "Rouse Hill": "Rouse Hill Town Centre",
                "Green Hills": "Greenhills"}


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
    ws = f"{week_start.day} {week_start:%b}" if week_start.month != d.month else f"{week_start.day}"
    windows = f"daily = {d.day} {d:%b} · WTD = {ws}–{d.day} {d:%b} · MTD = 1–{d.day} {d:%b}"
    return {
        "reportDate": anchor, "dailyDate": anchor,
        "weekStart": week_start.isoformat(), "monthStart": month_start.isoformat(),
        "windows": windows,
    }


# Map each source query to the dashboard "system" it feeds, so a source that goes
# dark can be flagged on the board's status strip instead of just silently blanking.
_QUERY_SYSTEM = {
    "reviews": "Review Tracker", "celsi": "Celsi", "labour": "Tanda",
    "policies": "Chi Central", "comms": "Chi Central", "training": "Chi Central",
}


def _safe_query(name, sql, params, down):
    """Run a non-essential source query. If that source is unavailable (a permission
    revocation, a disconnected connector, or a transient error), degrade to no data
    for its metrics rather than failing the whole refresh — and record the outage in
    `down`. Sales/anchor stay strict: there's no board without them."""
    try:
        return datasights_query(sql, params)
    except SystemExit as e:
        down.add(_QUERY_SYSTEM.get(name, name))
        print(f"WARN  source '{name}' unavailable — its metrics render '—' this run: {str(e)[:160]}",
              file=sys.stderr)
        return []


def live_extract(snap):
    """Query DataSights live and shape the results into the FIXTURE tuple form,
    applying the same normalisation the offline snapshot encodes. A source that is
    unavailable this run blanks only its own metrics; the rest still refresh."""
    p = {k: snap[k] for k in ("dailyDate", "weekStart", "monthStart")}
    down = set()   # dashboard "systems" whose source went dark this run
    # Sales is the backbone (it also defines the venue list) — let it fail loudly.
    sales_by_store = _index(datasights_query(SQL["sales"], p), "store")
    reviews_by_sub = _index(_safe_query("reviews", SQL["reviews"], p, down), "suburb")
    celsi_by_code  = _index(_safe_query("celsi", SQL["celsi"], p, down), "code")
    labour_by_venue = _index(_safe_query("labour", SQL["labour"], p, down), "venue")
    policy_by_wp   = _index(_safe_query("policies", SQL["policies"], p, down), "workplace_name")
    comms_by_wp    = _index(_safe_query("comms", SQL["comms"], p, down), "workplace_name")
    train_by_wp    = _index(_safe_query("training", SQL["training"], p, down), "workplace_name")

    fixture = {}
    for display, sales_store, code, opcentral_wp, labour_venue in VENUES:
        s = sales_by_store.get(sales_store)
        if not s:
            print(f"WARN  no sales row for {display} (store={sales_store})", file=sys.stderr)
            continue
        sd, sw, sm = round(_num(s["d"])), round(_num(s["w"])), round(_num(s["m"]))

        # Celsi (weekly-bucketed): count -> daily rate; status from calib/corrective.
        if "Celsi" in down:                    # source down -> blank ("—"), not a false "Missed"/0
            ht_daily = temp_week = calib = correctiveA = None
        else:
            c = celsi_by_code.get(code, {})
            temp_week = int(_num(c.get("temp_week")))
            ht_daily = round(temp_week / 7) if temp_week else 0
            calib = "complete" if _num(c.get("calib")) > 0 else "missed"
            ca_n, ca_fail = _num(c.get("ca")), _num(c.get("ca_fail"))
            correctiveA = "issue" if ca_fail > 0 else ("ok" if ca_n > 0 else "none")

        rv = reviews_by_sub.get(REVIEW_ALIAS.get(display, display))
        if "Review Tracker" in down:
            reviews_week = None                       # source down -> render "—", not a misleading 0
        else:
            reviews_week = int(_num(rv["week_count"])) if rv else 0

        # Labour %: Tanda timesheet cost / net sales (MTD), with a plausibility guard.
        # Tanda attributes per venue cleanly, so no HQ-dump de-dup is needed; the
        # 5-45% band only catches a divide-by-tiny-sales blip or a mapping slip.
        labour_pct = None
        if labour_venue:
            lr = labour_by_venue.get(labour_venue)
            if lr and sm > 0:
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
    return fixture, down


_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _dedupe_discounts(s):
    """Collapse a repeated STRING_AGG list ('LAM 10%, LAM 10%, Team Free') to unique
    names in first-seen order ('LAM 10%, Team Free')."""
    seen, out = set(), []
    for x in (s or "").split(", "):
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return ", ".join(out)


def compute_discounts(start, end, with_other=False):
    """Per-venue reusable-bowl discount compliance over the window start..end,
    mirroring Mitch's Polygon "on or after start of this week" filter. Each
    reusable-bowl sale is classified: got the 10% reusable discount (compliant), got
    another POS discount instead (excluded, as his report does), or carried no discount
    at all (a MISS). Compliance % is measured over eligible sales only (compliant +
    missed), so comped/free sales don't dilute it. Called twice: once for the stable
    week-to-last-complete-day view, once for the Live tab (current week through today).
    When with_other is set, each venue also gets an `otherList` of the sales discounted
    another way, with the discount name(s) applied — this powers the Discounts Applied
    screen. Queried one venue at a time (StoreName is the only fast filter on the big
    Polygon line-item view); each venue is wrapped so a slow or failed one is skipped
    rather than sinking the whole section. Returns None if nothing was retrievable."""
    out = {}
    for display, sales_store, *_ in VENUES:
        try:
            rows = datasights_query(SQL["discount_detail"],
                                    {"store": sales_store, "winStart": start, "dailyDate": end}) or []
        except (SystemExit, Exception) as e:
            # Optional enrichment: skip this venue on ANY failure (permission, MCP
            # error, or a network read-timeout) rather than sinking the whole refresh.
            print(f"WARN  discounts unavailable for {display}: {str(e)[:120]}", file=sys.stderr)
            continue
        discounted = sum(1 for r in rows if int(_num(r.get("got_10"))) == 1)
        other = sum(1 for r in rows
                    if int(_num(r.get("got_10"))) == 0 and int(_num(r.get("any_disc"))) == 1)
        missed = sorted(
            ({"saleId": str(r.get("SaleID")), "date": str(r.get("txn_date"))[:10],
              "time": str(r.get("txn_time"))[:8], "bowl": r.get("bowl")}
             for r in rows if int(_num(r.get("any_disc"))) == 0),
            key=lambda m: (m["date"], m["time"]))
        eligible = discounted + len(missed)
        entry = {"reusable": len(rows), "discounted": discounted, "otherDisc": other,
                 "missed": len(missed),
                 "pct": round(100.0 * discounted / eligible, 1) if eligible else None,
                 "missedList": missed}
        if with_other:
            entry["otherList"] = sorted(
                ({"saleId": str(r.get("SaleID")), "date": str(r.get("txn_date"))[:10],
                  "time": str(r.get("txn_time"))[:8], "bowl": r.get("bowl"),
                  "discounts": _dedupe_discounts(r.get("disc_names"))}
                 for r in rows
                 if int(_num(r.get("got_10"))) == 0 and int(_num(r.get("any_disc"))) == 1),
                key=lambda m: (m["date"], m["time"]))
        out[display] = entry
    if not out:
        return None
    tr = sum(v["reusable"] for v in out.values())
    td = sum(v["discounted"] for v in out.values())
    to = sum(v["otherDisc"] for v in out.values())
    tm = sum(v["missed"] for v in out.values())
    elig = td + tm
    d0, d1 = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
    window = (f"{d1.day} {_MONTHS[d1.month-1]}" if d0 == d1
              else f"{d0.day} {_MONTHS[d0.month-1]} – {d1.day} {_MONTHS[d1.month-1]}")
    return {"metric": "Reusable bowl 10% discount", "items": list(REUSABLE_ITEMS),
            "discountName": REUSABLE_DISCOUNT, "windowStart": start, "windowEnd": end, "window": window,
            "totals": {"reusable": tr, "discounted": td, "otherDisc": to, "missed": tm,
                       "pct": round(100.0 * td / elig, 1) if elig else None},
            "venues": out}


# Offline sample for the Reusable Discounts tab (real Yo-Chi Burwood figures, calendar
# week 13–19 Jul; matches Mitch's official Polygon report: 4 missed). Live mode replaces
# this with all venues via compute_discounts().
DISCOUNT_FIXTURE = {
    "metric": "Reusable bowl 10% discount", "items": list(REUSABLE_ITEMS),
    "discountName": REUSABLE_DISCOUNT, "windowStart": "2026-07-13", "windowEnd": "2026-07-19",
    "window": "13 Jul – 19 Jul",
    "totals": {"reusable": 76, "discounted": 26, "otherDisc": 46, "missed": 4, "pct": 86.7},
    "venues": {
        "Burwood": {"reusable": 76, "discounted": 26, "otherDisc": 46, "missed": 4, "pct": 86.7, "missedList": [
            {"saleId": "115220135", "date": "2026-07-13", "time": "13:59:37", "bowl": "Icy Go Bowl Tare"},
            {"saleId": "115220155", "date": "2026-07-13", "time": "14:17:26", "bowl": "Icy Go Bowl Tare"},
            {"saleId": "115221326", "date": "2026-07-14", "time": "19:31:05", "bowl": "Icy Go Bowl Tare"},
            {"saleId": "114221327", "date": "2026-07-14", "time": "19:31:06", "bowl": "Icy Go Bowl Tare"},
        ]},
    },
}

# Offline sample for the Live tab (current calendar week through today, in progress).
DISCOUNT_FIXTURE_LIVE = {
    "metric": "Reusable bowl 10% discount", "items": list(REUSABLE_ITEMS),
    "discountName": REUSABLE_DISCOUNT, "windowStart": "2026-07-20", "windowEnd": "2026-07-20",
    "window": "20 Jul", "live": True,
    "totals": {"reusable": 11, "discounted": 4, "otherDisc": 6, "missed": 1, "pct": 80.0},
    "venues": {
        "Burwood": {"reusable": 11, "discounted": 4, "otherDisc": 6, "missed": 1, "pct": 80.0,
            "missedList": [
                {"saleId": "115230011", "date": "2026-07-20", "time": "12:04:11", "bowl": "Go Bowl Tare"},
            ],
            "otherList": [
                {"saleId": "115225978", "date": "2026-07-20", "time": "12:33:21", "bowl": "Go Bowl Tare", "discounts": "Team Free Yo-Chi"},
                {"saleId": "114226041", "date": "2026-07-20", "time": "13:21:12", "bowl": "Go Bowl Tare", "discounts": "LAM 10%"},
                {"saleId": "114226105", "date": "2026-07-20", "time": "14:07:06", "bowl": "Icy Go Bowl Tare", "discounts": "$10 OFF BIRTHDAY VOUCHER"},
                {"saleId": "115226263", "date": "2026-07-20", "time": "15:51:52", "bowl": "Go Bowl Tare", "discounts": "Ops Only 100%"},
                {"saleId": "114226351", "date": "2026-07-20", "time": "17:07:31", "bowl": "Go Bowl Tare", "discounts": "Loyalty Redemptions"},
                {"saleId": "114226628", "date": "2026-07-20", "time": "22:07:15", "bowl": "Go Bowl Tare", "discounts": "Team Free Yo-Chi"},
            ]},
    },
}


def main():
    ap = argparse.ArgumentParser(description="Rebuild data.json for the NSW Operations Dashboard")
    ap.add_argument("--offline", action="store_true", help="rebuild from the bundled snapshot (no DB)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data.json"))
    args = ap.parse_args()

    if args.offline:
        snap, fixture, down = SNAPSHOT, FIXTURE, set()
        discounts = DISCOUNT_FIXTURE
        discounts_live = DISCOUNT_FIXTURE_LIVE
    else:
        snap = resolve_snapshot()
        print(f"Resolved window: {snap['reportDate']} ({snap['windows']})", file=sys.stderr)
        fixture, down = live_extract(snap)
        # Reusable-discount compliance is a heavy Polygon crunch; never let it sink the
        # board — on any failure the tab just keeps its last data.
        # Stable view: this week through the last COMPLETE day (matches the closed-week report).
        try:
            discounts = compute_discounts(snap["weekStart"], snap["dailyDate"])
        except (SystemExit, Exception) as e:
            print(f"WARN  discount compliance skipped: {str(e)[:160]}", file=sys.stderr)
            discounts = None
        # Live view: the CURRENT calendar week through the freshest data (includes today).
        try:
            recent = (_dt.date.fromisoformat(snap["dailyDate"]) - _dt.timedelta(days=4)).isoformat()
            lrows = datasights_query(SQL["live_date"], {"recent": recent}) or []
            live_end = str(lrows[0]["live_date"])[:10] if lrows and lrows[0].get("live_date") else snap["dailyDate"]
            le = _dt.date.fromisoformat(live_end)
            live_start = (le - _dt.timedelta(days=le.weekday())).isoformat()
            discounts_live = compute_discounts(live_start, live_end, with_other=True)
            if discounts_live:
                discounts_live["live"] = True
        except (SystemExit, Exception) as e:
            print(f"WARN  live discount view skipped: {str(e)[:160]}", file=sys.stderr)
            discounts_live = None
    periods = build_periods(fixture)
    errors, warnings, coverage = validate(periods)

    for w in warnings:
        print(f"WARN  {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR {e}", file=sys.stderr)
        print("Validation failed — data.json NOT written (dashboard keeps last good copy).", file=sys.stderr)
        sys.exit(1)

    # Sources that went dark this run render as "awaiting source" (grey) on the
    # board rather than green/live, so the blanked metrics read as a known outage.
    sources = dict(SOURCE_STATUS)
    for sysname in down:
        sources[sysname] = "nosource"
    if down:
        print(f"WARN  degraded sources this run: {', '.join(sorted(down))} — refreshed everything else",
              file=sys.stderr)

    generated = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "meta": {
            "reportDate": snap["reportDate"],
            "generatedAt": generated,
            "windows": snap["windows"],
            "venues": len(periods["daily"]),
            "sources": sources,
            "coverage": coverage,
        },
        "periods": periods,
    }
    if discounts:
        payload["discounts"] = discounts
    if discounts_live:
        payload["discountsLive"] = discounts_live

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
