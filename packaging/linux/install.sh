#!/usr/bin/env bash
# User-level install — no sudo.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${COHORTOS_HOME:-$HOME/.local/share/cohortos}"
CFGDIR="${XDG_CONFIG_HOME:-$HOME/.config}/cohortos"
BINDIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
mkdir -p "$PREFIX" "$CFGDIR" "$BINDIR" "$PREFIX/data" "$PREFIX/logs"

echo "Installing CohortOS into $PREFIX"
cp -a "$HERE/api" "$HERE/services" "$HERE/models" "$HERE/frontend" "$HERE/BUILD_INFO.json" "$PREFIX/" 2>/dev/null || true
cp -a "$HERE/migrations" "$PREFIX/" 2>/dev/null || true
cp -a "$HERE/wheelhouse" "$PREFIX/"
cp "$HERE/requirements.txt" "$PREFIX/" 2>/dev/null || true

python3 -m venv "$PREFIX/venv"
# shellcheck disable=SC1091
source "$PREFIX/venv/bin/activate"
pip install --upgrade pip
pip install --no-index --find-links "$PREFIX/wheelhouse" -r "$PREFIX/requirements.txt" || \
  pip install --no-index --find-links "$PREFIX/wheelhouse" $(ls "$PREFIX/wheelhouse"/*.whl)

# env
ENVF="$CFGDIR/cohortos.env"
if [ ! -f "$ENVF" ]; then
  JWT=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  FOUNDER=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
  cat > "$ENVF" << EENV
COHORTOS_ENV=production
COHORTOS_JWT_SECRET=$JWT
COHORTOS_FOUNDER_TOKEN=$FOUNDER
COHORTOS_BIND=127.0.0.1
COHORTOS_PORT=8000
COHORTOS_DATA_DIR=$PREFIX/data
COHORTOS_AUTH_DB=$PREFIX/data/auth.db
COHORTOS_CLOUD_DB=$PREFIX/data/cloud.db
COHORTOS_LOCAL_OTP_FILE=$PREFIX/data/otp_log.txt
COHORTOS_TEST_EXPOSE_OTP=0
COHORTOS_RATE_LIMIT_DISABLED=0
COHORTOS_SKIP_MODEL_DOWNLOAD=1
EENV
  chmod 600 "$ENVF"
  echo "Wrote $ENVF (secrets generated)"
fi

install -m 755 "$HERE/bin/cohortos" "$BINDIR/cohortos"
# desktop entry
APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPDIR"
sed "s|@BINDIR@|$BINDIR|g" "$HERE/cohortos.desktop" > "$APPDIR/cohortos.desktop" 2>/dev/null || \
  cat > "$APPDIR/cohortos.desktop" << ED
[Desktop Entry]
Name=CohortOS
Comment=Coaching centre desk
Exec=$BINDIR/cohortos start --open
Terminal=false
Type=Application
Categories=Office;
ED

echo "Install complete."
echo "  $BINDIR/cohortos start"
echo "  $BINDIR/cohortos bootstrap   # first centre + owner (reads local OTP file)"
echo "  Open http://127.0.0.1:8000"
