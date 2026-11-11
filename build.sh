#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Compila l'eseguibile per la piattaforma corrente (Linux o macOS), lo collauda e lo impacchetta in dist/.
set -euo pipefail
cd "$(dirname "$0")"
echo "PDFDesk — Guido Cauli <guido.cauli@gmail.com> — build"
[ "${1:-}" = "--help" ] && { echo "uso: ./build.sh [--skip-tests]"; exit 0; }
PY=${PYTHON:-python3}
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pdfdesk/__init__.py)
$PY -m pip install -r requirements.txt
if [ "${1:-}" != "--skip-tests" ]; then
  QT_QPA_PLATFORM=offscreen $PY -I -W ignore tests/test_core.py
  QT_QPA_PLATFORM=offscreen $PY -I -W ignore tests/test_gui.py
  QT_QPA_PLATFORM=offscreen $PY -I -W ignore tests/test_features.py
  QT_QPA_PLATFORM=offscreen $PY -I -W ignore tests/test_standards.py
fi
(cd packaging && $PY -m PyInstaller --noconfirm --clean --distpath ../dist --workpath ../build pdfdesk.spec)
OS=$(uname -s | tr '[:upper:]' '[:lower:]'); ARCH=$(uname -m)
if [ "$OS" = "darwin" ]; then
  APP="dist/PDFDesk.app/Contents/MacOS/pdfdesk"; "$APP" --selftest
  (cd dist && ditto -c -k --keepParent PDFDesk.app "pdfdesk-$VER-macos-$ARCH.zip")
else
  ./dist/pdfdesk --selftest
  mkdir -p build/pkg && cp dist/pdfdesk LICENSE README.md THIRD_PARTY.md build/pkg/
  tar -C build/pkg -czf "dist/pdfdesk-$VER-linux-$ARCH.tar.gz" .
fi
echo "Pacchetto creato in dist/"
