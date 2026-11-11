# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# imgutil.py: gestione uniforme dei pixmap con canale alfa (trasparenza), maschere morbide e spazi colore diversi da RGB.
from __future__ import annotations

import io

import pymupdf as fitz


def _to_rgb_or_gray(pix: fitz.Pixmap) -> fitz.Pixmap:
    """Senza alfa e in RGB o grigio (CMYK, Lab, DeviceN… → RGB). Un pixmap con alfa viene prima privato dell'alfa."""
    if pix.alpha:
        pix = fitz.Pixmap(pix, 0)
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix


def split_alpha(pix: fitz.Pixmap):
    """(colore senza alfa, maschera grigia 8 bit o None) di un pixmap qualsiasi."""
    mask = None
    if pix.alpha:
        # estrae il canale alfa: ogni n-esimo byte
        n = pix.n
        a = bytes(pix.samples[n - 1::n]) if pix.stride == pix.width * n else b"".join(
            bytes(pix.samples[r * pix.stride + n - 1:(r + 1) * pix.stride:n][:pix.width]) for r in range(pix.height))
        mask = fitz.Pixmap(fitz.csGRAY, pix.width, pix.height, a, 0)
    return _to_rgb_or_gray(pix), mask


def with_mask(color: fitz.Pixmap, mask: fitz.Pixmap) -> fitz.Pixmap:
    """Pixmap RGBA da colore + maschera, portandoli alla stessa dimensione."""
    color = _to_rgb_or_gray(color)
    if mask.alpha:
        mask = fitz.Pixmap(mask, 0)
    if mask.colorspace is None or mask.colorspace.n != 1:
        mask = fitz.Pixmap(fitz.csGRAY, mask)
    if (mask.width, mask.height) != (color.width, color.height):
        if mask.width * mask.height > color.width * color.height:
            color = fitz.Pixmap(color, mask.width, mask.height, None)
        else:
            mask = fitz.Pixmap(mask, color.width, color.height, None)
    return fitz.Pixmap(color, mask)


def image_pixmap(doc: fitz.Document, xref: int) -> fitz.Pixmap:
    """Pixmap dell'immagine incorporata con TUTTA la sua trasparenza: maschera morbida (/SMask), alfa proprio
    (JPX, /SMaskInData) o nessuna. Sempre RGB/grigio (+ alfa), mai con colorspace esotici; mai errori di alfa doppio."""
    base = fitz.Pixmap(doc, xref)
    own_alpha = base.alpha
    smask = None
    try:
        k = doc.xref_get_key(xref, "SMask")
        if k[0] == "xref":
            smask = fitz.Pixmap(doc, int(k[1].split()[0]))
    except Exception:
        smask = None
    if smask is not None:
        try:
            return with_mask(base, smask)
        except Exception:
            pass
    if own_alpha:
        try:
            col, mask = split_alpha(base)
            return with_mask(col, mask) if mask is not None else col
        except Exception:
            return base
    return _to_rgb_or_gray(base)


def to_png_bytes(src) -> bytes:
    """Qualsiasi immagine (percorso, byte o file) → PNG, conservando la trasparenza (PNG/GIF/WEBP/TIFF con alfa, tavolozza con
    colore trasparente). CMYK → RGB; 16 bit → 8 bit."""
    from PIL import Image
    im = Image.open(src if not isinstance(src, (bytes, bytearray)) else io.BytesIO(src))
    try:
        im.load()
        if im.mode == "P":
            im = im.convert("RGBA" if "transparency" in im.info else "RGB")
        elif im.mode in ("LA", "PA", "La", "RGBa"):
            im = im.convert("RGBA")
        elif im.mode == "CMYK":
            im = im.convert("RGB")
        elif im.mode.startswith("I;16") or im.mode in ("I", "F"):
            im = im.point(lambda v: v / 256).convert("L") if im.mode == "I" else im.convert("L")
        elif im.mode not in ("1", "L", "RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.mode else "RGB")
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()
    finally:
        im.close()
