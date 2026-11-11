#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Crea l'archivio dei sorgenti con il numero di versione nel nome: dist/pdfdesk-<versione>-sorgenti.tar.gz
set -euo pipefail
cd "$(dirname "$0")"
VER=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' pdfdesk/__init__.py)
mkdir -p dist
# la chiave privata di firma (pdfdesk-sign.key/.pfx) non va mai negli archivi pubblici
tar --exclude=dist --exclude=build --exclude=build-win --exclude=dist-win --exclude=.git --exclude=dist-wine --exclude=build-wine --exclude=__pycache__ --exclude=.pytest_cache \
    --exclude=pdfdesk-sign.key --exclude=pdfdesk-sign.pfx --exclude=pdfdesk-sign.pem \
    --transform "s,^\.,pdfdesk-$VER," -czf "dist/pdfdesk-$VER-sorgenti.tar.gz" .
echo "Creato dist/pdfdesk-$VER-sorgenti.tar.gz"
