#!/usr/bin/env bash
# Usage: scripts/ci_step.sh <name> -- <cmd...>
set -uo pipefail
NAME="${1:-step}"
shift || true
if [[ "${1:-}" == "--" ]]; then shift; fi
OUT="/tmp/${NAME}.out"
set +e
"$@" 2>&1 | tee "$OUT"
RC=${PIPESTATUS[0]}
set -e
python3 - <<PY || true
import json, pathlib, os
name = ${NAME@Q}
name = """$NAME"""
out = pathlib.Path("""$OUT""")
text = out.read_text(errors="replace") if out.exists() else ""
doc = {
  "schema": "cohortos.ci-report/v1",
  "kind": "diag",
  "name": name,
  "exit_code": $RC,
  "log_tail": "\n".join(text.splitlines()[-120:]),
}
pathlib.Path(f"/tmp/diag-{name}.json").write_text(json.dumps(doc, indent=2))
print(json.dumps({"name": name, "exit_code": $RC, "tail_lines": len(text.splitlines())}))
PY
# best-effort publish
if [[ -f scripts/publish_diag.py ]]; then
  python scripts/publish_diag.py "$NAME" "diag-${NAME}-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.json" "/tmp/diag-${NAME}.json" || true
fi
exit $RC
