"""Esportazione del PDF — PDFDesk, Guido Cauli <guido.cauli@gmail.com>

Immagini (PNG, JPG, TIFF), testo semplice, DOCX e ODT.  DOCX e ODT sono scritti direttamente
(archivi zip con XML OOXML / OpenDocument), senza librerie esterne, ricostruendo la struttura
del documento: titoli, paragrafi con grassetto/corsivo/dimensione/colore/allineamento,
tabelle, immagini e interruzioni di pagina.
"""
from __future__ import annotations

import io
import os
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional
from xml.sax.saxutils import escape, quoteattr

import pymupdf as fitz

# Analisi del layout di PyMuPDF (pymupdf.layout + onnxruntime): non inclusa nel programma. Disattivata ovunque, così
# il riconoscimento delle tabelle (che richiede NumPy) funziona allo stesso modo dai sorgenti e negli eseguibili.
try:
    fitz._layout_enabled = False
except Exception:
    pass

from . import parallel

Progress = Optional[Callable[[int, int], bool]]       # (fatte, totali) -> False per annullare

IMAGE_FORMATS = {"png": "PNG", "jpg": "JPG", "tiff": "TIFF"}
FORMATS = {
    "png": ("Immagini PNG", ".png"), "jpg": ("Immagini JPG", ".jpg"), "tiff": ("Immagini TIFF", ".tiff"),
    "txt": ("Testo semplice (TXT)", ".txt"), "docx": ("Documento Word (DOCX)", ".docx"),
    "odt": ("Documento OpenDocument (ODT)", ".odt"),
}


class Cancelled(Exception):
    pass


def parse_pages(spec: str, count: int) -> list[int]:
    """«1-3, 5, 8-» → [0,1,2,4,7,…] (indici da 0).  Stringa vuota = tutte."""
    spec = (spec or "").strip()
    if not spec:
        return list(range(count))
    out: list[int] = []
    for part in re.split(r"[;,\s]+", spec):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else count
        elif part.isdigit():
            a = b = int(part)
        else:
            raise ValueError(f"Intervallo non valido: «{part}»")
        if a < 1 or b < a or b > count:
            raise ValueError(f"Intervallo fuori dalle pagine del documento (1–{count}): «{part}»")
        out += [p for p in range(a - 1, b) if p not in out]
    return out


def _tick(progress: Progress, i: int, n: int) -> None:
    if progress and progress(i, n) is False:
        raise Cancelled()


# ====================================================================== immagini
def _doc_bytes(doc: fitz.Document) -> bytes:
    kw = {"encryption": fitz.PDF_ENCRYPT_NONE} if getattr(doc, "is_encrypted", False) else {}
    return doc.tobytes(garbage=0, **kw)


def _run_parallel(doc, func, items, args, progress, min_pages=parallel.MIN_PAGES):
    """Lavoro su più processi; None se conviene restare seriali (poche pagine / un solo core / file enorme)."""
    if parallel.plan(len(items), 0, min_pages) <= 1:
        return None
    data = _doc_bytes(doc)
    w = parallel.plan(len(items), len(data), min_pages)
    if w <= 1:
        return None
    try:
        return parallel.run(data, func, items, w, args, progress)
    except parallel.Cancelled:
        raise Cancelled()
    except Exception:
        return None                    # processi non avviabili o errore in un processo: si ripete in modo seriale (che segnala l'errore vero)


def _parallel_images(doc, pages, fmt, dpi, quality, target, base, tiff_compression, progress):
    os.makedirs(target, exist_ok=True)
    res = _run_parallel(doc, parallel.w_export_images, list(pages), (fmt, dpi, quality, target, base, tiff_compression), progress)
    if res is None:
        return None
    ext = {"png": "png", "jpg": "jpg", "tiff": "tiff"}[fmt]
    return [os.path.join(target, f"{base}_p{p + 1:03d}.{ext}") for p in pages]       # nell'ordine richiesto


