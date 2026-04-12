# ERP-IOT — Multi-Marina Pedestal Management Platform

Central ERP layer that connects multiple marina installations (each running Pedestal SW) to a single management dashboard.

## Architecture

```
Browser/Dashboard
       │
       ▼
   ERP-IOT (this repo)
   ├── FastAPI Backend  ─── JWT Auth, Marina CRUD, Webhooks
   ├── PostgreSQL       ─── Marinas, Users, Alarm/Session Logs, Cache
   └── React Frontend   ─── Multi-marina dashboard
       │
       ▼  (HTTP API + Webhooks)
Pedestal SW instances (one per marina)
   └── Arduino Opta ↔ MQTT
```

## Phase 1 Features

- Multi-marina management (super_admin sees all, marina_manager sees assigned)
- JWT authentication with role-based access control
- Pedestal API proxy with caching and stale-data fallback
- Webhook receiver with HMAC-SHA256 signature validation
- Session control (allow/deny/stop) with full audit logging
- Alarm log with acknowledgment
- Energy analytics dashboard with Recharts
- Real-time updates via WebSocket
- Security middleware (injection detection, security headers)

## Phase 2 Features — Marina Dashboard Restructure + Pedestal Detail

### Marina Dashboard (2 tabs)
- **Overview tab** — all existing marina content unchanged; pedestal cards are now clickable links to Pedestal Detail
- **Berths tab** — unified berth view grouped by pedestal:
  - Per-berth occupancy badge (Occupied / Available / No Analysis)
  - **Get Frame** button — fetches JPEG from Pedestal SW camera inline
  - **Refresh All** button + per-pedestal refresh
  - Data fetched on demand (not polled)

### Pedestal Detail page (`/marinas/:marinaId/pedestals/:pedestalId`)
- **Real Time tab** — health indicators, active/pending sessions, alarm log — all filtered to this pedestal
- **Berths tab** — per-berth occupancy + frame grab + RTSP stream URL (copyable, VLC note)
- **Controls tab** — Allow/Deny/Stop sessions + Acknowledge alarms with confirmation dialogs; mirrors PedestalControl look and feel; every action logged to audit_log

### Camera & Berth Ext API (new backend endpoints)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/marinas/{marina_id}/pedestals/{pedestal_id}/berths/occupancy` | Berth occupancy from Pedestal SW (cached, stale fallback) |
| GET | `/api/marinas/{marina_id}/pedestals/{pedestal_id}/camera/frame` | Live JPEG frame from Pedestal SW camera (no cache, `Cache-Control: no-store`) |
| GET | `/api/marinas/{marina_id}/pedestals/{pedestal_id}/camera/stream` | RTSP stream URL from Pedestal SW (cached, stale fallback) |

All three endpoints require JWT auth + marina access. Camera frame fetches are logged to audit_log as operator-initiated actions.

## Quick Start

### Prerequisites
- PostgreSQL 16+ running locally or via Docker
- Python 3.11+
- Node.js 18+

### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/Scripts/activate  # Windows
# or: source .venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Configure environment — create backend/.env with:
#   DATABASE_URL=postgresql://erp_user:erp_password@localhost:5432/erp_iot
#   JWT_SECRET=<random hex>
#   DEFAULT_ADMIN_EMAIL=admin@erp-iot.local
#   DEFAULT_ADMIN_PASSWORD=<your password>
#   ALLOWED_ORIGINS=http://localhost:5173
#   ERP_ENCRYPTION_KEY=<generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# Run database migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --reload
```

Backend runs at http://localhost:8000
API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:5173

### Docker Compose (full stack)

```bash
docker compose up -d
```

## Default Login

After seeding (set `DEFAULT_ADMIN_PASSWORD` in `.env`):
- Email: `admin@erp-iot.local` (or `DEFAULT_ADMIN_EMAIL`)
- Password: whatever you set in `DEFAULT_ADMIN_PASSWORD`

## Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

**96 tests** covering auth, marinas, dashboard, controls, energy, alarms, webhooks, pedestal API client (retry/cache/stale), and all Phase 2 pedestal ext endpoints.

Pre-push hook runs the full suite automatically. Pushes to `main` require `CLOUD_IOT_RELEASE=1` and a merged `dev` branch.

## System Verification

```bash
bash scripts/verify_system.sh         # Full check
bash scripts/verify_system.sh --quick # Skip slow checks
```

## Git Workflow

- `dev` branch: daily development work — push here first
- `main` branch: releases only — requires `CLOUD_IOT_RELEASE=1` or interactive confirmation

```bash
# Daily work
git checkout dev
git commit -m "feat: ..."
git push origin dev

# Release
git checkout main
git merge dev
CLOUD_IOT_RELEASE=1 git push origin main
```

## API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Get JWT token |
| GET | `/api/auth/me` | Current user info |
| POST | `/api/auth/refresh` | Refresh token |

### Marinas (super_admin only for write)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/marinas` | List accessible marinas |
| POST | `/api/marinas` | Create marina |
| GET | `/api/marinas/{id}` | Get marina |
| PATCH | `/api/marinas/{id}` | Update marina |
| DELETE | `/api/marinas/{id}` | Delete marina |
| POST | `/api/marinas/{id}/access` | Grant user access |
| DELETE | `/api/marinas/{id}/access/{uid}` | Revoke access |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/marinas/{id}/dashboard` | Aggregated overview |
| GET | `/api/marinas/{id}/health` | Marina health |
| GET | `/api/marinas/{id}/pedestals` | List pedestals |

### Controls
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/marinas/{id}/sessions/{sid}/allow` | Allow session |
| POST | `/api/marinas/{id}/sessions/{sid}/deny` | Deny session |
| POST | `/api/marinas/{id}/sessions/{sid}/stop` | Stop session |

### Energy
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/marinas/{id}/energy/daily` | Daily analytics |
| GET | `/api/marinas/{id}/energy/summary` | Session summary |
| GET | `/api/marinas/{id}/sessions/active` | Active sessions |
| GET | `/api/marinas/{id}/sessions/pending` | Pending sessions |

### Alarms
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/marinas/{id}/alarms/active` | Active alarms (from Pedestal SW) |
| GET | `/api/marinas/{id}/alarms/log` | Local alarm log |
| POST | `/api/marinas/{id}/alarms/{aid}/acknowledge` | Acknowledge alarm |

### Pedestal Ext (Camera & Berths)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/marinas/{marina_id}/pedestals/{pedestal_id}/berths/occupancy` | Berth occupancy (cached, stale fallback) |
| GET | `/api/marinas/{marina_id}/pedestals/{pedestal_id}/camera/frame` | Live JPEG frame (`image/jpeg`, no cache) |
| GET | `/api/marinas/{marina_id}/pedestals/{pedestal_id}/camera/stream` | RTSP stream URL (cached, stale fallback) |

### Webhooks
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/webhooks/pedestal/{marina_id}` | Receive Pedestal SW event |

## Data Flow: Stale Data Handling

When a Pedestal SW instance is unreachable:
1. ERP-IOT retries up to 3× with exponential backoff (1s, 2s, 4s)
2. Falls back to last cached data in `pedestal_cache` table
3. Returns `is_stale: true` in response
4. Frontend shows yellow `StaleDataBanner`
