# PDFDesk — Guido Cauli
# docstats.py: statistiche del documento per la barra di stato (dimensione, parole, caratteri, immagini, font…).
# Il conteggio del testo procede a blocchi di pagine (iter_text_stats), così l'interfaccia resta reattiva anche con
# documenti molto lunghi.
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterator, Optional

import pymupdf as fitz

# formati di pagina riconosciuti (mm, verticale); tolleranza ±2 mm
PAPER = {"A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
         "A6": (105, 148), "B4": (250, 353), "B5": (176, 250), "Letter": (216, 279), "Legal": (216, 356),
         "Tabloid": (279, 432)}


@dataclass
class TextStats:
    pages_done: int = 0
    pages: int = 0
    words: int = 0
    chars: int = 0             # spazi inclusi (gli a capo non contano)
    chars_nospace: int = 0
    lines: int = 0
    images: set = field(default_factory=set)   # xref delle immagini (ognuna contata una volta)
    text_pages: int = 0        # pagine con testo (le altre sono probabilmente scansioni)

    @property
    def done(self) -> bool:
        return self.pages_done >= self.pages


def page_format(page: fitz.Page) -> str:
    """«A4 verticale», «Letter orizzontale» o le misure in mm."""
    r = page.rect
    w, h = r.width * 25.4 / 72, r.height * 25.4 / 72
    a, b = sorted((w, h))
    orient = "orizzontale" if w > h + 1 else "verticale"
    for name, (pw, ph) in PAPER.items():
        if abs(a - pw) <= 2 and abs(b - ph) <= 2:
            return f"{name} {orient}"
    return f"{w:.0f} × {h:.0f} mm"


def iter_text_stats(doc: fitz.Document, chunk: int = 8) -> Iterator[TextStats]:
    """Restituisce le statistiche parziali ogni `chunk` pagine; l'ultima è completa."""
    st = TextStats(pages=doc.page_count)
    for pno in range(doc.page_count):
        try:
            page = doc[pno]
            words = page.get_text("words")
            text = page.get_text("text")
            st.words += len(words)
            body = text.replace("\n", "")
            st.chars += len(body)
            st.chars_nospace += sum(1 for c in body if not c.isspace())
            st.lines += sum(1 for ln in text.splitlines() if ln.strip())
            if words:
                st.text_pages += 1
            for im in page.get_images(full=True):
                st.images.add(im[0])
        except Exception:
            pass
        st.pages_done = pno + 1
        if st.pages_done % chunk == 0 and not st.done:
            yield st
    yield st


def text_stats(doc: fitz.Document) -> TextStats:
    st = TextStats()
    for st in iter_text_stats(doc, chunk=10 ** 9):
        pass
    return st


def disk_size(path: Optional[str]) -> Optional[int]:
    try:
        return os.path.getsize(path) if path else None
    except OSError:
        return None


def doc_info(doc: fitz.Document) -> dict:
    """Informazioni rapide (senza leggere il testo delle pagine)."""
    out = {"version": "", "encrypted": bool(doc.is_encrypted or (doc.metadata or {}).get("encryption")),
           "fonts_embedded": 0, "fonts_missing": 0}
    try:
        out["version"] = (doc.metadata or {}).get("format", "") or ""
    except Exception:
        pass
    try:
        from .compress import font_inventory
        inv = font_inventory(doc)
        out["fonts_embedded"], out["fonts_missing"] = inv["embedded"], len(inv["missing"])
    except Exception:
        pass
    return out
