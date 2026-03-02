import os
import requests
import base64
import urllib3
from flask import Flask, jsonify, render_template
from datetime import datetime, timedelta, timezone
from collections import defaultdict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

CW_SITE        = os.environ.get("CW_SITE", "api-eu.myconnectwise.net")
CW_COMPANY     = os.environ.get("CW_COMPANY", "")
CW_PUBLIC_KEY  = os.environ.get("CW_PUBLIC_KEY", "")
CW_PRIVATE_KEY = os.environ.get("CW_PRIVATE_KEY", "")
CW_CLIENT_ID   = os.environ.get("CW_CLIENT_ID", "")
HTTPS_PROXY    = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
REFRESH_INTERVAL = int(os.environ.get("CW_REFRESH_INTERVAL", "300"))

# Priorities to exclude from stale tickets view
_raw_excl_pri = os.environ.get("CW_EXCLUDE_PRIORITIES", "")
EXCLUDE_PRIORITIES = {p.strip().lower() for p in _raw_excl_pri.split(",") if p.strip()}

# Ticket count thresholds for owner card colour
THRESH_RED   = int(os.environ.get("CW_THRESH_RED",   "20"))
THRESH_AMBER = int(os.environ.get("CW_THRESH_AMBER", "15"))
VERIFY_SSL     = os.environ.get("CW_VERIFY_SSL", "true").lower() != "false"

# Statuses to exclude from stale tickets view — driven by CW_EXCLUDE_STATUSES env var
# Defaults include common closed statuses; extend via docker-compose environment
_raw_exclude = os.environ.get("CW_EXCLUDE_STATUSES", "Closed,Resolved,Cancelled,Completed,Complete,Closed - Resolved,Closed - No Resolution")
CLOSED_STATUSES = {s.strip().lower() for s in _raw_exclude.split(",") if s.strip()}

def get_session():
    s = requests.Session()
    if HTTPS_PROXY:
        s.proxies = {"https": HTTPS_PROXY, "http": HTTPS_PROXY}
    s.verify = VERIFY_SSL
    return s

def get_auth_header():
    creds = f"{CW_COMPANY}+{CW_PUBLIC_KEY}:{CW_PRIVATE_KEY}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "clientId": CW_CLIENT_ID,
        "Content-Type": "application/json"
    }

def cw_get(endpoint, params=None):
    url = f"https://{CW_SITE}/v4_6_release/apis/3.0{endpoint}"
    headers = get_auth_header()
    all_results = []
    page = 1
    page_size = 100  # smaller pages = faster, less timeout risk

    if params is None:
        params = {}

    session = get_session()

    while True:
        paged_params = {**params, "page": page, "pageSize": page_size}
        response = session.get(url, headers=headers, params=paged_params, timeout=90)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        all_results.extend(data)
        if len(data) < page_size:
            break
        page += 1

    return all_results

def is_closed(ticket):
    status = ""
    s = ticket.get("status")
    if isinstance(s, dict):
        status = s.get("name", "").lower().strip()
    elif isinstance(s, str):
        status = s.lower().strip()
    return status in CLOSED_STATUSES

@app.route("/")
def index():
    return render_template("dashboard.html", refresh_interval=REFRESH_INTERVAL, thresh_red=THRESH_RED, thresh_amber=THRESH_AMBER)

@app.route("/api/stale-tickets")
def stale_tickets():
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "conditions": f"closedFlag = false and parentTicketId = null and lastUpdated < [{cutoff_str}]",
            "fields": "id,summary,status,owner,board,priority,lastUpdated,dateEntered,company",
            "orderBy": "lastUpdated asc"
        }

        tickets = cw_get("/service/tickets", params)

        # Filter out any closed/completed statuses in Python as a safety net
        tickets = [t for t in tickets if not is_closed(t)]

        # Filter out excluded priorities
        if EXCLUDE_PRIORITIES:
            tickets = [t for t in tickets if
                (t.get("priority", {}).get("name", "") if isinstance(t.get("priority"), dict) else "").lower().strip()
                not in EXCLUDE_PRIORITIES]

        result = []
        for t in tickets:
            last_updated = t.get("lastUpdated", "")
            hours_stale = None
            if last_updated:
                try:
                    lu = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                    hours_stale = round((datetime.now(timezone.utc) - lu).total_seconds() / 3600, 1)
                except:
                    pass

            result.append({
                "id": t.get("id"),
                "summary": t.get("summary", ""),
                "status": t.get("status", {}).get("name", "") if isinstance(t.get("status"), dict) else "",
                "owner": t.get("owner", {}).get("name", "Unassigned") if isinstance(t.get("owner"), dict) else "Unassigned",
                "board": t.get("board", {}).get("name", "") if isinstance(t.get("board"), dict) else "",
                "priority": t.get("priority", {}).get("name", "") if isinstance(t.get("priority"), dict) else "",
                "lastUpdated": last_updated,
                "hoursStale": hours_stale,
                "company": t.get("company", {}).get("name", "") if isinstance(t.get("company"), dict) else "",
            })

        return jsonify({"tickets": result, "count": len(result), "asOf": datetime.now(timezone.utc).isoformat()})
    except Exception as e:
        return jsonify({"error": str(e), "tickets": [], "count": 0}), 500

@app.route("/api/config-check")
def config_check():
    configured = all([CW_COMPANY, CW_PUBLIC_KEY, CW_PRIVATE_KEY, CW_CLIENT_ID])
    return jsonify({
        "configured": configured,
        "site": CW_SITE,
        "company": CW_COMPANY if CW_COMPANY else "(not set)",
        "hasPublicKey": bool(CW_PUBLIC_KEY),
        "hasPrivateKey": bool(CW_PRIVATE_KEY),
        "hasClientId": bool(CW_CLIENT_ID),
        "proxy": HTTPS_PROXY if HTTPS_PROXY else "none",
        "sslVerify": VERIFY_SSL
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
