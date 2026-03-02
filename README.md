# ConnectWise Dashboard

A self-hosted web dashboard that shows:
- **Stale Tickets** — open tickets not updated in 24+ hours, grouped by owner with expandable ticket lists
- **Top 5 Oldest** — the five longest-untouched tickets displayed prominently
- **Auto-refreshes** on a configurable interval (default: every 5 minutes)

---

## Quick Start

### Option A: Docker Compose (recommended)

1. Edit `docker-compose.yml` and fill in your ConnectWise credentials
2. Run:
```bash
docker compose up -d
```
3. Open http://localhost:5000

### Option B: docker run
```bash
docker run -d \
  -p 5000:5000 \
  -e CW_SITE=api-eu.myconnectwise.net \
  -e CW_COMPANY=yourcompanyid \
  -e CW_PUBLIC_KEY=your_public_key \
  -e CW_PRIVATE_KEY=your_private_key \
  -e CW_CLIENT_ID=your_client_id \
  --name cw-dashboard \
  --restart unless-stopped \
  samuelstreets/connectwise-ticket-dashboard:latest
```

---

## Getting Your API Keys

### 1. Create API Keys in ConnectWise
- Go to **System → Members → (select a member) → API Keys**
- Click **New Item** and save the public/private key pair

### 2. Get a Client ID
- Register at **https://developer.connectwise.com/ClientID**
- Create a new application entry and copy the Client ID

### 3. Find Your Site & Company ID
- **Site**: your ConnectWise API hostname (e.g. `api-eu.myconnectwise.net`, `api-na.myconnectwise.net`)
- **Company ID**: the short company identifier you use to log in

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `CW_SITE` | ConnectWise API hostname | `api-eu.myconnectwise.net` |
| `CW_COMPANY` | Company login ID | *(required)* |
| `CW_PUBLIC_KEY` | API public key | *(required)* |
| `CW_PRIVATE_KEY` | API private key | *(required)* |
| `CW_CLIENT_ID` | Developer client ID | *(required)* |
| `CW_VERIFY_SSL` | Verify SSL certificates (`true`/`false`) | `true` |
| `HTTPS_PROXY` | Proxy URL if required by your network | *(none)* |
| `CW_REFRESH_INTERVAL` | Dashboard auto-refresh in seconds | `300` |
| `CW_EXCLUDE_STATUSES` | Comma-separated statuses to hide from stale view | `Closed,Resolved,Cancelled,Completed,Complete,Closed - Resolved,Closed - No Resolution` |
| `CW_EXCLUDE_PRIORITIES` | Comma-separated priorities to hide (e.g. `Low,Planning`) | *(none)* |
| `CW_THRESH_RED` | Stale ticket count threshold for red owner card | `20` |
| `CW_THRESH_AMBER` | Stale ticket count threshold for amber owner card | `15` |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Main dashboard UI |
| `GET /api/stale-tickets` | Tickets not updated in 24+ hours (JSON) |
| `GET /api/config-check` | Verify environment configuration (JSON) |

---

## Stopping / Removing
```bash
docker compose down        # stop
docker compose down -v     # stop and remove volumes
```
