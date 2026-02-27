# ConnectWise Dashboard

A self-hosted web dashboard that shows:
- **Stale Tickets** — open tickets not updated in 8+ hours (color-coded by severity)
- **Closed Tickets by User** — how many tickets each tech closed per day for the last 7 days
- **Auto-refreshes** every 60 seconds

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
docker build -t cw-dashboard .

docker run -d \
  -p 5000:5000 \
  -e CW_SITE=na.myconnectwise.net \
  -e CW_COMPANY=yourcompanyid \
  -e CW_PUBLIC_KEY=your_public_key \
  -e CW_PRIVATE_KEY=your_private_key \
  -e CW_CLIENT_ID=your_client_id \
  --name cw-dashboard \
  --restart unless-stopped \
  cw-dashboard
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
- **Site**: your ConnectWise URL (e.g. `na.myconnectwise.net`, `eu.myconnectwise.net`)
- **Company ID**: the short company identifier you use to log in

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `CW_SITE` | ConnectWise instance hostname | `na.myconnectwise.net` |
| `CW_COMPANY` | Company login ID | *(required)* |
| `CW_PUBLIC_KEY` | API public key | *(required)* |
| `CW_PRIVATE_KEY` | API private key | *(required)* |
| `CW_CLIENT_ID` | Developer client ID | *(required)* |

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Main dashboard UI |
| `GET /api/stale-tickets` | Tickets not updated in 8+ hours (JSON) |
| `GET /api/closed-by-user` | Closed tickets per user per day, last 7 days (JSON) |
| `GET /api/config-check` | Verify environment configuration (JSON) |

---

## Stopping / Removing

```bash
docker compose down        # stop
docker compose down -v     # stop and remove volumes
```
