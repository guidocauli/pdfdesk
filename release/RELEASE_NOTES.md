# PDFDesk — Guido Cauli <guido.cauli@gmail.com> — 0.7.20

## Novità
- **Wayland nativo su Linux.** In una sessione Wayland PDFDesk usa Wayland nativo (finestre nitide con qualsiasi scala). Se Wayland non è disponibile passa da solo a X11 invece di interrompersi. In *Preferenze → Aspetto → Sistema grafico* si può forzare X11 (XWayland).
- La finestra ha l'identificativo `pdfdesk`, uguale alla voce di menu: icona, raggruppamento e regole del compositor funzionano.

## Correzioni
- **Compositor a tasselli (niri, Hyprland, sway, river, i3)**:
  - la finestra principale si stringe fino a circa 300 pixel, prima almeno 850. I pulsanti e i controlli della barra Proprietà che non ci stanno passano nel menu «»» delle barre; le statistiche nella barra di stato si accorciano con «…»;
  - la dimensione della finestra la decide il compositor: quella salvata non viene più imposta né sovrascritta.
- **Dialoghi sempre entro lo schermo**, anche su schermi piccoli; sui compositor a tasselli galleggiano sopra la finestra.
- **Su ogni sistema** la dimensione salvata della finestra si riduce se supera lo schermo su cui si apre (per esempio passando a un monitor più piccolo).
- Fra le librerie richieste su Linux nel README ci sono anche quelle di Wayland.

## File della release
- `pdfdesk-0.7.20-windows-x86_64-setup.exe`, `pdfdesk-0.7.20-windows-x86_64.zip`
- `pdfdesk-0.7.20-linux-x86_64.tar.gz`
- `pdfdesk-0.7.20-macos-arm64.zip` (Apple Silicon; al primo avvio usare `sblocca.sh` incluso nello zip)
- `pdfdesk-0.7.20-sorgenti.tar.gz`
- `SHA256SUMS-0.7.20.txt`