def export_images(doc: fitz.Document, pages: list[int], fmt: str, target: str, dpi: int = 150, quality: int = 85,
                  tiff_multipage: bool = True, tiff_compression: str = "tiff_lzw", progress: Progress = None) -> list[str]:
    """Esporta le pagine come immagini.  `target` è una cartella (file `nome_pNNN.ext`) oppure, per il TIFF
    multipagina, il percorso del file.  Restituisce i file scritti."""
    from PIL import Image
    fmt = fmt.lower()
    zoom = dpi / 72.0
    written: list[str] = []
    imgs: list = []
    base = "pagina"
    if fmt == "tiff" and tiff_multipage:
        pass
    else:
        os.makedirs(target, exist_ok=True)
    n = len(pages)
    if not (fmt == "tiff" and tiff_multipage):          # più core quando le pagine sono tante (il TIFF multipagina resta seriale)
        par = _parallel_images(doc, pages, fmt, dpi, quality, target, base, tiff_compression, progress)
        if par is not None:
            return par
    for k, p in enumerate(pages):
        _tick(progress, k, n)
        pix = doc[p].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.set_dpi(dpi, dpi)
        if fmt == "png":
            out = os.path.join(target, f"{base}_p{p + 1:03d}.png")
            pix.save(out)
            written.append(out)
        elif fmt == "jpg":
            out = os.path.join(target, f"{base}_p{p + 1:03d}.jpg")
            pix.save(out, jpg_quality=int(quality))
            written.append(out)
        elif fmt == "tiff":
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            if tiff_multipage:
                imgs.append(im)
            else:
                out = os.path.join(target, f"{base}_p{p + 1:03d}.tiff")
                im.save(out, compression=tiff_compression, dpi=(dpi, dpi))
                written.append(out)
        else:
            raise ValueError(f"Formato immagine sconosciuto: {fmt}")
    if fmt == "tiff" and tiff_multipage and imgs:
        d = os.path.dirname(os.path.abspath(target))
        os.makedirs(d, exist_ok=True)
        imgs[0].save(target, save_all=True, append_images=imgs[1:], compression=tiff_compression, dpi=(dpi, dpi))
        written.append(target)
    _tick(progress, n, n)
    return written


# ====================================================================== testo semplice
def export_text(doc: fitz.Document, pages: list[int], target: str, progress: Progress = None, keep_layout: bool = True) -> str:
    from .export_fixed import layout_text
    parts = []
    n = len(pages)
    res = _run_parallel(doc, parallel.w_text, list(pages), (keep_layout,), progress)
    if res is not None:
        by = {p: t for part in res for p, t in part}
        parts = [by[p] for p in pages]
        pages = []                                       # già fatto: il ciclo seriale sotto non gira
    for k, p in enumerate(pages):
        _tick(progress, k, n)
        parts.append(layout_text(doc[p]).rstrip("\n") if keep_layout else doc[p].get_text("text", sort=True).rstrip())
    text = "\n\n\f".join(parts) + "\n"
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    _tick(progress, n, n)
    return target


# ====================================================================== struttura del documento
@dataclass
class Run:
    text: str
    font: str = ""
    size: float = 11.0
    bold: bool = False
    italic: bool = False
    color: str = "000000"        # RRGGBB


@dataclass
class Block:
    kind: str                    # "para" | "table" | "image"
    runs: list = field(default_factory=list)
    level: int = 0               # 1-3 = titolo
    align: str = "left"
    rows: list = field(default_factory=list)       # tabella: righe di celle (stringhe)
    image: bytes = b""
    ext: str = "png"
    w: float = 0.0               # dimensioni dell'immagine in punti
    h: float = 0.0
    page_break: bool = False     # inizia una nuova pagina


@dataclass
class Layout:
    width: float
    height: float
    margins: tuple               # sinistra, alto, destra, basso (pt)
    blocks: list


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _clean(t: str) -> str:
    return _CTRL.sub("", t)


