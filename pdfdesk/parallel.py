# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# parallel.py: lavoro su più core "al bisogno" (fino a n-1 processori) per le operazioni lunghe su documenti con molte pagine.
#
# MuPDF non permette di usare lo stesso documento da più thread, quindi si usano processi separati: il documento corrente è
# scritto una sola volta in un file temporaneo e ogni processo lo riapre in sola lettura e lavora su un gruppo di pagine.
# I processi sono creati con "spawn" (identico su Windows, macOS e Linux, e con gli eseguibili PyInstaller: vedi
# multiprocessing.freeze_support() in cli.main).  Le funzioni dei processi stanno in questo modulo e non importano Qt.
from __future__ import annotations

import os
import shutil
import tempfile
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from typing import Callable, Optional

_CORES = 0            # 0 = automatico (tutti i processori meno uno); altrimenti il massimo scelto dall'utente
MIN_PAGES = 8         # sotto questa soglia l'avvio dei processi costa più del lavoro: si resta su un solo core
MEM_BUDGET = 3_000_000_000   # ogni processo riapre il documento: si limita il numero di processi sui file molto grandi


def set_cores(n: int) -> None:
    global _CORES
    _CORES = max(0, int(n))


def cpu_total() -> int:
    return max(1, os.cpu_count() or 1)


def max_workers() -> int:
    """Processi utilizzabili: PDFDESK_CORES, altrimenti la scelta dell'utente, altrimenti n-1 (almeno 1)."""
    env = os.environ.get("PDFDESK_CORES", "")
    want = int(env) if env.isdigit() and int(env) > 0 else _CORES
    auto = max(1, cpu_total() - 1)
    return max(1, min(want, cpu_total())) if want else auto


def plan(npages: int, size: int = 0, min_pages: int = MIN_PAGES) -> int:
    """Quanti processi usare per `npages` pagine: 1 = lavoro seriale (poche pagine, un solo core, o file enorme)."""
    w = min(max_workers(), npages // 2 if npages >= min_pages else 1)
    if size > 0:
        w = min(w, max(1, MEM_BUDGET // max(size, 1)))
    return max(1, w)


class Cancelled(Exception):
    pass


def _chunks(items: list, n: int) -> list[list]:
    """Divide in 2n gruppi alternati (le pagine pesanti si distribuiscono; i gruppi piccoli bilanciano il carico)."""
    k = min(len(items), max(n * 2, 1))
    return [items[i::k] for i in range(k) if items[i::k]]


def run(data: bytes, func: Callable, items: list, workers: int, args: tuple = (),
        progress: Optional[Callable[[int, int], Optional[bool]]] = None) -> list:
    """Esegue `func(path, gruppo, *args)` in `workers` processi; `data` è il PDF corrente.  `func` deve essere una funzione di
    questo modulo.  `progress(fatte, totali)` può restituire False per annullare.  Restituisce i risultati dei gruppi."""
    import multiprocessing as mp
    tmpdir = tempfile.mkdtemp(prefix="pdfdesk-par-")
    path = os.path.join(tmpdir, "doc.pdf")
    results: list = []
    ex = None
    try:
        with open(path, "wb") as f:
            f.write(data)
        total = len(items)
        done = 0
        if progress and progress(0, total) is False:
            raise Cancelled()
        ex = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"))
        pending = {ex.submit(func, path, ch, *args): len(ch) for ch in _chunks(items, workers)}
        while pending:
            fin, _ = wait(list(pending), timeout=0.1, return_when=FIRST_COMPLETED)
            for fu in fin:
                done += pending.pop(fu)
                results.append(fu.result())
            if progress and progress(done, total) is False:
                raise Cancelled()
        return results
    except BaseException:
        if ex is not None:
            ex.shutdown(wait=False, cancel_futures=True)
            for p in list(getattr(ex, "_processes", {}).values()):      # annullamento/errore: ferma subito i processi
                try:
                    p.terminate()
                except Exception:
                    pass
            ex = None
        raise
    finally:
        if ex is not None:
            ex.shutdown(wait=True)
        shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================ funzioni dei processi (solo PyMuPDF, niente Qt)
def w_export_images(path: str, pages: list[int], fmt: str, dpi: int, quality: int, target: str, base: str,
                    tiff_compression: str = "tiff_lzw") -> list[str]:
    import pymupdf as fitz
    doc = fitz.open(path)
    zoom = dpi / 72.0
    out = []
    try:
        for p in pages:
            pix = doc[p].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pix.set_dpi(dpi, dpi)
            if fmt == "png":
                fn = os.path.join(target, f"{base}_p{p + 1:03d}.png"); pix.save(fn)
            elif fmt == "jpg":
                fn = os.path.join(target, f"{base}_p{p + 1:03d}.jpg"); pix.save(fn, jpg_quality=int(quality))
            else:
                from PIL import Image
                fn = os.path.join(target, f"{base}_p{p + 1:03d}.tiff")
                Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(fn, compression=tiff_compression, dpi=(dpi, dpi))
            out.append(fn)
    finally:
        doc.close()
    return out


def w_search(path: str, pages: list[int], needle: str) -> list[tuple[int, list[tuple[float, float, float, float]]]]:
    import pymupdf as fitz
    doc = fitz.open(path)
    out = []
    try:
        for p in pages:
            rs = doc[p].search_for(needle)
            if rs:
                out.append((p, [(r.x0, r.y0, r.x1, r.y1) for r in rs]))
    finally:
        doc.close()
    return out


def w_text(path: str, pages: list[int], keep_layout: bool) -> list[tuple[int, str]]:
    import pymupdf as fitz
    doc = fitz.open(path)
    out = []
    try:
        for p in pages:
            if keep_layout:
                from .export_fixed import layout_text
                out.append((p, layout_text(doc[p]).rstrip("\n")))
            else:
                out.append((p, doc[p].get_text("text", sort=True).rstrip()))
    finally:
        doc.close()
    return out
