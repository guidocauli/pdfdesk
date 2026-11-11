# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Unione in batch di più PDF (e immagini) in un unico PDF, con ordine scelto, intervalli di pagine e segnalibri.
from __future__ import annotations

import os
from typing import Callable, Optional

import pymupdf as fitz

from .export import parse_pages

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")


class MergeError(Exception):
    pass


def probe(path: str, password: str = "") -> dict:
    """Informazioni su un sorgente: pagine, dimensione, se richiede password. Solleva MergeError se illeggibile."""
    try:
        d = fitz.open(path)
    except Exception as e:
        raise MergeError(f"{os.path.basename(path)}: {e}") from e
    try:
        if d.needs_pass and not d.authenticate(password):
            return {"pages": 0, "locked": True, "size": os.path.getsize(path)}
        return {"pages": d.page_count, "locked": False, "size": os.path.getsize(path)}
    finally:
        d.close()


def _open_source(path: str, password: str) -> fitz.Document:
    d = fitz.open(path)
    if d.is_pdf:
        if d.needs_pass and not d.authenticate(password or ""):
            raise MergeError(f"{os.path.basename(path)}: password mancante o errata")
        return d
    # immagine → PDF di una pagina (dimensione secondo la risoluzione dichiarata, 72 dpi se assente)
    pdf = fitz.open("pdf", d.convert_to_pdf())
    d.close()
    return pdf


def merge_pdfs(items: list[dict], out_path: str, bookmarks: bool = True,
               progress: Optional[Callable[[int, int], bool]] = None, title: str = "") -> int:
    """Unisce `items` nell'ordine dato.

    Ogni voce: {"path": str, "pages": "1-3,5" (vuoto = tutte), "password": str}.
    `bookmarks`: aggiunge un segnalibro per ogni file sorgente. Restituisce il numero di pagine scritte.
    """
    if not items:
        raise MergeError("Nessun file da unire")
    out = fitz.open()
    toc, n = [], len(items)
    try:
        for i, it in enumerate(items):
            if progress and progress(i, n) is False:
                raise MergeError("Operazione annullata")
            src = _open_source(it["path"], it.get("password", ""))
            try:
                try:
                    pages = parse_pages(it.get("pages", "") or "", src.page_count)
                except ValueError as e:
                    raise MergeError(f"{os.path.basename(it['path'])}: {e}") from e
                if not pages:
                    continue
                start = out.page_count
                for p in pages:
                    out.insert_pdf(src, from_page=p, to_page=p)
                toc.append([1, os.path.splitext(os.path.basename(it["path"]))[0], start + 1])
            finally:
                src.close()
        if out.page_count == 0:
            raise MergeError("Nessuna pagina da unire")
        if bookmarks and toc:
            out.set_toc(toc)
        if title:
            out.set_metadata({"title": title})
        out.save(out_path, garbage=3, deflate=True)
        if progress:
            progress(n, n)
        return out.page_count
    finally:
        out.close()
