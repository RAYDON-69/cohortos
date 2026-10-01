#!/usr/bin/env bash
# Fail if main JS entry exceeds budget (4GB-device friendly target).
set -euo pipefail
cd "$(dirname "$0")/../frontend"
BUDGET_BYTES="${BUNDLE_BUDGET_BYTES:-1500000}"  # 1.5MB raw main chunk budget
if [ ! -d dist ]; then
  npm run build >/tmp/cohortos-bundle-build.log 2>&1 || {
    echo "build failed"; tail -20 /tmp/cohortos-bundle-build.log; exit 1;
  }
fi
# sum JS in dist/assets
TOTAL=$(find dist -name '*.js' -print0 2>/dev/null | xargs -0 wc -c 2>/dev/null | tail -1 | awk '{print $1}')
TOTAL=${TOTAL:-0}
echo "bundle_js_bytes=$TOTAL budget=$BUDGET_BYTES"
if [ "$TOTAL" -gt "$BUDGET_BYTES" ]; then
  echo "BUNDLE BUDGET EXCEEDED"
  exit 1
fi
echo "bundle budget OK"
