#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Compila PDFDesk.app su un Mac raggiungibile via SSH (un Mac fisico, anche su rete locale) e riporta qui lo zip.
# macOS non si può compilare da Linux/Windows: PyInstaller e Qt richiedono macOS vero.
# Sul Mac servono: Python 3.12+ e Homebrew con «brew install ghostscript» (e Xcode Command Line Tools).
# Uso: MAC_HOST=utente@mac.lan ./build_macos_remote.sh      (opzionale: MAC_DIR=cartella remota, default ~/pdfdesk-build)
set -euo pipefail
cd "$(dirname "$0")"
echo "PDFDesk — Guido Cauli <guido.cauli@gmail.com> — build macOS (remota)"
: "${MAC_HOST:?Imposta MAC_HOST=utente@host}"
DIR=${MAC_DIR:-pdfdesk-build}
rsync -az --delete --exclude build --exclude dist --exclude __pycache__ --exclude .pytest_cache ./ "$MAC_HOST:$DIR/"
ssh "$MAC_HOST" "cd $DIR && export PATH=/opt/homebrew/bin:/usr/local/bin:\$PATH && ./build.sh"
mkdir -p dist
scp "$MAC_HOST:$DIR/dist/pdfdesk-*-macos-*.zip" dist/
ls -la dist/pdfdesk-*-macos-*.zip
