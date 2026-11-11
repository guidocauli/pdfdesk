#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Firma (Authenticode) un file Windows con il certificato autofirmato di PDFDesk, senza ricompilare nulla.
# Uso: ./sign_windows.sh ENTRATA.exe USCITA.exe        Richiede: osslsigncode (apt install osslsigncode)
# La chiave privata (packaging/signing/pdfdesk-sign.key) NON è nel repository: tienila al sicuro. Se manca, il file viene copiato non firmato.
set -euo pipefail
cd "$(dirname "$0")"
IN=${1:?uso: ./sign_windows.sh ENTRATA.exe USCITA.exe}; OUT=${2:?uso: ./sign_windows.sh ENTRATA.exe USCITA.exe}
KEY=${PDFDESK_SIGN_KEY:-packaging/signing/pdfdesk-sign.key}; CRT=${PDFDESK_SIGN_CERT:-packaging/signing/pdfdesk-sign.pem}
if [ ! -f "$KEY" ] || ! command -v osslsigncode >/dev/null; then
  echo "!! firma saltata (manca la chiave $KEY o osslsigncode): $OUT resta non firmato" >&2
  [ "$IN" = "$OUT" ] || cp "$IN" "$OUT"; exit 0
fi
TMP=$(mktemp -u); trap 'rm -f "$TMP"' EXIT
TS=()
[ "${PDFDESK_TIMESTAMP:-1}" = "1" ] && TS=(-ts http://timestamp.digicert.com)
if ! osslsigncode sign -certs "$CRT" -key "$KEY" -h sha256 -n "PDFDesk" -i "https://github.com/guidocauli/pdfdesk" "${TS[@]}" -in "$IN" -out "$TMP" >/dev/null 2>&1; then
  osslsigncode sign -certs "$CRT" -key "$KEY" -h sha256 -n "PDFDesk" -i "https://github.com/guidocauli/pdfdesk" -in "$IN" -out "$TMP" >/dev/null   # senza marca temporale (server non raggiungibile)
  echo "-- firmato senza marca temporale: $OUT" >&2
fi
mv "$TMP" "$OUT"; trap - EXIT
osslsigncode verify -CAfile "$CRT" -in "$OUT" 2>&1 | grep -E "Signature verification|Subject|Hash" | head -n 3 || true
