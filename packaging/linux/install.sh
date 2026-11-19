#!/usr/bin/env bash
# PDFDesk — Guido Cauli <guido.cauli@gmail.com> — installazione / aggiornamento per Linux
# Uso:   ./install.sh              installa per l'utente corrente (~/.local), senza privilegi
#        sudo ./install.sh --system   installa per tutti gli utenti (/opt/pdfdesk, /usr/local/bin, /usr/share)
#        ./install.sh --help
# Per AGGIORNARE basta lanciare di nuovo lo script del pacchetto nuovo: la versione precedente viene sostituita.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MODE=user
for a in "$@"; do
  case "$a" in
    --system) MODE=system ;;
    -h|--help) sed -n 3,7p "$0"; exit 0 ;;
    *) echo "Opzione sconosciuta: $a (vedi --help)"; exit 2 ;;
  esac
done
[ -x "$HERE/pdfdesk" ] || { echo "Errore: «pdfdesk» non trovato accanto a install.sh"; exit 1; }
if [ "$MODE" = system ]; then
  [ "$(id -u)" = 0 ] || { echo "Per l'installazione di sistema serve root: sudo ./install.sh --system"; exit 1; }
  APPDIR=/opt/pdfdesk; BINDIR=/usr/local/bin; SHARE=/usr/share
else
  APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/pdfdesk"; BINDIR="$HOME/.local/bin"; SHARE="${XDG_DATA_HOME:-$HOME/.local/share}"
fi
NEW=$("$HERE/pdfdesk" --version 2>/dev/null | sed -n 's/.*versione \([0-9][^ ]*\).*/\1/p' | head -1)
OLD=""
[ -x "$APPDIR/pdfdesk" ] && OLD=$("$APPDIR/pdfdesk" --version 2>/dev/null | sed -n 's/.*versione \([0-9][^ ]*\).*/\1/p' | head -1) || true
if [ -n "$OLD" ]; then echo "Aggiornamento di PDFDesk dalla versione $OLD alla ${NEW:-nuova}…"; else echo "Installazione di PDFDesk ${NEW:-}…"; fi

mkdir -p "$APPDIR" "$BINDIR" "$SHARE/applications" "$SHARE/icons/hicolor/scalable/apps"
# l'eseguibile si sostituisce in modo atomico (funziona anche se il programma è aperto)
install -m 755 "$HERE/pdfdesk" "$APPDIR/pdfdesk.new" && mv -f "$APPDIR/pdfdesk.new" "$APPDIR/pdfdesk"
for f in LICENSE README.md THIRD_PARTY.md; do [ -f "$HERE/$f" ] && install -m 644 "$HERE/$f" "$APPDIR/$f"; done
install -m 755 "$HERE/uninstall.sh" "$APPDIR/uninstall.sh"
ln -sf "$APPDIR/pdfdesk" "$BINDIR/pdfdesk"
for s in 16 32 48 64 128 256 512; do
  if [ -f "$HERE/icons/pdfdesk-$s.png" ]; then
    mkdir -p "$SHARE/icons/hicolor/${s}x${s}/apps"; install -m 644 "$HERE/icons/pdfdesk-$s.png" "$SHARE/icons/hicolor/${s}x${s}/apps/pdfdesk.png"
  fi
done
[ -f "$HERE/icons/pdfdesk.svg" ] && install -m 644 "$HERE/icons/pdfdesk.svg" "$SHARE/icons/hicolor/scalable/apps/pdfdesk.svg"
# voce del menu: il modello pdfdesk.desktop.in diventa pdfdesk.desktop con il percorso reale del programma.
# In Exec il percorso va tra virgolette (può contenere spazi) con \ " ` $ protetti; TryExec vuole il percorso così com'è.
TEMPLATE="$HERE/pdfdesk.desktop.in"
[ -f "$TEMPLATE" ] || TEMPLATE="$HERE/pdfdesk.desktop"          # pacchetti fino alla 0.7.16
EXE="$APPDIR/pdfdesk"
# 1) tra virgolette: \ " ` $ preceduti da «\»;  2) le stringhe del file .desktop raddoppiano a loro volta ogni «\»
Q=$(printf '%s' "$EXE" | sed -e 's/[\\"`$]/\\&/g' -e 's/\\/\\\\/g')
DESKTOP="$SHARE/applications/pdfdesk.desktop"
TMPD="$DESKTOP.tmp"
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in                        # printf inserisce i percorsi alla lettera (nessuna sostituzione di bash o sed)
    Exec=*)    printf 'Exec="%s" %%F\n' "$Q" ;;
    TryExec=*) printf 'TryExec=%s\n' "$(printf '%s' "$EXE" | sed 's/\\/\\\\/g')" ;;
    *)         printf '%s\n' "$line" ;;
  esac
done < "$TEMPLATE" > "$TMPD"
if grep -q '@EXEC' "$TMPD"; then rm -f "$TMPD"; echo "Errore: voce del menu non generata correttamente"; exit 1; fi
chmod 644 "$TMPD" && mv -f "$TMPD" "$DESKTOP"
command -v desktop-file-validate >/dev/null && { desktop-file-validate "$DESKTOP" || echo "Avviso: desktop-file-validate segnala problemi in $DESKTOP"; }
command -v update-desktop-database >/dev/null && update-desktop-database "$SHARE/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f "$SHARE/icons/hicolor" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
echo "Fatto. PDFDesk è in $APPDIR; lancialo dal menu delle applicazioni o con il comando «pdfdesk»."
case ":$PATH:" in *":$BINDIR:"*) ;; *) echo "Nota: $BINDIR non è nel PATH; usa il menu delle applicazioni o aggiungilo al PATH." ;; esac
echo "Per disinstallare: $APPDIR/uninstall.sh"
