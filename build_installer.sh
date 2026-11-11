#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Crea l'installer Windows (NSIS) dall'eseguibile già compilato (dist-wine/pdfdesk.exe o dist/pdfdesk.exe).
# Uso: ./build_installer.sh [percorso/pdfdesk.exe]      Richiede: makensis (apt install nsis)
set -euo pipefail
cd "$(dirname "$0")"
echo "PDFDesk — Guido Cauli <guido.cauli@gmail.com> — installer Windows"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pdfdesk/__init__.py)
EXE=${1:-$( [ -f dist-wine/pdfdesk.exe ] && echo dist-wine/pdfdesk.exe || echo dist/pdfdesk.exe )}
command -v makensis >/dev/null || { echo "Errore: makensis non trovato (apt install nsis)"; exit 1; }
[ -f "$EXE" ] || { echo "Errore: $EXE non trovato"; exit 1; }
mkdir -p dist
OUT="$PWD/dist/pdfdesk-$VER-windows-x86_64-setup.exe"
(cd packaging/windows && makensis -V2 -DVERSION="$VER" -DEXE="$(realpath "../../$EXE" 2>/dev/null || realpath "$EXE")" -DOUTFILE="$OUT" pdfdesk.nsi)
echo "Installer creato: $OUT"