def _family(name: str) -> str:
    n = re.sub(r"^[A-Z]{6}\+", "", name or "")
    n = re.split(r"[-,]", n)[0]
    n = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", n)       # «TimesNewRoman» → «Times New Roman»
    n = re.sub(r"\b(Bold|Italic|Oblique|Regular|MT|PS)\b", "", n).strip()
    return n or "Arial"


def _rgb(c: int) -> str:
    return f"{(c >> 16) & 255:02X}{(c >> 8) & 255:02X}{c & 255:02X}"


def _image_bytes(img: bytes, ext: str) -> tuple[bytes, str]:
    ext = (ext or "").lower().replace("jpeg", "jpg")
    if ext in ("png", "jpg"):
        return img, ext
    try:
        pix = fitz.Pixmap(img)
        if pix.colorspace and pix.colorspace.n > 3 or pix.alpha and pix.colorspace.n != 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        return pix.tobytes("png"), "png"
    except Exception:
        return b"", ""


def _para_from_block(b: dict, body: float) -> Optional[Block]:
    runs: list[Run] = []
    sizes: Counter = Counter()
    for ln in b.get("lines", []):
        spans = [s for s in ln.get("spans", []) if s.get("text") is not None]
        if not spans:
            continue
        for s in spans:
            t = _clean(s["text"])
            if not t:
                continue
            fl = s.get("flags", 0)
            font = s.get("font", "")
            r = Run(t, _family(font), round(s.get("size", 11), 1), bool(fl & 16) or "bold" in font.lower(),
                    bool(fl & 2) or "italic" in font.lower() or "oblique" in font.lower(), _rgb(s.get("color", 0)))
            sizes[r.size] += len(t)
            if runs and (runs[-1].font, runs[-1].size, runs[-1].bold, runs[-1].italic, runs[-1].color) == \
                    (r.font, r.size, r.bold, r.italic, r.color):
                runs[-1].text += r.text
            else:
                runs.append(r)
        # fine riga: spazio (o niente se la riga termina con un trattino di sillabazione)
        last = runs[-1]
        if last.text.endswith("-") and len(last.text) > 1 and last.text[-2].isalpha():
            last.text = last.text[:-1]
        elif not last.text.endswith(" "):
            last.text += " "
    if not runs or not "".join(r.text for r in runs).strip():
        return None
    runs[-1].text = runs[-1].text.rstrip()
    blk = Block("para", runs)
    size = sizes.most_common(1)[0][0]
    total = sum(len(r.text) for r in runs)
    allbold = all(r.bold for r in runs)
    if total <= 160 and body and size >= body * 1.18:
        blk.level = 1 if size >= body * 1.6 else 2 if size >= body * 1.35 else 3
    elif total <= 90 and allbold and body and size >= body * 1.0 and len(b.get("lines", [])) == 1:
        blk.level = 3
    return blk


