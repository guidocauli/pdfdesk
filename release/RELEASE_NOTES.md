# PDFDesk — Guido Cauli <guido.cauli@gmail.com> — 0.7.19

## Novità
- **OCR sui PDF esistenti**: *File → Rendi ricercabile (OCR)…* (Ctrl+Maiusc+O) o l'attività *Rendi ricercabile (OCR)*.
  - Il documento aperto e/o altri PDF, anche trascinati nella finestra.
  - Ogni file si salva come nuovo file con un suffisso (predefinito `_ocr`: `relazione.pdf` → `relazione_ocr.pdf`), nella stessa cartella o in una scelta. Gli originali non vengono modificati.
  - Il documento aperto, una volta riconosciuto, si apre in una scheda accanto.
  - Si possono scegliere più lingue insieme e la risoluzione (200, 300, 400 dpi). In modo predefinito si riconoscono solo le pagine senza testo.
  - Il testo riconosciuto è invisibile e appoggiato sulla pagina: l'aspetto non cambia (anche sulle pagine ruotate), ma il testo diventa selezionabile, copiabile e ricercabile.
- **OCR senza installare Tesseract**, su Windows, macOS e Linux. Il motore OCR è già incluso nel programma; servono solo i dati delle lingue.
  - Si scaricano da *Preferenze → Scansione e OCR → Scarica lingue…*: 33 lingue, 1–8 MB ciascuna.
  - I file vanno nella cartella dei dati di PDFDesk, senza privilegi di amministratore, e vengono verificati con SHA-256.
  - Se una rete blocca un indirizzo, si prova automaticamente il successivo.
  - Se nel sistema c'è già Tesseract, PDFDesk ne usa anche le lingue installate.
- **Scansione**: l'OCR usa lo stesso motore integrato. Il pulsante *Lingue OCR…* è disponibile su tutti i sistemi.
- **Installatore Windows**: il componente «OCR» scarica solo le lingue italiano e inglese (circa 7 MB) invece di Tesseract (50 MB).
- **Riga di comando**: `pdfdesk --ocr FILE.pdf… [--ocr-lang ita+eng] [--ocr-suffix _ocr] [--outdir CARTELLA] [--ocr-all] [--dpi 300] [--overwrite]`. Le lingue si scaricano con `pdfdesk --ocr-download ita+eng+deu`.

## File della release
- `pdfdesk-0.7.19-windows-x86_64-setup.exe`, `pdfdesk-0.7.19-windows-x86_64.zip`
- `pdfdesk-0.7.19-linux-x86_64.tar.gz`
- `pdfdesk-0.7.19-macos-arm64.zip` (Apple Silicon; al primo avvio usare `sblocca.sh` incluso nello zip)
- `pdfdesk-0.7.19-sorgenti.tar.gz`
- `SHA256SUMS-0.7.19.txt`
