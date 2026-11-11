#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Compila tutto il possibile da questo computer:
#   Linux   → nativo (solo su Linux)           macOS   → su un Mac via SSH (se MAC_HOST è impostato)
#   Windows → Wine in Docker (se c'è docker)   su un Mac/Windows: usa direttamente build.sh / build.bat
set -uo pipefail
cd "$(dirname "$0")"
echo "PDFDesk — Guido Cauli <guido.cauli@gmail.com> — build di tutte le piattaforme"
OS=$(uname -s)
[ "$OS" = "Linux" ]  && { ./build.sh --skip-tests || echo "!! Linux: fallito"; }
[ "$OS" = "Darwin" ] && { ./build.sh || echo "!! macOS: fallito"; }
if [ "$OS" = "Linux" ]; then
  if command -v docker >/dev/null; then ./build_windows_wine.sh || echo "!! Windows: fallito"; else echo "-- Windows saltato: manca docker"; fi
  if [ -n "${MAC_HOST:-}" ]; then ./build_macos_remote.sh || echo "!! macOS: fallito"; else echo "-- macOS saltato: imposta MAC_HOST=utente@mac"; fi
fi
echo; ls -1 dist/pdfdesk-*.zip dist/pdfdesk-*.tar.gz 2>/dev/null
