#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT — System Verification Script
#
#  Checks that all critical system components are running correctly.
#
#  Usage:
#    bash scripts/verify_system.sh           # Full check
#    bash scripts/verify_system.sh --quick   # Skip slow checks (4, 5, 6)
#
#  Exit code: 0 = all critical checks passed, 1 = one or more failures
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

QUICK=false
for arg in "$@"; do
    [[ "$arg" == "--quick" ]] && QUICK=true
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0
OVERALL_EXIT=0

pass() { echo -e "  ${GREEN}[✔] $1${NC}"; ((PASS++)) || true; }
fail() { echo -e "  ${RED}[✘] $1${NC}"; ((FAIL++)) || true; OVERALL_EXIT=1; }
warn() { echo -e "  ${YELLOW}[!] $1${NC}"; ((WARN++)) || true; }
info() { echo -e "  ${CYAN}     $1${NC}"; }
skip() { echo -e "  ${YELLOW}[~] SKIPPED (--quick): $1${NC}"; }

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_DIST="${FRONTEND_DIST:-frontend/dist}"
CLOUDFLARE_URL="${CLOUDFLARE_URL:-https://erp.lika.solutions}"

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║        ERP-IOT — System Verification              ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "  Backend:    ${BACKEND_URL}"
echo "  Frontend:   ${FRONTEND_DIST}"
echo "  Mode:       $(${QUICK} && echo 'Quick (checks 1-3, 7-10)' || echo 'Full')"
echo ""

# ── 1. PostgreSQL ──────────────────────────────────────────────────────────────
echo -e "${BOLD}[1] PostgreSQL connectivity${NC}"
if command -v pg_isready &>/dev/null; then
    if pg_isready -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -q 2>/dev/null; then
        pass "PostgreSQL is accepting connections"
    else
        fail "PostgreSQL is NOT accepting connections"
        info "Try: docker compose up -d postgres"
    fi
elif command -v psql &>/dev/null; then
    if psql "${DATABASE_URL:-postgresql://erp_user:erp_password@localhost:5432/erp_iot}" \
        -c "SELECT 1" &>/dev/null 2>&1; then
        pass "PostgreSQL responding (via psql)"
    else
        fail "PostgreSQL not responding"
    fi
else
    warn "pg_isready / psql not found — skipping PostgreSQL check"
fi
echo ""

# ── 2. Backend health ──────────────────────────────────────────────────────────
echo -e "${BOLD}[2] Backend API health${NC}"
if curl -sf "${BACKEND_URL}/api/health" -o /tmp/health_resp.json 2>/dev/null; then
    STATUS=$(python3 -c "import json,sys; d=json.load(open('/tmp/health_resp.json')); print(d.get('status','?'))" 2>/dev/null || echo "?")
    if [[ "$STATUS" == "ok" ]]; then
        WS_COUNT=$(python3 -c "import json; d=json.load(open('/tmp/health_resp.json')); print(d.get('ws_connections',0))" 2>/dev/null || echo "?")
        pass "Backend responding — status=${STATUS}, ws_connections=${WS_COUNT}"
    else
        fail "Backend responded but status=${STATUS}"
    fi
else
    fail "Backend not responding at ${BACKEND_URL}/api/health"
    info "Try: cd backend && uvicorn app.main:app --reload"
fi
echo ""

# ── 3. Frontend build ──────────────────────────────────────────────────────────
echo -e "${BOLD}[3] Frontend build artifacts${NC}"
if [ -d "${FRONTEND_DIST}" ] && [ -f "${FRONTEND_DIST}/index.html" ]; then
    ASSET_COUNT=$(find "${FRONTEND_DIST}" -name "*.js" -o -name "*.css" | wc -l)
    pass "Frontend dist/ found — ${ASSET_COUNT} JS/CSS assets"
else
    warn "Frontend not built (dist/ missing)"
    info "Run: cd frontend && npm run build"
fi
echo ""

# ── 4. Cloudflare tunnel ──────────────────────────────────────────────────────
echo -e "${BOLD}[4] Cloudflare tunnel routing${NC}"
if $QUICK; then
    skip "Cloudflare tunnel check (--quick)"
else
    if curl -sf --max-time 10 "${CLOUDFLARE_URL}/api/health" -o /tmp/cf_resp.json 2>/dev/null; then
        STATUS=$(python3 -c "import json; d=json.load(open('/tmp/cf_resp.json')); print(d.get('status','?'))" 2>/dev/null || echo "?")
        pass "Cloudflare tunnel routing to backend — status=${STATUS}"
    else
        warn "Cloudflare tunnel not reachable at ${CLOUDFLARE_URL}"
        info "Ensure cloudflared tunnel is running"
    fi
fi
echo ""

# ── 5. WebSocket ──────────────────────────────────────────────────────────────
echo -e "${BOLD}[5] WebSocket endpoint${NC}"
if $QUICK; then
    skip "WebSocket check (--quick)"
else
    WS_RESP=$(curl -sf --max-time 5 \
        --include \
        --no-buffer \
        -H "Connection: Upgrade" \
        -H "Upgrade: websocket" \
        -H "Sec-WebSocket-Version: 13" \
        -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
        "${BACKEND_URL/http/ws}/ws" 2>&1 | head -5 || true)

    if echo "$WS_RESP" | grep -q "101 Switching Protocols"; then
        pass "WebSocket endpoint upgrades correctly"
    else
        warn "Could not confirm WebSocket upgrade — may need authentication"
        info "Response: $(echo "$WS_RESP" | head -2)"
    fi
