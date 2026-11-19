# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Unione in batch di più PDF (e immagini) in un unico PDF, con ordine scelto, intervalli di pagine e segnalibri.
from __future__ import annotations

import os
from typing import Callable, Optional

import pymupdf as fitz

from .export import parse_pages
from .i18n import tr

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
    # dai byte, non dal file: se l'uscita coincide con un sorgente, su Windows il file aperto non si potrebbe sovrascrivere
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lstrip(".").lower() or "pdf"
    try:
        d = fitz.open(stream=data, filetype=ext)
    except Exception:
        d = fitz.open(stream=data)
    if d.is_pdf:
        if d.needs_pass and not d.authenticate(password or ""):
            raise MergeError(tr("{}: password mancante o errata").format(os.path.basename(path)))
        return d
    # immagine → PDF di una pagina (dimensione secondo la risoluzione dichiarata, 72 dpi se assente)
    pdf = fitz.open("pdf", d.convert_to_pdf())
    d.close()
    return pdf


def _fix_levels(toc: list) -> list:
    """Livelli coerenti dopo aver tolto i segnalibri delle pagine escluse: ogni voce al più un livello sotto la precedente
    (set_toc rifiuta i salti), e la prima voce al livello 1."""
    out, prev = [], 0
    for lvl, ttl, pg in toc:
        lvl = max(1, min(lvl, prev + 1))
        out.append([lvl, ttl, pg]); prev = lvl
    return out


def merge_pdfs(items: list[dict], out_path: str, bookmarks: bool = True,
               progress: Optional[Callable[[int, int], bool]] = None, title: str = "") -> int:
    """Unisce `items` nell'ordine dato.

    Ogni voce: {"path": str, "pages": "1-3,5" (vuoto = tutte), "password": str}.
    `bookmarks`: aggiunge un segnalibro per ogni file sorgente, con sotto i segnalibri originali del file; senza, i
    segnalibri originali restano al loro livello. In entrambi i casi puntano alle pagine giuste del documento unito
    (quelli di pagine non incluse vengono tolti). Restituisce il numero di pagine scritte.
    """
    if not items:
        raise MergeError(tr("Nessun file da unire"))
    out = fitz.open()
    toc, n = [], len(items)
    try:
        for i, it in enumerate(items):
            if progress and progress(i, n) is False:
                raise MergeError(tr("Operazione annullata"))
            src = _open_source(it["path"], it.get("password", ""))
            try:
                try:
                    pages = parse_pages(it.get("pages", "") or "", src.page_count)
                except ValueError as e:
                    raise MergeError(f"{os.path.basename(it['path'])}: {e}") from e
                if not pages:
                    continue
                start = out.page_count
                # pagine consecutive in un'unica copia; final=False mantiene la tabella degli oggetti già copiati da questo
                # file, così font e immagini condivisi tra le pagine si copiano una volta sola (prima: una copia per pagina,
                # con file uniti molto più grandi degli originali)
                runs = []
                for p in pages:
                    if runs and p == runs[-1][1] + 1:
                        runs[-1][1] = p
                    else:
                        runs.append([p, p])
                for k, (p0, p1) in enumerate(runs):
                    out.insert_pdf(src, from_page=p0, to_page=p1, final=(k == len(runs) - 1))
                # segnalibri originali del file: riportati sulle pagine nuove (solo quelli delle pagine incluse)
                newpage = {p: start + k for k, p in enumerate(pages)}             # pagina sorgente (0) -> pagina unita (0)
                own = []
                try:
                    src_toc = src.get_toc(simple=True)
                except Exception:
                    src_toc = []
                for i, (lvl, ttl, pg) in enumerate(src_toc):
                    if (pg - 1) in newpage:
                        own.append([lvl, ttl, newpage[pg - 1] + 1])
                        continue
                    # pagina esclusa: il segnalibro resta se qualcuno dei suoi sotto-segnalibri è incluso, e punta al primo
                    for lvl2, _, pg2 in src_toc[i + 1:]:
                        if lvl2 <= lvl:
                            break
                        if (pg2 - 1) in newpage:
                            own.append([lvl, ttl, newpage[pg2 - 1] + 1])
                            break
                own = _fix_levels(own)
                if bookmarks:
                    # un segnalibro per il file, con sotto quelli originali del file
                    toc.append([1, os.path.splitext(os.path.basename(it["path"]))[0], start + 1])
                    toc += [[lvl + 1, ttl, pg] for lvl, ttl, pg in own]
                else:
                    toc += own
            finally:
                src.close()
        if out.page_count == 0:
            raise MergeError(tr("Nessuna pagina da unire"))
        if toc:
            out.set_toc(toc)
        if title:
            out.set_metadata({"title": title})
        # garbage=4: unisce anche i flussi identici (stesso font o immagine presenti in più file sorgente)
        out.save(out_path, garbage=4, deflate=True)
        if progress:
            progress(n, n)
        return out.page_count
    finally:
        out.close()
