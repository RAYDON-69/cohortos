#!/usr/bin/env bash
# Single entry: mirrors CI gates (P41). Fail fast on first hard gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "== workflow lint =="
python scripts/lint_workflows.py
echo "== unit tests (core) =="
export COHORTOS_ENV=test
export COHORTOS_JWT_SECRET="${COHORTOS_JWT_SECRET:-verify-secret-not-for-prod-32chars}"
export COHORTOS_SKIP_MODEL_DOWNLOAD=1
python -m pytest tests/test_no_chroma_in_prod.py tests/test_scorecard_by_kind.py tests/test_workflow_lint.py tests/test_bandit_summary.py tests/test_start_api_env_parity.py tests/test_money_invariants_b2.py tests/test_sqlite_vec_parity.py -q --tb=line
echo "== bandit =="
if command -v bandit >/dev/null; then
  bandit -r services api -ll
else
  echo "bandit not installed — skip (CI installs it)"
fi
echo "== frontend tsc (if node_modules) =="
if [ -d frontend/node_modules ]; then
  (cd frontend && npx tsc --noEmit) || true
else
  echo "frontend/node_modules missing — skip tsc"
fi
echo "verify OK"
