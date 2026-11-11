#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com> — disinstallazione per Linux (le impostazioni personali e le firme salvate restano)
# Uso: ./uninstall.sh   (per l'utente)     sudo ./uninstall.sh --system   (installazione di sistema)
set -euo pipefail
if [ "${1:-}" = "--system" ]; then
  [ "$(id -u)" = 0 ] || { echo "Serve root: sudo ./uninstall.sh --system"; exit 1; }
  APPDIR=/opt/pdfdesk; BINDIR=/usr/local/bin; SHARE=/usr/share
else
  APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/pdfdesk"; BINDIR="$HOME/.local/bin"; SHARE="${XDG_DATA_HOME:-$HOME/.local/share}"
fi
[ "$(readlink "$BINDIR/pdfdesk" 2>/dev/null)" = "$APPDIR/pdfdesk" ] && rm -f "$BINDIR/pdfdesk"
rm -f "$SHARE/applications/pdfdesk.desktop" "$SHARE/icons/hicolor/scalable/apps/pdfdesk.svg"
for s in 16 32 48 64 128 256 512; do rm -f "$SHARE/icons/hicolor/${s}x${s}/apps/pdfdesk.png"; done
rm -rf "$APPDIR"
command -v update-desktop-database >/dev/null && update-desktop-database "$SHARE/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f "$SHARE/icons/hicolor" 2>/dev/null || true
echo "PDFDesk rimosso."
