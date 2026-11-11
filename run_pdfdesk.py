# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Punto d'ingresso per PyInstaller e per l'avvio da sorgente.
import multiprocessing
import sys

from pdfdesk.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()          # eseguibile PyInstaller: i processi di calcolo (spawn) ripartono da qui
    sys.exit(main())
