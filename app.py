import os
import requests
import base64
from flask import Flask, jsonify, render_template
from datetime import datetime, timedelta, timezone
from collections import defaultdict

app = Flask(__name__)

# ConnectWise API Configuration (from environment variables)
CW_SITE       = os.environ.get("CW_SITE", "na.myconnectwise.net")
CW_COMPANY    = os.environ.get("CW_COMPANY", "")
CW_PUBLIC_KEY = os.environ.get("CW_PUBLIC_KEY", "")
CW_PRIVATE_KEY= os.environ.get("CW_PRIVATE_KEY", "")
CW_CLIENT_ID  = os.environ.get("CW_CLIENT_ID", "")

# Optional proxy + SSL settings
HTTPS_PROXY   = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
VERIFY_SSL    = os.environ.get("CW_VERIFY_SSL", "true").lower() != "false"

def get_session():
    session = requests.Session()
    if HTTPS_PROXY:
        session.proxies = {"https": HTTPS_PROXY, "http": HTTPS_PROXY}
    session.verify = VERIFY_SSL
    return session

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
    page_size = 1000

    if params is None:
        params = {}

    session = get_session()

    while True:
        paged_params = {**params, "page": page, "pageSize": page_size}
        response = session.get(url, headers=headers, params=paged_params, timeout=60)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        all_results.extend(data)
        if len(data) < page_size:
            break
        page += 1

    return all_results

@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/stale-tickets")
def stale_tickets():
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=8)
        cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "conditions": f"status/name not in (\"Closed\",\"Resolved\",\"Cancelled\") and lastUpdated < [{cutoff_str}]",
            "fields": "id,summary,status,owner,board,priority,lastUpdated,dateEntered,company",
            "orderBy": "lastUpdated asc"
        }

        tickets = cw_get("/service/tickets", params)

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

@app.route("/api/closed-by-user")
def closed_by_user():
    try:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        days_back = 7
        start_date = today - timedelta(days=days_back - 1)
        start_str = start_date.strftime("%Y-%m-%dT00:00:00Z")
        end_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "conditions": f"status/name in (\"Closed\",\"Resolved\") and lastUpdated >= [{start_str}] and lastUpdated <= [{end_str}]",
            "fields": "id,owner,lastUpdated,closedBy",
            "orderBy": "lastUpdated desc"
        }

        tickets = cw_get("/service/tickets", params)

        data = defaultdict(lambda: defaultdict(int))

        for t in tickets:
            lu = t.get("lastUpdated", "")
            owner_info = t.get("owner")
            owner = owner_info.get("name", "Unassigned") if isinstance(owner_info, dict) else "Unassigned"
            if lu:
                try:
                    dt = datetime.fromisoformat(lu.replace("Z", "+00:00"))
                    day_str = dt.strftime("%Y-%m-%d")
                    data[owner][day_str] += 1
                except:
                    pass

        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back - 1, -1, -1)]
        users = sorted(data.keys())
        result = {"dates": dates, "users": []}

        for user in users:
            daily = [data[user].get(d, 0) for d in dates]
            total = sum(daily)
            result["users"].append({"name": user, "daily": daily, "total": total})

        result["users"].sort(key=lambda x: x["total"], reverse=True)
        result["asOf"] = datetime.now(timezone.utc).isoformat()

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "dates": [], "users": []}), 500

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
