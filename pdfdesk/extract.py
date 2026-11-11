# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# extract.py: estrazione delle immagini incorporate e di aree della pagina (JPG, TIFF, PNG).
from __future__ import annotations

import os
from typing import Callable, Optional

import pymupdf as fitz

from . import imgutil

FORMATS = {"png": ("PNG", ".png"), "jpg": ("JPG", ".jpg"), "tiff": ("TIFF", ".tiff")}


def image_pixmap(doc: fitz.Document, xref: int) -> fitz.Pixmap:
    """Pixmap dell'immagine incorporata con la sua trasparenza; CMYK/altri spazi → RGB."""
    return imgutil.image_pixmap(doc, xref)


def write_pixmap(pix: fitz.Pixmap, path: str, fmt: str, quality: int = 90, dpi: Optional[int] = None,
                 tiff_compression: str = "tiff_lzw") -> str:
    """Scrive il pixmap come PNG, JPG o TIFF. JPG non ha trasparenza: viene composta su bianco."""
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"Formato non supportato: {fmt}")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if pix.colorspace is not None and pix.colorspace.n not in (1, 3):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    if dpi:
        pix.set_dpi(dpi, dpi)
    if fmt == "png":
        pix.save(path)
        return path
    from PIL import Image
    mode = {(1, 0): "L", (1, 1): "LA", (3, 0): "RGB", (3, 1): "RGBA"}[(pix.n - pix.alpha, pix.alpha)]
    im = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    if fmt == "jpg":
        if "A" in mode:
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
            im = bg
        im.save(path, "JPEG", quality=int(quality), dpi=(dpi, dpi) if dpi else (72, 72), optimize=True)
    else:
        if mode == "LA":
            im = im.convert("RGBA")
        im.save(path, "TIFF", compression=tiff_compression, dpi=(dpi, dpi) if dpi else (72, 72))
    return path


def list_images(doc: fitz.Document, pages: Optional[list[int]] = None) -> list[dict]:
    """Immagini incorporate (una voce per immagine e pagina in cui compare, senza ripetizioni)."""
    out, seen = [], set()
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        for im in page.get_images(full=True):
            xref = im[0]
            if (pno, xref) in seen:
                continue
            seen.add((pno, xref))
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                rects = []
            r = rects[0] if rects else None
            dpi = int(im[2] / (r.width / 72)) if r is not None and r.width > 0 else 0
            try:
                size = len(doc.xref_stream_raw(xref) or b"")
            except Exception:
                size = 0
            out.append({"page": pno, "xref": xref, "w": im[2], "h": im[3], "bpc": im[4], "cs": im[5], "dpi": dpi,
                        "bytes": size, "rect": tuple(r) if r is not None else None, "mask": bool(im[1])})
    return out


def extract_images(doc: fitz.Document, items: list[dict], fmt: str, folder: str, quality: int = 90,
                   progress: Optional[Callable[[int, int], bool]] = None) -> list[str]:
    """Salva le immagini indicate in `folder`: «pagN_imgM.ext» (M = numero d'ordine nella pagina)."""
    os.makedirs(folder, exist_ok=True)
    ext = FORMATS[fmt][1]
    written, per_page = [], {}
    for i, it in enumerate(items):
        if progress and progress(i, len(items)) is False:
            break
        per_page[it["page"]] = per_page.get(it["page"], 0) + 1
        path = os.path.join(folder, f"pag{it['page'] + 1:03d}_img{per_page[it['page']]:02d}{ext}")
        write_pixmap(image_pixmap(doc, it["xref"]), path, fmt, quality, it["dpi"] or None)
        written.append(path)
    if progress:
        progress(len(items), len(items))
    return written


def render_area(doc: fitz.Document, pno: int, rect, dpi: int = 200, annots: bool = True) -> fitz.Pixmap:
    """Area della pagina (`rect` in coordinate di visualizzazione) resa a `dpi`: testo, grafica e immagini insieme."""
    page = doc[pno]
    r = fitz.Rect(rect) & page.rect
    if r.is_empty:
        raise ValueError("Area fuori dalla pagina")
    z = dpi / 72.0
    return page.get_pixmap(matrix=fitz.Matrix(z, z), clip=r, alpha=False, annots=annots)
