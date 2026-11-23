#!/usr/bin/env bash
# PDFDesk — Guido Cauli
# Prepara la cartella release/ che la build di GitHub (Actions → build → Run workflow, «pubblica» attivo) usa per creare la
# bozza della Release: note di rilascio, archivio dei sorgenti e somme SHA-256 dei pacchetti compilati qui (Windows, Linux).
# Uso: ./prepara_release.sh   (dopo build.sh, build_installer.sh, lo zip Windows e make_sources.sh; note in dist/RELEASE_NOTES-<versione>.md)
set -euo pipefail
cd "$(dirname "$0")"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pdfdesk/__init__.py)
FILES=("pdfdesk-$VER-windows-x86_64-setup.exe" "pdfdesk-$VER-windows-x86_64.zip" "pdfdesk-$VER-linux-x86_64.tar.gz" "pdfdesk-$VER-sorgenti.tar.gz")
for f in "${FILES[@]}" "RELEASE_NOTES-$VER.md"; do
  [ -f "dist/$f" ] || { echo "Manca dist/$f" >&2; exit 1; }
done
rm -rf release && mkdir release
cp "dist/RELEASE_NOTES-$VER.md" release/RELEASE_NOTES.md
cp "dist/pdfdesk-$VER-sorgenti.tar.gz" release/
(cd dist && sha256sum "${FILES[@]}") > release/SHA256SUMS-parziale.txt
echo "release/ pronta per la versione $VER:"
ls -la release
cat release/SHA256SUMS-parziale.txt
