# ERP-IOT Deployment Guide

## Production Deployment Checklist

### 1. Server Prerequisites

- Ubuntu 22.04 LTS (or equivalent)
- PostgreSQL 16+
- Docker + Docker Compose v2
- Cloudflare tunnel (`cloudflared`)
- Python 3.11+
- Node.js 18+

### 2. PostgreSQL Setup

```sql
-- As postgres superuser:
CREATE USER erp_user WITH PASSWORD 'your-strong-password';
CREATE DATABASE erp_iot OWNER erp_user;
GRANT ALL PRIVILEGES ON DATABASE erp_iot TO erp_user;
```

Or via Docker Compose:
```bash
docker compose up -d postgres
```

### 3. Backend Configuration

```bash
cd backend
cp .env.example .env
```

Edit `.env`:
```env
DATABASE_URL=postgresql://erp_user:your-strong-password@localhost:5432/erp_iot
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
DEFAULT_ADMIN_EMAIL=admin@yourdomain.com
DEFAULT_ADMIN_PASSWORD=<strong-password>
ALLOWED_ORIGINS=https://erp.lika.solutions
```

### 4. Run Migrations

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

### 5. Backend Service (systemd)

```ini
# /etc/systemd/system/erp-iot-backend.service
[Unit]
Description=ERP-IOT Backend
After=network.target postgresql.service

[Service]
Type=simple
User=erp
WorkingDirectory=/opt/erp-iot/backend
EnvironmentFile=/opt/erp-iot/backend/.env
ExecStart=/opt/erp-iot/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable erp-iot-backend
systemctl start erp-iot-backend
```

### 6. Frontend Build

```bash
cd frontend
npm install
npm run build
# Artifacts in frontend/dist/
```

### 7. Nginx Configuration

Configure nginx to:
- Serve `frontend/dist/` as static files
- Proxy `/api/` to `http://localhost:8000/api/`
- Proxy `/ws` as WebSocket to `http://localhost:8000/ws`

See `nginx.conf` for a complete configuration template.

### 8. Cloudflare Tunnel

```bash
# Install cloudflared
# Configure tunnel to route erp.lika.solutions → http://localhost:80
cloudflared tunnel create erp-iot
cloudflared tunnel route dns erp-iot erp.lika.solutions
cloudflared tunnel run erp-iot
```

### 9. Verify Deployment

```bash
bash scripts/verify_system.sh
```

All 10 checks should pass (or warn for optional components).

---

## Connecting a Marina (Pedestal SW)

### On the ERP-IOT side

1. Log in as super_admin
2. Create a marina: POST `/api/marinas` with `pedestal_api_base_url` and `pedestal_api_key`
3. Note the `marina_id` returned
4. Generate a `webhook_secret` (e.g., `openssl rand -hex 32`)

### On the Pedestal SW side

Configure the Pedestal SW to send webhooks to:
```
POST https://erp.lika.solutions/api/webhooks/pedestal/{marina_id}
Header: X-Webhook-Signature: sha256=<hmac-sha256 of body with webhook_secret>
```

### Webhook Payload Format

```json
{
  "event_type": "alarm_triggered|session_created|session_updated|sensor_update",
  "pedestal_id": 1,
  "data": { ... }
}
```

### HMAC Signature (Python example)

```python
import hmac, hashlib, json

secret = "your-webhook-secret"
payload = {"event_type": "alarm_triggered", "pedestal_id": 1}
body = json.dumps(payload).encode()
sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
# Include in header: X-Webhook-Signature: {sig}
```

---

## Backup & Restore

### PostgreSQL backup

```bash
# Backup
pg_dump postgresql://erp_user:password@localhost:5432/erp_iot > backup_$(date +%Y%m%d).sql

# Restore
psql postgresql://erp_user:password@localhost:5432/erp_iot < backup_20260405.sql
```

### Automated daily backup

```bash
# /etc/cron.d/erp-iot-backup
0 3 * * * erp pg_dump postgresql://erp_user:password@localhost:5432/erp_iot | gzip > /opt/backups/erp_iot_$(date +\%Y\%m\%d).sql.gz
```

---

## Scaling

For high-load deployments:
- Run multiple uvicorn workers: `--workers 4`
- Use pgBouncer for connection pooling
- Configure Redis for session caching (future phase)
- Enable Cloudflare load balancing across multiple ERP-IOT nodes
