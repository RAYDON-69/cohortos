#!/usr/bin/env bash
# Same as CI package_linux.sh for a 4GB laptop when Actions is unavailable.
set -euo pipefail
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=1536}"
export COHORTOS_VERSION="${COHORTOS_VERSION:-0.1.0-rc1-local}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "Node $(node -v 2>/dev/null || echo MISSING) Python $(python3 -V)"
bash scripts/package_linux.sh
echo "Artifacts in dist/linux/"
ls -la dist/linux/
