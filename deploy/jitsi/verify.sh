#!/usr/bin/env bash
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"
echo "Checking $BASE ..."
curl -fsS -o /dev/null -w "%{http_code}\n" "$BASE" || { echo "FAIL primary"; exit 1; }
echo "OK primary reachable"

echo "Manual: confirm JWT-protected room rejects unauthenticated guests."
echo "Manual: confirm TLS cert valid."
echo "Manual: set COHORTOS_JITSI_FALLBACK_URL if primary blocked."
