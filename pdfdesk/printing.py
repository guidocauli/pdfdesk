# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# printing.py: stampa delle pagine (anche su file PDF) tramite QPrinter.
from __future__ import annotations

from typing import Callable, Optional

import pymupdf as fitz
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPainter, QPageSize
from PySide6.QtPrintSupport import QPrinter


def print_pages(doc: fitz.Document, printer: QPrinter, pages: list[int], progress: Optional[Callable[[int, int], bool]] = None,
                max_dpi: int = 300) -> bool:
    """Stampa le pagine indicate (indici da 0), adattandole al foglio e orientandolo come la pagina.
    Restituisce False se annullata."""
    if not pages:
        return True
    dpi = max(72, min(int(printer.resolution() or 300), max_dpi))
    painter = QPainter()
    first = True
    n = len(pages)
    for k, p in enumerate(pages):
        if progress and progress(k, n) is False:
            if not first:
                painter.end()
            return False
        page = doc[p]
        r = page.rect
        orient = QPageLayout.Landscape if r.width > r.height else QPageLayout.Portrait
        if first:
            printer.setPageOrientation(orient)
            if not painter.begin(printer):
                raise RuntimeError("Impossibile avviare la stampa")
            first = False
        else:
            printer.setPageOrientation(orient)
            printer.newPage()
        z = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        target = painter.viewport()
        w, h = target.width(), target.height()
        s = min(w / img.width(), h / img.height())
        tw, th = img.width() * s, img.height() * s
        painter.drawImage(QRectF((w - tw) / 2, (h - th) / 2, tw, th), img)
    if not first:
        painter.end()
    if progress:
        progress(n, n)
    return True
