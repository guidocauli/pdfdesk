#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Compila l'eseguibile WINDOWS da un computer Linux, con Wine + Python per Windows dentro Docker.
# Requisiti: docker funzionante e accesso a Internet (immagine tobix/pywine, pacchetti pip, Ghostscript da GitHub).
# Uso: ./build_windows_wine.sh [--with-tests]      (variabili: WINE_IMAGE, GS_TAG, GS_FILE)
set -euo pipefail
cd "$(dirname "$0")"
echo "PDFDesk — Guido Cauli <guido.cauli@gmail.com> — build Windows (Wine)"
[ "${1:-}" = "--help" ] && { sed -n 3,6p "$0"; exit 0; }
command -v docker >/dev/null || { echo "Errore: docker non trovato (serve per Wine+Python di Windows)."; exit 1; }
IMAGE=${WINE_IMAGE:-tobix/pywine:3.11}
GS_TAG=${GS_TAG:-gs10021}; GS_FILE=${GS_FILE:-gs10021w64.exe}          # Ghostscript 10.02.1 a 64 bit
TESTS=0; [ "${1:-}" = "--with-tests" ] && TESTS=1
mkdir -p dist build
docker run --rm -e TESTS=$TESTS -e GS_TAG="$GS_TAG" -e GS_FILE="$GS_FILE" -e HOSTUID="$(id -u)" -e HOSTGID="$(id -g)" \
  -v "$PWD":/src -w /src "$IMAGE" /bin/bash -c '
set -e
export WINEDEBUG=-all
echo "== Ghostscript per Windows"
if [ ! -f /tmp/gs.exe ]; then
  curl -fL -o /tmp/gs.exe "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/$GS_TAG/$GS_FILE"
fi
wine /tmp/gs.exe /S /D=C:\\gs\\gs10.02.1 || true
GS=$(find "$WINEPREFIX/drive_c/gs" -name gswin64c.exe | head -1)
[ -n "$GS" ] || { echo "Ghostscript non installato nel prefisso Wine"; exit 1; }
export PDFDESK_GS="C:\\gs\\gs10.02.1\\bin\\gswin64c.exe"
echo "== Dipendenze"
wine python -m pip install --no-warn-script-location -r requirements.txt
# Wine 9 non implementa alcune funzioni di numpy 2 (crealf): componenti non usati da PDFDesk, già esclusi dal pacchetto
wine python -m pip uninstall -y numpy onnxruntime pymupdf4llm pymupdf_layout 2>/dev/null || true
if [ "$TESTS" = 1 ]; then
  export QT_QPA_PLATFORM=offscreen
  for t in core gui features standards; do wine python -I -W ignore tests/test_$t.py || echo "ATTENZIONE: test_$t non superato sotto Wine"; done
  unset QT_QPA_PLATFORM
fi
echo "== PyInstaller"
cd packaging && wine python -m PyInstaller --noconfirm --clean --distpath ../dist --workpath ../build pdfdesk.spec && cd ..
echo "== Collaudo (solo parte non grafica: Qt su Wine richiede icuuc.dll di Windows, che Wine non ha)"
python3 - <<PY
import pymupdf
d = pymupdf.open(); d.new_page().insert_text((72, 100), "Prova PDFDesk"); d.save("/tmp/in.pdf")
PY
wine dist/pdfdesk.exe --compress /tmp/in.pdf /tmp/out.pdf --standard pdfa-2b && echo "Conversione PDF/A con Ghostscript incluso: OK" || echo "ATTENZIONE: conversione PDF/A non riuscita"
chown -R "$HOSTUID:$HOSTGID" dist build 2>/dev/null || true
'
[ -f dist/pdfdesk.exe ] || { echo "Errore: dist/pdfdesk.exe non creato"; exit 1; }
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pdfdesk/__init__.py)
VER=$VER python3 - <<'PY'
import os, zipfile
with zipfile.ZipFile(f"dist/pdfdesk-{os.environ['VER']}-windows-x86_64.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in ("dist/pdfdesk.exe", "LICENSE", "README.md", "THIRD_PARTY.md"):
        z.write(f, f.split("/")[-1])
PY
echo "Pacchetto creato: dist/pdfdesk-$VER-windows-x86_64.zip"
