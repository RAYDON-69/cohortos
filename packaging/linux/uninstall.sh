#!/usr/bin/env bash
set -euo pipefail
PREFIX="${COHORTOS_HOME:-$HOME/.local/share/cohortos}"
CFGDIR="${XDG_CONFIG_HOME:-$HOME/.config}/cohortos"
BINDIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
"$BINDIR/cohortos" stop 2>/dev/null || true
rm -f "$BINDIR/cohortos"
rm -rf "$PREFIX/venv" "$PREFIX/api" "$PREFIX/frontend" "$PREFIX/wheelhouse"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$PREFIX" "$CFGDIR"
  echo "Purged data and config"
else
  echo "Removed app; data kept in $PREFIX/data (use --purge to delete)"
fi
