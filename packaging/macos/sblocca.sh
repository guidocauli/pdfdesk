#!/bin/sh
# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Sblocca PDFDesk.app al primo avvio su macOS.
# Le app scaricate non firmate/notarizzate ricevono da macOS l'attributo di quarantena e vengono segnalate come
# «danneggiate». Questo script lo rimuove con: xattr -cr PDFDesk.app
#
# Uso (da Terminale, bash o zsh):
#     sh sblocca.sh                      # cerca PDFDesk.app accanto allo script, poi in /Applications
#     sh sblocca.sh /percorso/PDFDesk.app
set -eu
APP=${1:-}
if [ -z "$APP" ]; then
  HERE=$(cd "$(dirname "$0")" && pwd)
  for c in "$HERE/PDFDesk.app" "/Applications/PDFDesk.app" "$HOME/Applications/PDFDesk.app"; do
    [ -d "$c" ] && { APP=$c; break; }
  done
fi
if [ -z "$APP" ] || [ ! -d "$APP" ]; then
  echo "PDFDesk — Guido Cauli <guido.cauli@gmail.com>"
  echo "Errore: PDFDesk.app non trovata. Metti questo file accanto all'app oppure indica il percorso:  sh sblocca.sh /percorso/PDFDesk.app" >&2
  exit 1
fi
xattr -cr "$APP"
echo "PDFDesk — Guido Cauli <guido.cauli@gmail.com>"
echo "Sbloccata: $APP"
echo "Ora puoi aprirla normalmente (se vuoi, trascinala prima in Applicazioni)."
