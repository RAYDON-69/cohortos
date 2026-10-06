#!/usr/bin/env bash
# Portable proof runner. Never prints tokens.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RESULTS="${RESULTS_DIR:-$HOME/work/results}"
mkdir -p "$RESULTS" "$HOME/work/logs"
SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
REPORT="$ROOT/verification-report.md"
ONLY=""
LOW_MEM=0
while [ $# -gt 0 ]; do
  case "$1" in
    --only) ONLY="$2"; shift 2 ;;
    --low-mem) LOW_MEM=1; shift ;;
    *) shift ;;
  esac
done
{
  echo "# verification-report"
  echo "sha: $SHA"
  echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "low_mem: $LOW_MEM"
} >"$REPORT"
fail=0
write_result() {
  local gate="$1" exitc="$2" detail="${3:-}"
  python3 -c "
import json, time
from pathlib import Path
Path('$RESULTS/$gate.json').write_text(json.dumps({
  'gate': '$gate', 'exit': $exitc, 'sha': '$SHA',
  'detail': '''$detail''', 'ts': time.time()
}, indent=2))
" 2>/dev/null || echo "{\"gate\":\"$gate\",\"exit\":$exitc}" >"$RESULTS/$gate.json"
}
should_run() {
  local gate="$1"
  if [ -n "$ONLY" ] && [ "$ONLY" != "$gate" ]; then return 1; fi
  if [ -f "$RESULTS/$gate.json" ]; then
    if python3 -c "import json; d=json.load(open('$RESULTS/$gate.json')); raise SystemExit(0 if d.get('exit')==0 and d.get('sha')=='$SHA' else 1)" 2>/dev/null; then
      echo "### $gate SKIP already passed for $SHA" | tee -a "$REPORT"
      return 1
    fi
  fi
  return 0
}
run() {
  local gate="$1"; shift
  should_run "$gate" || return 0
  echo "### $gate" | tee -a "$REPORT"
  echo "cmd: $*" | tee -a "$REPORT"
  set +e
  "$@" >"$HOME/work/logs/$gate.log" 2>&1
  local rc=$?
  set -e
  echo "exit: $rc" | tee -a "$REPORT"
  write_result "$gate" "$rc" "see logs/$gate.log"
  if [ "$rc" != "0" ]; then fail=1; fi
}
not_run() {
  echo "### $1 NOT RUN — $2" | tee -a "$REPORT"
  write_result "$1" 99 "NOT RUN: $2"
}

export COHORTOS_ENV="${COHORTOS_ENV:-test}"
export COHORTOS_JWT_SECRET="${COHORTOS_JWT_SECRET:-final-verify-secret-not-for-prod32}"
export COHORTOS_TEST_EXPOSE_OTP="${COHORTOS_TEST_EXPOSE_OTP:-1}"
export COHORTOS_SKIP_MODEL_DOWNLOAD="${COHORTOS_SKIP_MODEL_DOWNLOAD:-1}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
if [ "$LOW_MEM" = "1" ]; then
  export NODE_OPTIONS="--max-old-space-size=600"
fi

run gate_logic python3 -m pytest tests/test_ci_gate_logic.py -q --tb=line
run unit python3 -m pytest tests/ -q --tb=line --junitxml=/tmp/junit-unit.xml -p no:cacheprovider -m "not live and not e2e_ui"
run skip_budget python3 scripts/check_skip_budget.py
run stress python3 -m pytest tests/test_stress_p49.py -q --tb=line
run chaos env CHAOS_SEED=42 python3 -m pytest tests/test_stress_p49.py::test_kill9_chaos_idempotent_writer -q --tb=line
run route_inventory python3 -m pytest tests/test_route_inventory.py -q --tb=line
run boot_backup python3 -m pytest tests/test_boot_backup_restore.py -q --tb=line
run package_overrides python3 -m pytest tests/test_package_json_overrides.py -q --tb=line

if [ -f frontend/package-lock.json ] && command -v npm >/dev/null 2>&1; then
  (
    cd frontend
    run npm_ci npm ci --prefer-offline --ignore-scripts --no-audit --no-fund --legacy-peer-deps --no-progress
    if [ -d node_modules ]; then
      run npm_build npm run build
    else
      not_run npm_build "no node_modules after ci"
    fi
  )
else
  not_run npm_ci "npm or lock missing"
  not_run npm_build "npm or lock missing"
fi

echo "overall_fail=$fail" | tee -a "$REPORT"
exit "$fail"