def extract_layout(doc: fitz.Document, pages: list[int], progress: Progress = None) -> Layout:
    # dimensione del testo «normale» = quella più frequente (per numero di caratteri)
    freq: Counter = Counter()
    for p in pages[:30]:
        for b in doc[p].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    freq[round(s["size"], 1)] += len(s["text"].strip())
    body = freq.most_common(1)[0][0] if freq else 11.0

    first = doc[pages[0]].rect
    blocks: list[Block] = []
    xs0: list[float] = []; xs1: list[float] = []; ys0: list[float] = []; ys1: list[float] = []
    n = len(pages)
    for k, p in enumerate(pages):
        _tick(progress, k, n)
        page = doc[p]
        pw = page.rect.width
        d = page.get_text("dict", sort=True)
        tables = []
        try:
            for t in page.find_tables(use_layout=False).tables:
                rows = t.extract()
                if rows and len(rows) >= 1 and len(rows[0]) >= 2:
                    tables.append((fitz.Rect(t.bbox), [[_clean((c or "").replace("\n", " ")).strip() for c in r] for r in rows]))
        except Exception:
            tables = []
        items: list[tuple[float, float, Block]] = []
        for tb, rows in tables:
            items.append((tb.y0, tb.x0, Block("table", rows=rows)))
        for b in d["blocks"]:
            bb = fitz.Rect(b["bbox"])
            if any((bb & tr).get_area() > 0.5 * bb.get_area() for tr, _ in tables if not (bb & tr).is_empty):
                continue
            if b["type"] == 0:
                blk = _para_from_block(b, body)
                if blk is None:
                    continue
                cx = (bb.x0 + bb.x1) / 2
                if bb.width < pw * 0.8 and abs(cx - pw / 2) < pw * 0.03 and bb.x0 > pw * 0.12:
                    blk.align = "center"
                elif bb.x0 > pw * 0.45 and bb.x1 > pw * 0.8 and bb.width < pw * 0.5:
                    blk.align = "right"
                xs0.append(bb.x0); xs1.append(bb.x1); ys0.append(bb.y0); ys1.append(bb.y1)
                items.append((bb.y0, bb.x0, blk))
            elif b["type"] == 1 and b.get("image"):
                data, ext = _image_bytes(b["image"], b.get("ext", ""))
                if data and bb.width > 4 and bb.height > 4:
                    items.append((bb.y0, bb.x0, Block("image", image=data, ext=ext, w=bb.width, h=bb.height)))
        items.sort(key=lambda t: (round(t[0] / 4), t[1]))
        if items:
            items[0][2].page_break = bool(blocks)
        elif blocks:
            blocks.append(Block("para", [Run("")], page_break=True))
        blocks += [it[2] for it in items]
    _tick(progress, n, n)
    cl = lambda v: max(28.0, min(90.0, v))
    margins = (cl(min(xs0, default=54)), cl(min(ys0, default=54)),
               cl(first.width - max(xs1, default=first.width - 54)), cl(first.height - max(ys1, default=first.height - 54)))
    return Layout(first.width, first.height, margins, blocks)


# ====================================================================== DOCX
_NS_DOCX = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')
_EMU = 12700


def _docx_run(r: Run) -> str:
    props = f'<w:rFonts w:ascii={quoteattr(r.font)} w:hAnsi={quoteattr(r.font)} w:cs={quoteattr(r.font)}/>' if r.font else ""
    if r.bold:
        props += "<w:b/>"
    if r.italic:
        props += "<w:i/>"
    if r.color != "000000":
        props += f'<w:color w:val="{r.color}"/>'
    props += f'<w:sz w:val="{max(2, int(round(r.size * 2)))}"/>'
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(r.text)}</w:t></w:r>'


