#!/usr/bin/env bash
# Local/CI verification gate runner. Never prints tokens.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
REPORT="$ROOT/verification-report.md"
SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
{
  echo "# verification-report"
  echo "sha: $SHA"
  echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >"$REPORT"
fail=0
run() {
  local name="$1"
  shift
  echo "### $name" | tee -a "$REPORT"
  echo "cmd: $*" | tee -a "$REPORT"
  set +e
  "$@"
  local rc=$?
  set -e
  echo "exit: $rc" | tee -a "$REPORT"
  if [ "$rc" != "0" ]; then
    fail=1
  fi
  return 0
}
not_run() {
  echo "### $1" | tee -a "$REPORT"
  echo "status: NOT RUN — $2" | tee -a "$REPORT"
}

export COHORTOS_ENV="${COHORTOS_ENV:-test}"
export COHORTOS_JWT_SECRET="${COHORTOS_JWT_SECRET:-final-verify-secret-not-for-prod32}"
export COHORTOS_TEST_EXPOSE_OTP="${COHORTOS_TEST_EXPOSE_OTP:-1}"
export COHORTOS_SKIP_MODEL_DOWNLOAD="${COHORTOS_SKIP_MODEL_DOWNLOAD:-1}"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

run gate_logic python3 -m pytest tests/test_ci_gate_logic.py -q --tb=line || not_run gate_logic "missing test file"
run unit python3 -m pytest tests/ -q --tb=line --junitxml=/tmp/junit-unit.xml -p no:cacheprovider -m "not live and not e2e_ui"
if [ -f scripts/check_skip_budget.py ]; then
  run skip_budget python3 scripts/check_skip_budget.py
else
  not_run skip_budget "script missing"
fi
run stress python3 -m pytest tests/test_stress_p49.py -q --tb=line
run chaos env CHAOS_SEED=42 python3 -m pytest tests/test_stress_p49.py::test_kill9_chaos_idempotent_writer -q --tb=line
run route_inventory python3 -m pytest tests/test_route_inventory.py -q --tb=line
run boot_backup python3 -m pytest tests/test_boot_backup_restore.py -q --tb=line
run package_overrides python3 -m pytest tests/test_package_json_overrides.py -q --tb=line

if [ -f frontend/package-lock.json ]; then
  (
    cd frontend
    export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=600}"
    if command -v npm >/dev/null 2>&1; then
      run npm_ci npm ci --prefer-offline --ignore-scripts --no-audit --no-fund --legacy-peer-deps --no-progress
      if [ -d node_modules ]; then
        run npm_build npm run build
      else
        not_run npm_build "no node_modules"
      fi
    else
      not_run npm_ci "npm not installed"
    fi
  )
else
  not_run npm_ci "no package-lock"
fi

if command -v pip-audit >/dev/null 2>&1; then
  run pip_audit pip-audit -r requirements.txt || true
else
  not_run pip_audit "pip-audit not installed"
fi

echo "overall_fail=$fail" | tee -a "$REPORT"
exit "$fail"
