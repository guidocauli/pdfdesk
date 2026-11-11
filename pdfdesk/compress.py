# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# compress.py: salvataggio a qualità/compressione diverse. Il testo resta sempre testo (mai rasterizzato).
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import pymupdf as fitz


@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    description: str
    dpi_threshold: Optional[int]   # ricomprime solo immagini sopra questa risoluzione
    dpi_target: int                # risoluzione di arrivo
    quality: int                   # qualità JPEG (1-100)


PRESETS: list[Preset] = [
    Preset("original", "Originale (nessuna ricompressione delle immagini)",
           "Nessuna perdita: solo ottimizzazione della struttura del file.", None, 0, 0),
    Preset("high", "Alta qualità (stampa)",
           "Immagini a 300 dpi, JPEG 90. Differenza quasi invisibile.", 400, 300, 90),
    Preset("medium", "Media (e-mail, schermo)",
           "Immagini a 150 dpi, JPEG 75. Buon compromesso.", 200, 150, 75),
    Preset("low", "Bassa (condivisione veloce)",
           "Immagini a 96 dpi, JPEG 55. File piccoli.", 130, 96, 55),
    Preset("minimum", "Minima (archivio/anteprima)",
           "Immagini a 72 dpi, JPEG 35. Dimensione minima.", 90, 72, 35),
]
PRESET_BY_KEY = {p.key: p for p in PRESETS}


CUSTOM = Preset("custom", "Personalizzata…", "Scegli tu ogni parametro di compressione.", 200, 150, 75)
PRESETS_UI: list[Preset] = PRESETS + [CUSTOM]


@dataclass
class SaveOptions:
    preset: str = "original"
    grayscale: bool = False          # converte le immagini in scala di grigi
    strip_metadata: bool = False     # rimuove metadati e XMP
    subset_fonts: bool = False       # riduce i font incorporati ai soli caratteri usati (il testo resta testo)
    standard: Optional[str] = None   # chiave di pdfstd.STANDARDS (es. "pdfa-2b"): conversione finale
    icc: Optional[str] = None        # profilo ICC di destinazione (PDF/X: profilo di stampa CMYK)
    runner: Any = None               # esecutore per la parte lunga della conversione (thread dell'interfaccia)
    # --- parametri della compressione «personalizzata» (preset == "custom"; per gli altri preset valgono quelli del preset)
    dpi_threshold: Optional[int] = None   # ricampiona solo immagini sopra questa risoluzione (None = nessun ricampionamento)
    dpi_target: int = 150
    quality: int = 75                     # qualità JPEG
    lossy: bool = True                    # ricomprime con perdita (JPEG)
    lossless: bool = True                 # ricomprime senza perdita (Flate)
    kinds: tuple = (True, True, True)     # tipi di immagine trattati: colore, grigio, bianco/nero (1 bit)
    # --- struttura e pulizia (valgono per ogni preset)
    garbage: Optional[int] = None         # 0-4 (None = automatico: 1 per «Originale», 4 per gli altri)
    clean_streams: bool = False           # normalizza i flussi di contenuto delle pagine
    objstms: Optional[bool] = None        # flussi di oggetti compressi (None = automatico)
    drop_thumbnails: bool = False
    drop_attachments: bool = False
    drop_javascript: bool = False
    linearize: bool = False               # «Fast web view»


def resolve(opts: SaveOptions) -> tuple[Optional[int], int, int]:
    """(soglia dpi, dpi di arrivo, qualità) effettivi: del preset, o i valori scelti per «custom»."""
    if opts.preset == "custom":
        return opts.dpi_threshold, opts.dpi_target, opts.quality
    p = PRESET_BY_KEY[opts.preset]
    return p.dpi_threshold, p.dpi_target, p.quality


