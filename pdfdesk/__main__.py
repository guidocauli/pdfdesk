# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
import sys

from .cli import main

if __name__ == "__main__":            # i processi di calcolo (spawn) reimportano questo modulo: non devono avviare il programma
    sys.exit(main())
