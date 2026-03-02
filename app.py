import os
import requests
import base64
import urllib3
from flask import Flask, jsonify, render_template_string
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

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ConnectWise Dashboard</title>
<style>
  :root {
    --crit: #ff3b30;
    --warn: #ffcc00;
    --good: #4cd964;
    --stale: #444444;
    --bg: #0a0a0a;
    --card-bg: #161616;
    --header-bg: #111111;
    --border: #222222;
    --text: #ffffff;
    --text-dim: #888888;
    --text-muted: #555555;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; min-height: 100vh; }
  header { background: var(--header-bg); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }
  .logo { font-size: 1rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; color: white; }
  .logo span { color: var(--good); }
  .header-right { display: flex; align-items: center; gap: 16px; }
  .refresh-status { display: flex; align-items: center; gap: 8px; font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
  .pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--good); animation: pulse 2s infinite; flex-shrink: 0; }
  @keyframes pulse { 0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(76,217,100,0.5)}50%{opacity:.7;box-shadow:0 0 0 5px rgba(76,217,100,0)} }
  .countdown-ring { position: relative; width: 26px; height: 26px; flex-shrink: 0; }
  .countdown-ring svg { transform: rotate(-90deg); }
  .countdown-ring .bg { fill: none; stroke: #333; stroke-width: 2.5; }
  .countdown-ring .progress { fill: none; stroke: var(--good); stroke-width: 2.5; stroke-linecap: round; transition: stroke-dashoffset 1s linear; }
  .countdown-label { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); font-size: 8px; color: var(--good); font-weight: 700; }
  .refresh-picker { display: flex; gap: 4px; align-items: center; }
  .refresh-opt { background: #1a1a1a; border: 1px solid #333; color: var(--text-dim); font-size: .7rem; font-weight: 600; padding: 4px 9px; border-radius: 4px; cursor: pointer; transition: all .2s; font-family: inherit; letter-spacing: .5px; }
  .refresh-opt:hover { border-color: var(--good); color: var(--good); }
  .refresh-opt.active { background: rgba(76,217,100,.15); border-color: var(--good); color: var(--good); }
  .config-warning { background: rgba(255,59,48,0.08); border-left: 4px solid var(--crit); padding: 16px 24px; margin: 20px 24px; border-radius: 0 8px 8px 0; display: none; }
  .config-warning.visible { display: block; }
  .config-warning h3 { color: var(--crit); font-size: .9rem; margin-bottom: 8px; }
  .config-warning p { font-size: .8rem; color: var(--text-dim); line-height: 1.8; }
  .config-warning code { background: rgba(255,255,255,.07); padding: 1px 6px; border-radius: 3px; color: var(--warn); }
  main { padding: 24px; }
  .section-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
  .section-title { font-size: .8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; color: var(--text-dim); }
  .count-pill { font-size: .7rem; font-weight: 700; padding: 2px 9px; border-radius: 20px; background: var(--crit); color: white; }
  .count-pill.green { background: var(--good); color: #000; }
  .section-gap { margin-bottom: 40px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 20px; }
  .card { padding: 20px; border-radius: 12px; background: var(--card-bg); border-left: 10px solid; transition: 0.3s ease-in-out; }
  .card.Red   { border-color: var(--crit); }
  .card.Amber { border-color: var(--warn); }
  .card.Green { border-color: var(--good); opacity: 0.6; }
  .card:hover { opacity: 1 !important; }
  .cust-name { font-size: 1.1rem; font-weight: 700; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .status-meta { font-size: .75rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 14px; }
  .issue-item { margin-bottom: 8px; padding: 10px 12px; border-radius: 4px; border-left: 4px solid; }
  .sev-critical { border-left-color: var(--crit); background: rgba(255,59,48,0.08); }
  .sev-warning  { border-left-color: var(--warn); background: rgba(255,204,0,0.05); }
  .sev-stale    { border-left-color: var(--stale); background: rgba(255,255,255,0.02); color: #666; }
  .issue-summary { font-size: .85rem; font-weight: 600; display: block; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sev-stale .issue-summary { font-style: italic; color: #555; }
  .instruction { display: block; font-size: .75rem; color: var(--text-dim); }
  .instruction a { color: inherit; text-decoration: none; }
  .instruction a:hover { text-decoration: underline; }
  .stale-hours { display: inline-block; font-size: .7rem; font-weight: 700; padding: 1px 7px; border-radius: 20px; margin-left: 6px; vertical-align: middle; }
  .sev-critical .stale-hours { background: rgba(255,59,48,.2); color: var(--crit); }
  .sev-warning  .stale-hours { background: rgba(255,204,0,.15); color: var(--warn); }
  .sev-stale    .stale-hours { background: rgba(68,68,68,.3); color: #666; }
  .tech-card { padding: 20px; border-radius: 12px; background: var(--card-bg); border-left: 10px solid var(--good); }
  .tech-total { font-size: 2rem; font-weight: 700; color: var(--good); line-height: 1; margin-bottom: 2px; }
  .tech-label { font-size: .7rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 14px; }
  .bar-chart { display: flex; align-items: flex-end; gap: 5px; height: 48px; }
  .bar-wrap { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; gap: 4px; }
  .bar-inner { flex: 1; width: 100%; display: flex; align-items: flex-end; }
  .bar { width: 100%; background: var(--good); border-radius: 2px 2px 0 0; min-height: 2px; opacity: .7; transition: opacity .2s; cursor: default; }
  .bar:hover { opacity: 1; }
  .bar-label { font-size: 9px; color: var(--text-muted); text-align: center; white-space: nowrap; }
  .loading { display: flex; align-items: center; justify-content: center; padding: 60px; color: var(--text-dim); gap: 12px; font-size: .8rem; }
  .spinner { width: 18px; height: 18px; border: 2px solid #333; border-top-color: var(--good); border-radius: 50%; animation: spin .8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .error-msg { padding: 30px; color: var(--crit); font-size: .8rem; }
  .empty-state { text-align: center; padding: 48px 24px; }
  .empty-state .big-check { font-size: 2.5rem; margin-bottom: 8px; }
  .top-row { display: flex; gap: 20px; padding: 20px 20px 0 20px; align-items: stretch; }
  .oldest-section { flex: 1; min-width: 0; }
  .top-owner-col { width: 220px; flex-shrink: 0; }
  .oldest-label { font-size: .7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 2px; color: var(--crit); margin-bottom: 12px; }
  .section-divider { border-top: 1px solid var(--border); margin: 20px 0 0 0; }
  .sev-badges { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .sev-badge { font-size: .7rem; font-weight: 700; padding: 3px 10px; border-radius: 20px; }
  .sev-badge.crit { background: rgba(255,59,48,.2); color: var(--crit); border: 1px solid rgba(255,59,48,.3); }
  .sev-badge.warn { background: rgba(255,204,0,.15); color: var(--warn); border: 1px solid rgba(255,204,0,.25); }
  .owner-ticket-row { display: flex; align-items: center; justify-content: space-between; }
  .owner-total { font-size: 2.2rem; font-weight: 800; line-height: 1; }
  .owner-total.red { color: var(--crit); }
  .owner-total.amber { color: var(--warn); }
  .owner-total.green { color: var(--good); }
  .empty-state p { color: var(--text-dim); font-size: .8rem; text-transform: uppercase; letter-spacing: 1px; }
</style>
</head>
<body>
<header>
  <div class="logo">ConnectWise Ticket Dashboard</div>
  <div class="header-right">
    <div class="refresh-status">
      <div class="pulse-dot"></div>
      <span id="last-updated-label">Loading…</span>
      <div class="countdown-ring">
        <svg width="26" height="26" viewBox="0 0 26 26">
          <circle class="bg" cx="13" cy="13" r="10"/>
          <circle class="progress" id="countdown-circle" cx="13" cy="13" r="10" stroke-dasharray="62.8" stroke-dashoffset="0"/>
        </svg>
        <span class="countdown-label" id="countdown-text">5m</span>
      </div>
    </div>
  </div>
</header>

<div class="config-warning" id="config-warning">
  <h3>⚠ ConnectWise API Not Configured</h3>
  <p>Set <code>CW_SITE</code>, <code>CW_COMPANY</code>, <code>CW_PUBLIC_KEY</code>, <code>CW_PRIVATE_KEY</code>, <code>CW_CLIENT_ID</code> in your docker-compose.yml environment section.</p>
</div>

<main>
  <div class="section-gap">
    <div class="section-header">
      <span class="section-title">Stale Tickets</span>
      <span class="count-pill" id="stale-count-pill">—</span>
      <span style="font-size:.72rem;color:var(--text-muted)">open · not updated in 24+ hours · grouped by owner</span>
    </div>
    <div id="stale-container"><div class="loading"><div class="spinner"></div>Loading…</div></div>
  </div>


</main>

<script>
const REFRESH_OPTIONS = [60, 120, 300, 600, 900];
let REFRESH_INTERVAL = parseInt(localStorage.getItem('cw_refresh') || '{{ refresh_interval }}');
const THRESH_RED   = {{ thresh_red }};
const THRESH_AMBER = {{ thresh_amber }};
let countdown = REFRESH_INTERVAL;
const circle = document.getElementById('countdown-circle');
const circumference = 62.8;

function setRefreshInterval(seconds) {
  REFRESH_INTERVAL = seconds;
  countdown = seconds;
  localStorage.setItem('cw_refresh', seconds);
  document.querySelectorAll('.refresh-opt').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.val) === seconds);
  });
}

setInterval(() => {
  countdown--;
  if (countdown <= 0) { countdown = REFRESH_INTERVAL; refreshAll(); }
  circle.style.strokeDashoffset = circumference * (1 - countdown / REFRESH_INTERVAL);
  const mins = Math.floor(countdown / 60);
  const secs = countdown % 60;
  document.getElementById('countdown-text').textContent = mins > 0 ? mins + 'm' : secs + 's';
}, 1000);

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-GB', {day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
}

function sevClass(hours) {
  if (hours >= 48) return 'sev-critical';
  if (hours >= 24) return 'sev-warning';
  return 'sev-stale';
}

function cardClass(tickets) {
  if (tickets.some(t => (t.hoursStale||0) >= 48)) return 'Red';
  if (tickets.some(t => (t.hoursStale||0) >= 24)) return 'Amber';
  return 'Green';
}

function ownerCardClass(count) {
  if (count >= THRESH_RED)   return 'Red';
  if (count >= THRESH_AMBER) return 'Amber';
  return 'Green';
}

async function loadStaleTickets() {
  const el = document.getElementById('stale-container');
  const pill = document.getElementById('stale-count-pill');
  try {
    const res = await fetch('/api/stale-tickets');
    const data = await res.json();
    if (data.error) { el.innerHTML = `<div class="error-msg">⚠ ${data.error}</div>`; pill.textContent='ERR'; return; }
    pill.textContent = data.count;
    if (!data.tickets.length) {
      el.innerHTML = `<div class="empty-state"><div class="big-check">✅</div><p>All tickets up to date</p></div>`;
      return;
    }

    // Sort all tickets by hoursStale descending
    const allSorted = [...data.tickets].sort((a,b) => (b.hoursStale||0) - (a.hoursStale||0));

    // Top 5 oldest tickets
    const top5 = allSorted.slice(0, 5);
    const top5HTML = top5.map(t => {
      const sc = sevClass(t.hoursStale||0);
      const h = t.hoursStale !== null ? t.hoursStale : '?';
      const url = `https://${window._cwSite||'eu.myconnectwise.net'}/v4_6_release/services/system_io/Service/fv_sr100_request.rails?service_recid=${t.id}`;
      return `<div class="issue-item ${sc}" style="margin-bottom:10px">
        <span class="issue-summary">#${t.id} — ${t.summary||'(no summary)'}<span class="stale-hours">${h}h</span></span>
        <span class="instruction"><a href="${url}" target="_blank">${t.owner||'Unassigned'} · ${t.company||''} · ${t.board||''} · ${t.status||''} · ${fmtDate(t.lastUpdated)}</a></span>
      </div>`;
    }).join('');

    // Group remaining by owner, show count only
    const byOwner = {};
    for (const t of data.tickets) {
      const owner = t.owner || 'Unassigned';
      if (!byOwner[owner]) byOwner[owner] = [];
      byOwner[owner].push(t);
    }
    const ownersSorted = Object.entries(byOwner).sort(([,a],[,b]) => b.length - a.length);
    const ownerCards = ownersSorted.map(([owner, tickets]) => {
      const worst = Math.max(...tickets.map(t => t.hoursStale||0));
      const cls = ownerCardClass(tickets.length);
      const critCount = tickets.filter(t => (t.hoursStale||0) >= 48).length;
      const warnCount = tickets.filter(t => (t.hoursStale||0) >= 24 && (t.hoursStale||0) < 48).length;
      const staleCount = tickets.filter(t => (t.hoursStale||0) < 24).length;
      const badges = [
        critCount > 0 ? `<span class="sev-badge crit">${critCount} 48h+</span>` : '',
        warnCount > 0 ? `<span class="sev-badge warn">${warnCount} 24h+</span>` : ''
      ].filter(Boolean).join('');
      return `<div class="card ${cls}">
        <div class="owner-ticket-row">
          <div class="cust-name">${owner}</div>
          <div class="owner-total ${cls.toLowerCase()}">${tickets.length}</div>
        </div>
        <div class="sev-badges">${badges}</div>
      </div>`;
    }).join('');

    // Find owner with most tickets for the sidebar
    const topOwner = ownersSorted[0];
    const topOwnerHTML = topOwner ? (() => {
      const [owner, tickets] = topOwner;
      const cls = ownerCardClass(tickets.length);
      const critCount = tickets.filter(t => (t.hoursStale||0) >= 48).length;
      const warnCount = tickets.filter(t => (t.hoursStale||0) >= 24 && (t.hoursStale||0) < 48).length;
      const badges = [
        critCount > 0 ? `<span class="sev-badge crit">${critCount} 48h+</span>` : '',
        warnCount > 0 ? `<span class="sev-badge warn">${warnCount} 24h+</span>` : ''
      ].filter(Boolean).join('');
      return `<div class="card ${cls}" style="height:100%;display:flex;flex-direction:column;justify-content:space-between;">
        <div>
          <div class="oldest-label" style="margin-bottom:8px">🏆 MOST TICKETS</div>
          <div class="cust-name" style="font-size:1.3rem">${owner}</div>
        </div>
        <div class="owner-total ${cls.toLowerCase()}" style="font-size:4rem;text-align:center;padding:10px 0">${tickets.length}</div>
        <div class="sev-badges">${badges}</div>
      </div>`;
    })() : '';

    // Unassigned card
    const unassignedTickets = data.tickets.filter(t => !t.owner || t.owner === 'Unassigned');
    const unassignedHTML = (() => {
      const count = unassignedTickets.length;
      if (count === 0) return '';
      const cls = ownerCardClass(count);
      const critCount = unassignedTickets.filter(t => (t.hoursStale||0) >= 48).length;
      const warnCount = unassignedTickets.filter(t => (t.hoursStale||0) >= 24 && (t.hoursStale||0) < 48).length;
      const badges = [
        critCount > 0 ? `<span class="sev-badge crit">${critCount} 48h+</span>` : '',
        warnCount > 0 ? `<span class="sev-badge warn">${warnCount} 24h+</span>` : ''
      ].filter(Boolean).join('');
      return `<div class="card ${cls}" style="height:100%;display:flex;flex-direction:column;justify-content:space-between;">
        <div>
          <div class="oldest-label" style="margin-bottom:8px;color:var(--text-dim)">⚠ UNASSIGNED</div>
          <div class="cust-name" style="font-size:1.3rem">Unassigned</div>
        </div>
        <div class="owner-total ${cls.toLowerCase()}" style="font-size:4rem;text-align:center;padding:10px 0">${count}</div>
        <div class="sev-badges">${badges}</div>
      </div>`;
    })();

    el.innerHTML = `
      <div class="top-row">
        <div class="oldest-section">
          <div class="oldest-label">🔥 TOP 5 OLDEST</div>
          ${top5HTML}
        </div>
        <div style="display:flex;flex-direction:column;gap:12px;width:220px;flex-shrink:0">
          ${unassignedHTML}
          ${topOwnerHTML}
        </div>
      </div>
      <div class="section-divider"></div>
      <div class="grid" style="padding:20px">${ownerCards}</div>`;
  } catch(e) {
    el.innerHTML = `<div class="error-msg">⚠ ${e.message}</div>`;
  }
}

async function checkConfig() {
  try {
    const data = await fetch('/api/config-check').then(r=>r.json());
    window._cwSite = data.site;
    if (!data.configured) document.getElementById('config-warning').classList.add('visible');
  } catch(e) {}
}

function refreshAll() {
  const now = new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  document.getElementById('last-updated-label').textContent = `Updated ${now}`;
  loadStaleTickets();
}

checkConfig();
refreshAll();
// Init button state from saved preference
setRefreshInterval(REFRESH_INTERVAL);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML, refresh_interval=REFRESH_INTERVAL, thresh_red=THRESH_RED, thresh_amber=THRESH_AMBER)

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