def export_docx(doc: fitz.Document, pages: list[int], target: str, progress: Progress = None, keep_layout: bool = True) -> str:
    if keep_layout:
        from .export_fixed import export_docx_fixed
        return export_docx_fixed(doc, pages, target, progress)
    lay = extract_layout(doc, pages, progress)
    avail = lay.width - lay.margins[0] - lay.margins[2]
    body: list[str] = []
    media: list[tuple[str, bytes]] = []
    rels: list[str] = []
    for blk in lay.blocks:
        brk = '<w:pageBreakBefore/>' if blk.page_break else ""
        if blk.kind == "para":
            style = f'<w:pStyle w:val="Heading{blk.level}"/>' if blk.level else ""
            jc = {"center": '<w:jc w:val="center"/>', "right": '<w:jc w:val="right"/>'}.get(blk.align, "")
            body.append(f'<w:p><w:pPr>{style}{brk}{jc}</w:pPr>{"".join(_docx_run(r) for r in blk.runs if r.text)}</w:p>')
        elif blk.kind == "table":
            ncol = max(len(r) for r in blk.rows)
            colw = int(avail * 20 / ncol)
            out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>'
                   + f'<w:gridCol w:w="{colw}"/>' * ncol + '</w:tblGrid>']
            for row in blk.rows:
                cells = list(row) + [""] * (ncol - len(row))
                out.append("<w:tr>" + "".join(
                    f'<w:tc><w:tcPr><w:tcW w:w="{colw}" w:type="dxa"/></w:tcPr><w:p><w:r><w:t xml:space="preserve">{escape(c)}</w:t></w:r></w:p></w:tc>'
                    for c in cells) + "</w:tr>")
            out.append("</w:tbl>")
            if blk.page_break:
                body.append('<w:p><w:pPr><w:pageBreakBefore/></w:pPr></w:p>')
            body.append("".join(out))
            body.append("<w:p/>")                               # Word richiede un paragrafo dopo una tabella
        elif blk.kind == "image":
            idx = len(media) + 1
            name = f"image{idx}.{blk.ext}"
            media.append((name, blk.image))
            rels.append(f'<Relationship Id="rIdImg{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>')
            w, h = blk.w, blk.h
            if w > avail:
                h, w = h * avail / w, avail
            cx, cy = int(w * _EMU), int(h * _EMU)
            drawing = (f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
                       f'<wp:docPr id="{idx}" name="Immagine {idx}"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
                       f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{idx}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
                       f'<pic:blipFill><a:blip r:embed="rIdImg{idx}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                       f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                       f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>')
            body.append(f'<w:p><w:pPr>{brk}</w:pPr><w:r>{drawing}</w:r></w:p>')
    if not body:
        body.append("<w:p/>")
    m = lay.margins
    sect = (f'<w:sectPr><w:pgSz w:w="{int(lay.width * 20)}" w:h="{int(lay.height * 20)}"/>'
            f'<w:pgMar w:top="{int(m[1] * 20)}" w:right="{int(m[2] * 20)}" w:bottom="{int(m[3] * 20)}" w:left="{int(m[0] * 20)}" '
            f'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    document = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {_NS_DOCX}><w:body>{"".join(body)}{sect}</w:body></w:document>'
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
              + "".join(f'<w:style w:type="paragraph" w:styleId="Heading{i}"><w:name w:val="heading {i}"/><w:basedOn w:val="Normal"/>'
                        f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="{240 - 40 * i}" w:after="120"/>'
                        f'<w:outlineLvl w:val="{i - 1}"/></w:pPr><w:rPr><w:b/><w:sz w:val="{36 - 4 * i}"/></w:rPr></w:style>' for i in (1, 2, 3))
              + '<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:uiPriority w:val="99"/><w:semiHidden/>'
                '<w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
                '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>'
                '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:basedOn w:val="TableNormal"/>'
                '<w:tblPr><w:tblBorders>'
              + "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="808080"/>' for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
              + '</w:tblBorders></w:tblPr></w:style></w:styles>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
          '<Default Extension="jpg" ContentType="image/jpeg"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>')
    rootrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
    docrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rIdSt" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
               + "".join(rels) + "</Relationships>")
    core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>PDFDesk</dc:creator></cp:coreProperties>')
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rootrels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/_rels/document.xml.rels", docrels)
        z.writestr("docProps/core.xml", core)
        for name, data in media:
            z.writestr("word/media/" + name, data)
    return target


