#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Crea l'archivio dei sorgenti con il numero di versione nel nome: dist/pdfdesk-<versione>-sorgenti.tar.gz
set -euo pipefail
cd "$(dirname "$0")"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pdfdesk/__init__.py)
mkdir -p dist
tar --exclude=dist --exclude=build --exclude=build-win --exclude=dist-win --exclude=.git --exclude=dist-wine --exclude=build-wine --exclude=__pycache__ --exclude=.pytest_cache \
    --transform "s,^\.,pdfdesk-$VER," -czf "dist/pdfdesk-$VER-sorgenti.tar.gz" .
echo "Creato dist/pdfdesk-$VER-sorgenti.tar.gz"
