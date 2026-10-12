#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  ERP-IOT gate — ONE script for pre-commit, pre-push and CI (spec §9, §10 faza 1).
#
#    bash scripts/gate.sh          full gate: lint, pytest, bandit, frontend, boot, browser,
#                                  growth (7 simulated days, retention proven)
#    bash scripts/gate.sh --fast   pre-commit: lint, pytest, bandit
#
#  Rule: a missing tool, a missing venv, missing node_modules, a skipped test,
#  or a server that does not come up is a FAILURE. Never a skip, never exit 0.
#  The previous tests/run_tests.sh fell back to system Python, pip-installed
#  unpinned pytest on the fly, and skipped bandit if it was not installed.
#
#  Emergency bypass is git's own --no-verify; this script has none.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="full"
[ "${1:-}" = "--fast" ] && MODE="fast"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

STAGES_RUN=0
PYTEST_LINE="PYTEST: not run"
BOOT_LINE="BOOT: not run"
BROWSER_LINE="BROWSER: not run"
GROWTH_LINE="GROWTH: not run"
STAGES_OK=0
FAILED=()

stage() { STAGES_RUN=$((STAGES_RUN + 1)); echo ""; echo -e "${CYAN}${BOLD}[$1] $2${NC}"; }
pass()  { STAGES_OK=$((STAGES_OK + 1)); echo -e "${GREEN}[ok] $1${NC}"; }
fail()  { FAILED+=("$1"); echo -e "${RED}[FAIL] $1${NC}"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ── Tools: from the project venv, or the gate fails ──────────────────────────
VENV_BIN="backend/.venv/Scripts"
[ -d "$VENV_BIN" ] || VENV_BIN="backend/.venv/bin"
PY="$VENV_BIN/python"
[ -f "$PY.exe" ] && PY="$PY.exe"

if [ ! -f "$PY" ]; then
    echo -e "${RED}[FAIL] backend/.venv not found.${NC}"
    echo "       python -m venv backend/.venv && backend/.venv/*/pip install -r backend/requirements.lock"
    echo ""
    echo "GATE: 0 stages run - FAILED"
    exit 1
fi
PY="$ROOT/$PY"

echo ""
echo -e "${BOLD}ERP-IOT gate ($MODE)${NC}  python: $("$PY" --version 2>&1)"

# ═════════════════════════════════════════════════════════════════════════════
stage "lint" "ruff (rules pinned in backend/ruff.toml)"
if (cd backend && "$PY" -m ruff check --config ruff.toml app tests alembic ../scripts); then
    pass "ruff"
else
    fail "ruff"
fi

# ═════════════════════════════════════════════════════════════════════════════
stage "pytest" "backend tests - no skips, no empty runs"
(cd backend && "$PY" -m pytest tests/ -q --tb=short -p no:cacheprovider \
    -W ignore::DeprecationWarning --junitxml="$WORK/pytest.xml")
PYTEST_EXIT=$?
rm -f backend/tests/test_erp.db
PYTEST_LINE="$("$PY" scripts/pytest_counts.py "$WORK/pytest.xml")"
COUNTS_EXIT=$?
echo "$PYTEST_LINE"
PYTEST_LINE="$(echo "$PYTEST_LINE" | head -1)"
if [ $PYTEST_EXIT -eq 0 ] && [ $COUNTS_EXIT -eq 0 ]; then
    pass "pytest"
else
    fail "pytest"
fi

# ═════════════════════════════════════════════════════════════════════════════
stage "bandit" "security scan - high AND medium block"
if "$PY" -m bandit --version >/dev/null 2>&1; then
    "$PY" -m bandit -q -r backend/app -f json -o "$WORK/bandit.json" >/dev/null 2>&1
    "$PY" - "$WORK/bandit.json" <<'PYEOF'
import json, sys
try:
    data = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print(f"  no readable bandit report ({exc})"); sys.exit(1)
res = data.get("results", [])
bad = [r for r in res if r.get("issue_severity") in ("HIGH", "MEDIUM")]
low = len(res) - len(bad)
print(f"BANDIT: high={sum(r['issue_severity']=='HIGH' for r in res)} "
      f"medium={sum(r['issue_severity']=='MEDIUM' for r in res)} low={low}")
for r in bad:
    print(f"  {r['filename']}:{r['line_number']} [{r['test_id']}] {r['issue_text']}")
sys.exit(1 if bad else 0)
PYEOF
    if [ $? -eq 0 ]; then pass "bandit"; else fail "bandit"; fi
else
    echo "  bandit is not in backend/.venv - install from backend/requirements.lock"
    fail "bandit (not installed)"
fi

if [ "$MODE" = "full" ]; then
# ═════════════════════════════════════════════════════════════════════════════
stage "frontend" "tsc --noEmit + vite build (real bundle)"
if [ ! -x frontend/node_modules/.bin/tsc ] && [ ! -f frontend/node_modules/.bin/tsc.cmd ]; then
    echo "  frontend/node_modules missing - run: (cd frontend && npm ci)"
    fail "frontend (node_modules missing)"
elif (cd frontend && node_modules/.bin/tsc --noEmit && node_modules/.bin/vite build --logLevel warn); then
    if ls frontend/dist/assets/index-*.js >/dev/null 2>&1; then
        pass "frontend"
    else
        echo "  vite exited 0 but produced no bundle"
        fail "frontend (no bundle)"
    fi
else
    fail "frontend"
fi

# ═════════════════════════════════════════════════════════════════════════════
stage "boot" "TC-ERP-BOOT-01a - migration, real uvicorn, health, login, auth route"
"$PY" scripts/boot_check.py | tee "$WORK/boot.log"
if [ "${PIPESTATUS[0]}" -eq 0 ]; then
    pass "boot"
else
    fail "boot"
fi

# ═════════════════════════════════════════════════════════════════════════════
stage "browser" "TC-ERP-BOOT-01b - real Chromium, real bundle, against the cabinet simulator"
"$PY" scripts/browser_check.py | tee "$WORK/browser.log"
if [ "${PIPESTATUS[0]}" -eq 0 ]; then
    pass "browser"
else
    fail "browser"
fi

# ═════════════════════════════════════════════════════════════════════════════
# Local hooks measure 2 simulated days, CI 7 (your decision 2026-10-12): the same
# check — rates, retention proof, budget — and the 7-day number comes from CI on
# real PostgreSQL. 7 days locally took 7-14 min per push on the author's machine.
GROWTH_DAYS=2
[ "${GITHUB_ACTIONS:-}" = "true" ] && GROWTH_DAYS=7
stage "growth" "phase 4 - database growth over $GROWTH_DAYS simulated days, bounded by retention"
"$PY" scripts/growth_check.py --days "$GROWTH_DAYS" | tee "$WORK/growth.log"
if [ "${PIPESTATUS[0]}" -eq 0 ]; then
    pass "growth"
else
    fail "growth"
fi
fi

[ -f "$WORK/boot.log" ] && BOOT_LINE="$(grep -o 'BOOT: .*' "$WORK/boot.log" | tail -1)"
[ -f "$WORK/browser.log" ] && BROWSER_LINE="$(grep -o 'BROWSER: .*' "$WORK/browser.log" | tail -1)"
[ -f "$WORK/growth.log" ] && GROWTH_LINE="$(grep -o 'GROWTH_JSON .*' "$WORK/growth.log" | tail -1)"

# ═════════════════════════════════════════════════════════════════════════════
EXPECTED=3
[ "$MODE" = "full" ] && EXPECTED=7
echo ""
echo "──────────────────────────────────────────────────────────"
echo "GATE ($MODE): $STAGES_OK/$EXPECTED stages passed"
# In GitHub Actions the summary also becomes an annotation: readable on the
# public run page and through the API without a login, unlike the raw log.
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    echo "::notice title=gate::GATE ($MODE): $STAGES_OK/$EXPECTED stages passed; $PYTEST_LINE; $BOOT_LINE; $BROWSER_LINE; $GROWTH_LINE"
fi
if [ ${#FAILED[@]} -eq 0 ] && [ "$STAGES_RUN" -eq "$EXPECTED" ] && [ "$STAGES_OK" -eq "$EXPECTED" ]; then
    echo -e "${GREEN}${BOLD}GREEN${NC}"
    exit 0
fi
for f in "${FAILED[@]}"; do echo -e "  ${RED}failed: $f${NC}"; done
echo -e "${RED}${BOLD}RED${NC}"
exit 1
