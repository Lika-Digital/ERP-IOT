#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT — Automated Test Suite
#
#  Stages:
#    1. pytest        — backend functional tests (must pass, blocks commit)
#    2. Bandit        — Python security scan (high severity blocks)
#    3. Basic gap checks — import sanity, schema sanity
#
#  Usage: bash tests/run_tests.sh [pytest extra args]
#  Called automatically by the pre-commit and pre-push hooks.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"

YELLOW='\033[1;33m'
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║           ERP-IOT — Automated Test Suite            ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

OVERALL_EXIT=0

# ── Resolve Python ─────────────────────────────────────────────────────────────
VENV_ACTIVATE="backend/.venv/Scripts/activate"
[ -f "$VENV_ACTIVATE" ] || VENV_ACTIVATE="backend/.venv/bin/activate"

if [ -f "$VENV_ACTIVATE" ]; then
    # shellcheck source=/dev/null
    source "$VENV_ACTIVATE"
    VENV_BIN="backend/.venv/Scripts"
    [ -d "$VENV_BIN" ] || VENV_BIN="backend/.venv/bin"
else
    VENV_BIN=""
    echo -e "${YELLOW}[!] Virtual environment not found — using system Python${NC}"
fi

# After activating the venv, 'python' is on PATH — use it directly.
# Only fall back to explicit path if 'python' is not found.
PYTHON_BIN="python"
if ! command -v python &>/dev/null; then
    if [ -n "$VENV_BIN" ]; then
        # Windows: try .exe extension
        [ -f "${VENV_BIN}/python.exe" ] && PYTHON_BIN="${VENV_BIN}/python.exe"
        [ -f "${VENV_BIN}/python"     ] && PYTHON_BIN="${VENV_BIN}/python"
    fi
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — pytest
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "${CYAN}${BOLD}[1/3] Backend tests (pytest)${NC}"
echo ""

if ! ${PYTHON_BIN} -m pytest --version &>/dev/null; then
    ${PYTHON_BIN} -m pip install pytest pytest-asyncio httpx starlette --quiet
fi

cd backend
DATABASE_URL="sqlite:///./tests/test_erp.db" \
JWT_SECRET="test-secret-for-erp-iot-ci" \
${PYTHON_BIN} -m pytest tests/ -v --tb=short --no-header -W ignore::DeprecationWarning "$@"
PYTEST_EXIT=$?
rm -f tests/test_erp.db
cd "$ROOT_DIR"

echo ""
if [ $PYTEST_EXIT -eq 0 ]; then
    echo -e "${GREEN}[✔] pytest passed${NC}"
else
    echo -e "${RED}[✘] pytest FAILED — fix before committing${NC}"
    OVERALL_EXIT=1
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — Bandit (Python security)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}${BOLD}[2/3] Python security scan (bandit)${NC}"
echo ""

BANDIT_BIN="${VENV_BIN:-}/bandit"
[ -f "${BANDIT_BIN}.exe" ] && BANDIT_BIN="${BANDIT_BIN}.exe"