fi
echo ""

# ── 6. Pedestal API connectivity ───────────────────────────────────────────────
echo -e "${BOLD}[6] Pedestal API connectivity per marina${NC}"
if $QUICK; then
    skip "Marina API connectivity check (--quick)"
else
    MARINAS_RESP=$(curl -sf "${BACKEND_URL}/api/health" 2>/dev/null || echo "{}")
    # We'd need a token to check marina health — skip with informative message
    warn "Marina API connectivity check requires authentication"
    info "Manual check: GET /api/marinas/{id}/health with a valid JWT"
fi
echo ""

# ── 7. Webhook endpoint ────────────────────────────────────────────────────────
echo -e "${BOLD}[7] Webhook endpoint (401 expected for unsigned request)${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${BACKEND_URL}/api/webhooks/pedestal/1" \
    -H "Content-Type: application/json" \
    -d '{"event_type":"test"}' 2>/dev/null || echo "000")

if [[ "$HTTP_CODE" == "401" ]] || [[ "$HTTP_CODE" == "404" ]]; then
    pass "Webhook endpoint active — returned ${HTTP_CODE} (expected for unsigned/unknown marina)"
elif [[ "$HTTP_CODE" == "000" ]]; then
    fail "Webhook endpoint not reachable"
else
    warn "Webhook endpoint returned ${HTTP_CODE} — investigate"
fi
echo ""

# ── 8. Python imports ──────────────────────────────────────────────────────────
echo -e "${BOLD}[8] Python package imports${NC}"
VENV_BIN="backend/.venv/Scripts"
[ -d "$VENV_BIN" ] || VENV_BIN="backend/.venv/bin"
PYTHON_BIN="${VENV_BIN}/python"
[ -f "${PYTHON_BIN}.exe" ] && PYTHON_BIN="${PYTHON_BIN}.exe"
[ -f "$PYTHON_BIN" ] || PYTHON_BIN="python"

IMPORT_CHECK=$(${PYTHON_BIN} -c "
import fastapi, sqlalchemy, passlib, jose, httpx, pydantic_settings
print('OK')
" 2>&1)

if [[ "$IMPORT_CHECK" == "OK" ]]; then
    pass "All required Python packages import successfully"
else
    fail "Python import error: ${IMPORT_CHECK}"
    info "Run: cd backend && pip install -r requirements.txt"
fi
echo ""

# ── 9. DB tables ──────────────────────────────────────────────────────────────
echo -e "${BOLD}[9] Database tables exist${NC}"
DB_URL="${DATABASE_URL:-postgresql://erp_user:erp_password@localhost:5432/erp_iot}"

if command -v psql &>/dev/null; then
    TABLES=$(psql "$DB_URL" -t -c \
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;" \
        2>/dev/null | tr -d ' ' | grep -v '^$' | sort)

    REQUIRED_TABLES="alarm_log audit_log marinas pedestal_cache session_log sync_log user_marina_access users"
    ALL_FOUND=true
    for tbl in $REQUIRED_TABLES; do
        if ! echo "$TABLES" | grep -q "^${tbl}$"; then
            fail "Missing table: ${tbl}"
            ALL_FOUND=false
        fi
    done
    if $ALL_FOUND; then
        pass "All required tables present: $(echo $REQUIRED_TABLES | tr ' ' ',')"
    fi
else
    warn "psql not found — cannot verify tables directly"
    info "Run alembic upgrade head or init_db() on startup"
fi
echo ""

# ── 10. JWT auth test ──────────────────────────────────────────────────────────
echo -e "${BOLD}[10] JWT authentication test${NC}"
TEST_EMAIL="${TEST_ADMIN_EMAIL:-admin@erp-iot.local}"
TEST_PASS="${TEST_ADMIN_PASSWORD:-change-me-in-production}"

LOGIN_RESP=$(curl -sf -X POST "${BACKEND_URL}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${TEST_EMAIL}\",\"password\":\"${TEST_PASS}\"}" 2>/dev/null || echo "{}")

TOKEN=$(python3 -c "import json,sys; d=json.loads('${LOGIN_RESP}'); print(d.get('access_token',''))" 2>/dev/null || echo "")

if [[ -n "$TOKEN" ]]; then
    pass "JWT login successful — token obtained"

    # Verify /me endpoint
    ME_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        "${BACKEND_URL}/api/auth/me" \
        -H "Authorization: Bearer ${TOKEN}" 2>/dev/null || echo "000")

    if [[ "$ME_CODE" == "200" ]]; then
        pass "GET /api/auth/me returns 200 with valid token"
    else
        fail "GET /api/auth/me returned ${ME_CODE}"
    fi
else
    warn "Could not obtain JWT — default admin credentials not valid or user not seeded"
    info "Set DEFAULT_ADMIN_EMAIL and DEFAULT_ADMIN_PASSWORD in backend/.env"
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "──────────────────────────────────────────────────────"
echo -e "  ${GREEN}Passed${NC}: ${PASS}  |  ${RED}Failed${NC}: ${FAIL}  |  ${YELLOW}Warnings${NC}: ${WARN}"
echo ""

if [ $OVERALL_EXIT -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ All critical checks passed.${NC}"
else
    echo -e "${RED}${BOLD}✗ ${FAIL} critical check(s) failed — see above.${NC}"
fi
echo ""

exit $OVERALL_EXIT
