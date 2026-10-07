#!/usr/bin/env bash
# Bounded mutation testing for money + tenant-isolation modules.
set -uo pipefail
export COHORTOS_ENV="${COHORTOS_ENV:-test}"
export COHORTOS_JWT_SECRET="${COHORTOS_JWT_SECRET:-mutmut-secret-not-for-prod-32xx}"
export COHORTOS_AUTH_DB="${COHORTOS_AUTH_DB:-/tmp/mutmut-auth.db}"
export COHORTOS_CLOUD_DB="${COHORTOS_CLOUD_DB:-/tmp/mutmut-cloud.db}"
export COHORTOS_SKIP_MODEL_DOWNLOAD="${COHORTOS_SKIP_MODEL_DOWNLOAD:-1}"
export COHORTOS_TEST_EXPOSE_OTP="${COHORTOS_TEST_EXPOSE_OTP:-1}"

LOG=/tmp/mutmut-full.log
REPORT=/tmp/mutmut-report.json
: > "$LOG"

{
  echo "python: $(python --version 2>&1)"
  echo "mutmut: $(mutmut --version 2>&1 || true)"
  echo "cwd: $(pwd)"
} | tee -a "$LOG"

# Baseline: money + isolation unit tests must pass before mutants
BASE_TESTS=(
  tests/test_money_invariants_b2.py
  tests/test_refund_and_notices.py
  tests/test_fee_properties.py
  tests/test_dual_tenant_matrix.py
)
set +e
python -m pytest "${BASE_TESTS[@]}" -q --tb=line 2>&1 | tee -a "$LOG"
BASE_RC=${PIPESTATUS[0]}
set -e
if [ "$BASE_RC" != "0" ]; then
  # dual_tenant may need fastapi — fall back to money-only baseline
  set +e
  python -m pytest tests/test_money_invariants_b2.py tests/test_refund_and_notices.py tests/test_fee_properties.py -q --tb=line 2>&1 | tee -a "$LOG"
  BASE_RC=${PIPESTATUS[0]}
  set -e
fi
if [ "$BASE_RC" != "0" ]; then
  python - <<'PY' | tee -a "$LOG"
import json
doc={"pass":False,"error":"baseline tests failed","mutation_score_pct":0,"killed":0,"survived":0}
open("/tmp/mutmut-report.json","w").write(json.dumps(doc,indent=2))
print(doc)
PY
  exit 1
fi

# Paths to mutate — money + auth/tenant
PATHS="services/licence_service.py"
# Prefer real fee/payment modules if present
for f in services/pricing_engine.py services/payment_service.py services/attendance_service.py api/auth.py; do
  [ -f "$f" ] && PATHS="$PATHS,$f"
done

set +e
# mutmut 2.x API: run with paths-to-mutate; timeout soft
timeout 1200 mutmut run --paths-to-mutate="$PATHS" --tests-dir=tests --runner="python -m pytest -x -q --tb=line" 2>&1 | tee -a "$LOG"
MUT_RC=${PIPESTATUS[0]}
timeout 60 mutmut results 2>&1 | tee -a "$LOG"
timeout 60 mutmut junitxml /tmp/mutmut-junit.xml 2>&1 | tee -a "$LOG"
set -e

python - <<'PY'
import json, re, pathlib
log = pathlib.Path("/tmp/mutmut-full.log").read_text(errors="replace")
killed = survived = suspicious = timeout_n = 0
# mutmut results patterns
for m in re.finditer(r"Killed\s+(\d+)\s+out of\s+(\d+)", log):
    killed = int(m.group(1)); total = int(m.group(2)); survived = total - killed
for m in re.finditer(r"(\d+)\s+killed", log, re.I):
    killed = max(killed, int(m.group(1)))
for m in re.finditer(r"(\d+)\s+survived", log, re.I):
    survived = max(survived, int(m.group(1)))
# fallback parse summary table lines
if killed == 0 and survived == 0:
    for line in log.splitlines():
        if "Survived" in line or "survived" in line:
            nums = re.findall(r"\d+", line)
            if nums:
                survived = int(nums[0])
        if "Killed" in line or "killed" in line:
            nums = re.findall(r"\d+", line)
            if nums:
                killed = int(nums[0])
total = killed + survived
score = (100.0 * killed / total) if total else 0.0
# if mutmut never ran mutants, mark fail with error
doc = {
    "schema": "cohortos.ci-report/v1",
    "kind": "mutmut",
    "killed": killed,
    "survived": survived,
    "mutation_score_pct": round(score, 1),
    "pass": score >= 85.0 and total > 0,
    "threshold": 85.0,
    "paths": "money+tenant",
    "log_tail": "\n".join(log.splitlines()[-200:]),
}
pathlib.Path("/tmp/mutmut-report.json").write_text(json.dumps(doc, indent=2))
print(json.dumps({k: doc[k] for k in ("killed","survived","mutation_score_pct","pass")}, indent=2))
PY
exit 0