# ====================================================================== ODT
def export_odt(doc: fitz.Document, pages: list[int], target: str, progress: Progress = None, keep_layout: bool = True) -> str:
    if keep_layout:
        from .export_fixed import export_odt_fixed
        return export_odt_fixed(doc, pages, target, progress)
    lay = extract_layout(doc, pages, progress)
    avail = lay.width - lay.margins[0] - lay.margins[2]
    tstyles: dict[tuple, str] = {}           # stili di carattere
    pstyles: dict[tuple, str] = {}           # stili di paragrafo (genitore, allineamento, interruzione)
    media: list[tuple[str, bytes]] = []
    body: list[str] = []

    def tstyle(r: Run) -> str:
        key = (r.font, r.size, r.bold, r.italic, r.color)
        if key not in tstyles:
            tstyles[key] = f"T{len(tstyles) + 1}"
        return tstyles[key]

    def pstyle(parent: str, align: str, brk: bool) -> str:
        key = (parent, align, brk)
        if key not in pstyles:
            pstyles[key] = f"P{len(pstyles) + 1}"
        return pstyles[key]

    for blk in lay.blocks:
        if blk.kind == "para":
            ps = pstyle("Standard" if not blk.level else f"Heading_20_{blk.level}", blk.align, blk.page_break)
            spans = "".join(f'<text:span text:style-name="{tstyle(r)}">{escape(r.text)}</text:span>' for r in blk.runs if r.text)
            if blk.level:
                body.append(f'<text:h text:style-name="{ps}" text:outline-level="{blk.level}">{spans}</text:h>')
            else:
                body.append(f'<text:p text:style-name="{ps}">{spans}</text:p>')
        elif blk.kind == "table":
            if blk.page_break:
                body.append(f'<text:p text:style-name="{pstyle("Standard", "left", True)}"/>')
            ncol = max(len(r) for r in blk.rows)
            tn = sum(1 for b in body if b.startswith("<table:table ")) + 1
            out = [f'<table:table table:name="Tabella{tn}" table:style-name="Tab1"><table:table-column table:style-name="TabCol" table:number-columns-repeated="{ncol}"/>']
            for row in blk.rows:
                cells = list(row) + [""] * (ncol - len(row))
                out.append("<table:table-row>" + "".join(
                    f'<table:table-cell table:style-name="TabCell" office:value-type="string"><text:p text:style-name="Standard">{escape(c)}</text:p></table:table-cell>'
                    for c in cells) + "</table:table-row>")
            out.append("</table:table>")
            body.append("".join(out))
        elif blk.kind == "image":
            idx = len(media) + 1
            name = f"Pictures/img{idx}.{blk.ext}"
            media.append((name, blk.image))
            w, h = blk.w, blk.h
            if w > avail:
                h, w = h * avail / w, avail
            ps = pstyle("Standard", "left", blk.page_break)
            body.append(f'<text:p text:style-name="{ps}"><draw:frame draw:style-name="fr1" draw:name="Immagine{idx}" text:anchor-type="as-char" '
                        f'svg:width="{w:.2f}pt" svg:height="{h:.2f}pt"><draw:image xlink:href="{name}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></text:p>')
    if not body:
        body.append('<text:p text:style-name="Standard"/>')

    auto = []
    for (font, size, bold, italic, color), nm in tstyles.items():
        pr = f'fo:font-size="{size}pt" fo:color="#{color}"'
        if font:
            pr += f' style:font-name={quoteattr(font)}'
        if bold:
            pr += ' fo:font-weight="bold"'
        if italic:
            pr += ' fo:font-style="italic"'
        auto.append(f'<style:style style:name="{nm}" style:family="text"><style:text-properties {pr}/></style:style>')
    for (parent, align, brk), nm in pstyles.items():
        pr = ""
        if align != "left":
            pr += f' fo:text-align="{align}"'
        if brk:
            pr += ' fo:break-before="page"'
        auto.append(f'<style:style style:name="{nm}" style:family="paragraph" style:parent-style-name="{parent}"><style:paragraph-properties{pr}/></style:style>')
    cw = avail / 1.0
    auto.append('<style:style style:name="Tab1" style:family="table"><style:table-properties style:width="%.2fpt" table:align="margins"/></style:style>' % cw)
    auto.append('<style:style style:name="TabCol" style:family="table-column"/>')
    auto.append('<style:style style:name="TabCell" style:family="table-cell"><style:table-cell-properties fo:padding="2pt" fo:border="0.5pt solid #808080"/></style:style>')
    auto.append('<style:style style:name="fr1" style:family="graphic"><style:graphic-properties style:vertical-pos="top" style:vertical-rel="baseline" fo:padding="0pt" fo:border="none"/></style:style>')
    fonts = sorted({k[0] for k in tstyles if k[0]})
    fontdecl = "".join(f'<style:font-face style:name={quoteattr(f)} svg:font-family={quoteattr(f)}/>' for f in fonts)
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
          'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
          'xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
          'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" xmlns:dc="http://purl.org/dc/elements/1.1/"')
    content = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {ns} office:version="1.2">'
               f'<office:font-face-decls>{fontdecl}</office:font-face-decls><office:automatic-styles>{"".join(auto)}</office:automatic-styles>'
               f'<office:body><office:text>{"".join(body)}</office:text></office:body></office:document-content>')
    m = lay.margins
    heads = "".join(
        f'<style:style style:name="Heading_20_{i}" style:display-name="Heading {i}" style:family="paragraph" style:parent-style-name="Standard" '
        f'style:next-style-name="Standard" style:default-outline-level="{i}"><style:paragraph-properties fo:margin-top="{12 - 2 * i}pt" fo:margin-bottom="6pt" fo:keep-with-next="always"/>'
        f'<style:text-properties fo:font-size="{20 - 2 * i}pt" fo:font-weight="bold"/></style:style>' for i in (1, 2, 3))
    styles = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-styles {ns} office:version="1.2">'
              '<office:styles><style:default-style style:family="paragraph"><style:paragraph-properties fo:margin-bottom="6pt"/>'
              '<style:text-properties style:font-name="Arial" fo:font-size="11pt"/></style:default-style>'
              '<style:style style:name="Standard" style:family="paragraph" style:class="text"/>' + heads + '</office:styles>'
              '<office:automatic-styles>'
              f'<style:page-layout style:name="pm1"><style:page-layout-properties fo:page-width="{lay.width:.2f}pt" fo:page-height="{lay.height:.2f}pt" '
              f'fo:margin-top="{m[1]:.1f}pt" fo:margin-bottom="{m[3]:.1f}pt" fo:margin-left="{m[0]:.1f}pt" fo:margin-right="{m[2]:.1f}pt"/></style:page-layout>'
              '</office:automatic-styles><office:master-styles><style:master-page style:name="Standard" style:page-layout-name="pm1"/></office:master-styles>'
              '</office:document-styles>')
    meta = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-meta {ns} office:version="1.2"><office:meta>'
            '<meta:generator>PDFDesk</meta:generator></office:meta></office:document-meta>')
    entries = ['<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>']
    for f in ("content.xml", "styles.xml", "meta.xml"):
        entries.append(f'<manifest:file-entry manifest:full-path="{f}" manifest:media-type="text/xml"/>')
    for name, _ in media:
        entries.append(f'<manifest:file-entry manifest:full-path="{name}" manifest:media-type="image/{"jpeg" if name.endswith("jpg") else "png"}"/>')
    manifest = ('<?xml version="1.0" encoding="UTF-8"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" '
                'manifest:version="1.2">' + "".join(entries) + "</manifest:manifest>")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/manifest.xml", manifest)
        z.writestr("content.xml", content)
        z.writestr("styles.xml", styles)
        z.writestr("meta.xml", meta)
        for name, data in media:
            z.writestr(name, data)
    return target


# ====================================================================== punto d'ingresso
def export(doc: fitz.Document, fmt: str, pages: list[int], target: str, **opt) -> list[str]:
    """Esporta `pages` nel formato `fmt`.  Per le immagini `target` è una cartella (o il file, per il TIFF multipagina)."""
    if not pages:
        raise ValueError("Nessuna pagina da esportare")
    progress = opt.get("progress")
    if fmt in IMAGE_FORMATS or fmt in ("png", "jpg", "tiff"):
        return export_images(doc, pages, fmt, target, dpi=opt.get("dpi", 150), quality=opt.get("quality", 85),
                             tiff_multipage=opt.get("tiff_multipage", True), tiff_compression=opt.get("tiff_compression", "tiff_lzw"),
                             progress=progress)
    if fmt == "txt":
        return [export_text(doc, pages, target, progress, opt.get("keep_layout", True))]
    if fmt == "docx":
        return [export_docx(doc, pages, target, progress, opt.get("keep_layout", True))]
    if fmt == "odt":
        return [export_odt(doc, pages, target, progress, opt.get("keep_layout", True))]
    raise ValueError(f"Formato non supportato: {fmt}")
