#!/usr/bin/env bash
# Single source of truth for Linux x86_64 release tarball.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="${COHORTOS_VERSION:-0.1.0-rc1}"
SHA="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
OUT="${COHORTOS_DIST_DIR:-$ROOT/dist/linux}"
STAGE="$OUT/stage"
NAME="cohortos-linux-x86_64-${VERSION}"
rm -rf "$STAGE"
mkdir -p "$STAGE/api" "$STAGE/frontend" "$STAGE/wheelhouse" "$STAGE/migrations" "$STAGE/bin" "$STAGE/docs"

echo "== frontend build =="
(
  cd frontend
  npm ci --no-audit --no-fund --legacy-peer-deps
  # Ensure native rolldown binding present after ci
  if ! find node_modules -name 'rolldown-binding*.node' 2>/dev/null | grep -q .; then
    npm install --no-audit --no-fund --legacy-peer-deps @rolldown/binding-linux-x64-gnu || true
    npm rebuild || true
  fi
  npm run build
)
cp -a frontend/dist "$STAGE/frontend/dist"

echo "== python wheels (runtime only) =="
# Runtime requirements: strip dev-only if separate file exists
REQ="$ROOT/requirements.txt"
python3 -m pip wheel -r "$REQ" -w "$STAGE/wheelhouse" \
  --python-version 312 \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --abi cp312 \
  --only-binary=:all: 2>/dev/null || python3 -m pip wheel -r "$REQ" -w "$STAGE/wheelhouse"

echo "== assemble app =="
cp -a api "$STAGE/"
cp -a services "$STAGE/" 2>/dev/null || true
cp -a models "$STAGE/" 2>/dev/null || true
cp -a migrations "$STAGE/" 2>/dev/null || true
# top-level python packages used by api
for d in services models; do
  [ -d "$d" ] && cp -a "$d" "$STAGE/"
done
cp requirements.txt "$STAGE/"
cp packaging/linux/install.sh "$STAGE/install.sh"
cp packaging/linux/uninstall.sh "$STAGE/uninstall.sh"
cp packaging/linux/cohortos "$STAGE/bin/cohortos"
cp packaging/linux/cohortos.desktop "$STAGE/cohortos.desktop"
cp docs/INSTALL_LINUX.md "$STAGE/docs/" 2>/dev/null || true
chmod +x "$STAGE/install.sh" "$STAGE/uninstall.sh" "$STAGE/bin/cohortos"

cat > "$STAGE/BUILD_INFO.json" << JSON
{
  "version": "$VERSION",
  "git_sha": "$SHA",
  "built_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "python": "3.12",
  "platform": "linux-x86_64"
}
JSON

echo "== secret exclusion assertion =="
if find "$STAGE" -type f \( -name '.env' -o -name '.env.*' -o -name '*.pem' -o -name '*id_rsa*' \) \
  | grep -v example | grep -q .; then
  echo "FATAL: secret-looking files in stage"; find "$STAGE" -type f \( -name '.env' -o -name '.env.*' \) ; exit 1
fi
# no .git
if [ -d "$STAGE/.git" ]; then echo "FATAL: .git in stage"; exit 1; fi
if [ -d "$STAGE/node_modules" ]; then echo "FATAL: node_modules in stage"; exit 1; fi
if [ -d "$STAGE/tests" ]; then echo "FATAL: tests in stage"; exit 1; fi

echo "== tarball =="
mkdir -p "$OUT"
tar -C "$STAGE" -czf "$OUT/${NAME}.tar.gz" .
( cd "$OUT" && sha256sum "${NAME}.tar.gz" > SHA256SUMS )
echo "OK $OUT/${NAME}.tar.gz"
cat "$OUT/SHA256SUMS"