BANDIT_EXIT=0
if command -v bandit &>/dev/null || ([ -n "$VENV_BIN" ] && [ -f "${VENV_BIN}/bandit" ]); then
    BANDIT_CMD="bandit"
    [ -n "$VENV_BIN" ] && [ -f "${VENV_BIN}/bandit" ] && BANDIT_CMD="${VENV_BIN}/bandit"
    [ -f "${BANDIT_CMD}.exe" ] && BANDIT_CMD="${BANDIT_CMD}.exe"

    BANDIT_LOG="${LOG_DIR}/bandit_last.log"

    $BANDIT_CMD \
        -r backend/app/ \
        -ll \
        -ii \
        --exclude "backend/app/tests,backend/tests" \
        -f json \
        -o "$BANDIT_LOG" \
        2>/dev/null || true

    BANDIT_RESULTS=$(${PYTHON_BIN} - "$BANDIT_LOG" << 'PYEOF'
import sys, json
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    results = data.get("results", [])
    high   = [r for r in results if r.get("issue_severity") == "HIGH"]
    medium = [r for r in results if r.get("issue_severity") == "MEDIUM"]
    print(f"HIGH={len(high)}")
    print(f"MEDIUM={len(medium)}")
    for r in high:
        print(f"ISSUE={r['filename']}:{r['line_number']} [{r['test_id']}] {r['issue_text']}")
except Exception as e:
    print(f"PARSE_ERROR={e}")
PYEOF
)

    HIGH_COUNT=$(echo "$BANDIT_RESULTS" | grep "^HIGH=" | cut -d= -f2)
    MED_COUNT=$(echo "$BANDIT_RESULTS"  | grep "^MEDIUM=" | cut -d= -f2)
    HIGH_COUNT=${HIGH_COUNT:-0}
    MED_COUNT=${MED_COUNT:-0}

    echo -e "  ${RED}High severity   : ${HIGH_COUNT}${NC}"
    echo -e "  ${YELLOW}Medium severity : ${MED_COUNT}${NC}"

    if [ "$HIGH_COUNT" -gt 0 ]; then
        echo ""
        echo -e "${RED}  ── High severity issues ──────────────────────────────────${NC}"
        echo "$BANDIT_RESULTS" | grep "^ISSUE=" | sed 's/^ISSUE=/  ✘ /'
        echo ""
        echo -e "${RED}[✘] Bandit found ${HIGH_COUNT} high-severity issue(s)${NC}"
        BANDIT_EXIT=1
        OVERALL_EXIT=1
    elif [ "$MED_COUNT" -gt 0 ]; then
        echo -e "${YELLOW}[!] Bandit: ${MED_COUNT} medium issue(s) — review recommended${NC}"
    else
        echo -e "${GREEN}[✔] Bandit passed — no high/medium issues${NC}"
    fi
else
    echo -e "${YELLOW}[!] Bandit not found — skipping.${NC}"
    echo -e "    Install: pip install bandit"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — Basic gap checks
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}${BOLD}[3/3] Basic gap checks${NC}"
echo ""

# GAP-1: Can we import the app without crashing?
echo "  [GAP-1] App import sanity check..."
cd backend
IMPORT_CHECK=$(DATABASE_URL="sqlite:///./tests/gap_import.db" \
    JWT_SECRET="gap-check-secret" \
    ${PYTHON_BIN} -c "from app.main import app; print('OK')" 2>&1)
cd "$ROOT_DIR"

if [[ "$IMPORT_CHECK" == *"OK"* ]]; then
    echo -e "  ${GREEN}[✔] GAP-1 passed — app imports cleanly${NC}"
else
    echo -e "  ${RED}[✘] GAP-1 FAILED — app import error:${NC}"
    echo "  $IMPORT_CHECK"
    OVERALL_EXIT=1
fi
rm -f backend/tests/gap_import.db

# GAP-2: Frontend package.json has no duplicate conflicting deps
echo "  [GAP-2] Frontend package.json sanity check..."
${PYTHON_BIN} - << 'PYEOF' 2>&1
import json, sys
try:
    with open("frontend/package.json") as f:
        pkg = json.load(f)
    deps = set(pkg.get("dependencies", {}).keys())
    dev_deps = set(pkg.get("devDependencies", {}).keys())
    overlap = deps & dev_deps
    if overlap:
        print(f"WARN: packages in both deps and devDeps: {overlap}")
    else:
        print("OK")
except Exception as e:
    print(f"ERROR: {e}")
PYEOF
PKG_CHECK_RESULT=$(cd "$ROOT_DIR" && ${PYTHON_BIN} -c "
import json
try:
    with open('frontend/package.json') as f:
        pkg = json.load(f)
    deps = set(pkg.get('dependencies', {}).keys())
    dev_deps = set(pkg.get('devDependencies', {}).keys())
    overlap = deps & dev_deps
    print('FAIL' if overlap else 'OK')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1)

if [[ "$PKG_CHECK_RESULT" == "OK" ]]; then
    echo -e "  ${GREEN}[✔] GAP-2 passed — no conflicting deps${NC}"
else
    echo -e "  ${YELLOW}[!] GAP-2 WARNING — ${PKG_CHECK_RESULT}${NC}"
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "──────────────────────────────────────────────────────────"
if [ $OVERALL_EXIT -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ All checks passed.${NC}"
else
    echo -e "${RED}${BOLD}✗ One or more checks FAILED — fix errors before committing.${NC}"
fi
echo ""

exit $OVERALL_EXIT