def optimize_bytes(data: bytes, opts: Optional[SaveOptions] = None) -> bytes:
    """Riscrive il PDF con le opzioni date. Testo, vettoriali e campi restano intatti."""
    opts = opts or SaveOptions()
    thr, target, quality = resolve(opts)
    doc = fitz.open("pdf", data)
    try:
        if thr is not None or opts.grayscale:
            doc.rewrite_images(dpi_threshold=thr, dpi_target=target, quality=quality, lossy=opts.lossy, lossless=opts.lossless,
                               color=opts.kinds[0], gray=opts.kinds[1], bitonal=opts.kinds[2], set_to_gray=opts.grayscale)
        if opts.subset_fonts:
            try:
                doc.subset_fonts()
            except Exception:
                pass
        if opts.strip_metadata:
            doc.set_metadata({})
            try:
                doc.del_xml_metadata()
            except Exception:
                pass
        if opts.drop_thumbnails or opts.drop_attachments or opts.drop_javascript:
            doc.scrub(attached_files=opts.drop_attachments, embedded_files=opts.drop_attachments, clean_pages=False,
                      hidden_text=False, javascript=opts.drop_javascript, metadata=False, redactions=False, remove_links=False,
                      reset_fields=False, reset_responses=False, thumbnails=opts.drop_thumbnails, xml_metadata=False)
        conservative = opts.preset == "original" and not opts.strip_metadata and not opts.subset_fonts
        title = (doc.metadata or {}).get("title") or ""
        garbage = opts.garbage if opts.garbage is not None else (1 if conservative else 4)
        objstm = opts.objstms if opts.objstms is not None else (not conservative)
        out = doc.tobytes(garbage=garbage, clean=opts.clean_streams, deflate=True, deflate_images=not conservative,
                          deflate_fonts=True, use_objstms=1 if objstm else 0,
                          compression_effort=0 if conservative else 100)
    finally:
        doc.close()
    if opts.linearize and not opts.standard:
        out = _linearize(out)
    if opts.standard:                                         # ultimo passo: la conversione riscrive il file
        from . import pdfstd
        out = pdfstd.convert(out, opts.standard, opts.icc, title=title, runner=opts.runner)
    return out


def _linearize(data: bytes) -> bytes:
    import io
    import pikepdf
    with pikepdf.open(io.BytesIO(data)) as pdf:
        buf = io.BytesIO()
        pdf.save(buf, linearize=True)
        return buf.getvalue()


# ---------------------------------------------------------------------- analisi del contenuto
def analyze(data: bytes, top: int = 8) -> dict:
    """Ripartizione delle dimensioni per tipo di contenuto e immagini più pesanti (con risoluzione effettiva)."""
    doc = fitz.open("pdf", data)
    try:
        cat = {"images": 0, "fonts": 0, "content": 0, "attachments": 0, "metadata": 0, "other": 0}
        counts = dict.fromkeys(cat, 0)
        imgs = []
        page_streams: set[int] = set()
        for pg in doc:
            for x in pg.get_contents():
                page_streams.add(x)
        for x in range(1, doc.xref_length()):
            try:
                if not doc.xref_is_stream(x):
                    continue
                n = len(doc.xref_stream_raw(x) or b"")
                obj = doc.xref_object(x, compressed=True)
            except Exception:
                continue
            if "/Subtype/Image" in obj.replace(" ", "") or "/Subtype /Image" in obj:
                k = "images"
            elif "/Length1" in obj or "/FontFile" in obj or "/Subtype/Type1C" in obj.replace(" ", "") or "/CIDFontType0C" in obj \
                    or "/OpenType" in obj:
                k = "fonts"
            elif x in page_streams or "/Subtype/Form" in obj.replace(" ", ""):
                k = "content"
            elif "/EmbeddedFile" in obj:
                k = "attachments"
            elif "/Type/Metadata" in obj.replace(" ", ""):
                k = "metadata"
            else:
                k = "other"
            cat[k] += n; counts[k] += 1
        seen = set()
        for pno, pg in enumerate(doc):
            for im in pg.get_images(full=True):
                xref = im[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    raw = len(doc.xref_stream_raw(xref) or b"")
                    rects = pg.get_image_rects(xref)
                    dpi = int(im[2] / (rects[0].width / 72)) if rects and rects[0].width > 0 else 0
                except Exception:
                    raw, dpi = 0, 0
                imgs.append({"page": pno + 1, "xref": xref, "w": im[2], "h": im[3], "bytes": raw, "dpi": dpi,
                             "filter": im[8] if len(im) > 8 else ""})
        imgs.sort(key=lambda i: -i["bytes"])
        return {"total": len(data), "categories": cat, "counts": counts, "images": imgs[:top], "image_count": len(imgs)}
    finally:
        doc.close()


def format_analysis(a: dict) -> str:
    lab = {"images": "Immagini", "fonts": "Font incorporati", "content": "Contenuto delle pagine", "attachments": "Allegati",
           "metadata": "Metadati XMP", "other": "Altri flussi"}
    tot = a["total"] or 1
    lines = [f"Dimensione del file: {human_size(a['total'])}"]
    for k, v in sorted(a["categories"].items(), key=lambda kv: -kv[1]):
        if v:
            lines.append(f"  {lab[k]}: {human_size(v)} ({v * 100 / tot:.0f}%, {a['counts'][k]} oggetti)")
    if a["images"]:
        lines.append(f"Immagini più pesanti ({a['image_count']} in totale):")
        for i in a["images"]:
            lines.append(f"  pag. {i['page']}: {i['w']}×{i['h']} px, {human_size(i['bytes'])}" + (f", ~{i['dpi']} dpi" if i["dpi"] else ""))
    return "\n".join(lines)


def write_atomic(path: str, data: bytes) -> None:
    tmp = path + ".pdfdesk-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"
