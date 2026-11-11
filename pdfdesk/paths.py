# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# paths.py: cartelle dati dell'utente (firme, font) senza dipendere da Qt.
from __future__ import annotations

import os
import sys


def data_dir(sub: str = "") -> str:
    base = os.environ.get("PDFDESK_DATA")
    if not base:
        if sys.platform == "win32":
            base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "PDFDesk")
        elif sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/PDFDesk")
        else:
            base = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "PDFDesk")
    d = os.path.join(base, sub) if sub else base
    os.makedirs(d, exist_ok=True)
    return d
