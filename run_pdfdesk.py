# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Punto d'ingresso per PyInstaller e per l'avvio da sorgente.
import sys

from pdfdesk.cli import main

if __name__ == "__main__":
    sys.exit(main())
