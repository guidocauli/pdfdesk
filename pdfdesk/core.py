# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# core.py: modello del documento PDF (annotazioni reali, annulla/ripeti, pagine, redazione).
from __future__ import annotations

import os
import math
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Optional, Sequence

import pymupdf as fitz
from . import imgutil

from . import fonts, pdfstd, textbox


def _pdf_str_decode(v: str) -> str:
    """Valore di una stringa PDF come restituito da xref_get_key → testo."""
    v = v.strip()
    try:
        if v.startswith("<") and v.endswith(">"):
            b = bytes.fromhex(re.sub(r"\s", "", v[1:-1]))
            return b.decode("utf-16-be", "replace").lstrip("\ufeff") if b[:2] == b"\xfe\xff" else b.decode("latin-1")
        if v.startswith("(") and v.endswith(")"):
            v = v[1:-1]
            v = re.sub(r"\\([nrtbf()\\])", lambda m: {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}.get(m.group(1), m.group(1)), v)
            return re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8)), v)
    except Exception:
        pass
    return v


def pdf_date_to_iso(d: str) -> str:
    """«D:20260131235959+01'00'» → «2026-01-31T23:59:59+01:00» (stringa vuota se non valida)."""
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?'?", (d or "").strip())
    if not m or not m.group(1):
        return ""
    y, mo, da, h, mi, se = (m.group(i) or ("01" if i in (2, 3) else "00") for i in range(1, 7))
    tz = m.group(7)
    z = "" if not tz else "Z" if tz in "Zz" else f"{tz}{m.group(8) or '00'}:{m.group(9) or '00'}"
    return f"{y}-{mo}-{da}T{h}:{mi}:{se}{z}"


def pdf_date_to_display(d: str) -> str:
    """Per la modifica: «2026-01-31 23:59:59 +01:00» (se non riconosciuta, il testo originale)."""
    iso = pdf_date_to_iso(d)
    if not iso:
        return d or ""
    return iso.replace("T", " ", 1).replace("+", " +", 1).replace("Z", " UTC") if "-" not in iso[19:] else iso.replace("T", " ", 1)[:19] + " " + iso[19:]


def display_to_pdf_date(t: str) -> str:
    """«2026-01-31 23:59[:59] [+01:00|UTC]» o «D:…» → data PDF. Stringa vuota → vuota. Errore → ValueError."""
    t = (t or "").strip()
    if not t:
        return ""
    if t.startswith("D:"):
        return t
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?\s*(UTC|Z|[+\-]\d{2}:?\d{2})?", t)
    if not m:
        raise ValueError(f"Data non valida: «{t}» (usa AAAA-MM-GG hh:mm:ss [+hh:mm])")
    y, mo, da, h, mi, se, tz = m.groups()
    out = f"D:{y}{mo}{da}{h or '00'}{mi or '00'}{se or '00'}"
    if tz in ("UTC", "Z"):
        out += "Z"
    elif tz:
        tz = tz.replace(":", "")
        out += f"{tz[0]}{tz[1:3]}'{tz[3:5]}'"
    return out

Color = tuple[float, float, float]
Point = tuple[float, float]

FONTS = {"Helvetica": "helv", "Times": "tiro", "Courier": "cour"}
FONT_NAMES = {v: k for k, v in FONTS.items()}

# Tipi di annotazione gestiti
T_FREETEXT = fitz.PDF_ANNOT_FREE_TEXT
T_LINE = fitz.PDF_ANNOT_LINE
T_SQUARE = fitz.PDF_ANNOT_SQUARE
T_CIRCLE = fitz.PDF_ANNOT_CIRCLE
T_HIGHLIGHT = fitz.PDF_ANNOT_HIGHLIGHT
T_UNDERLINE = fitz.PDF_ANNOT_UNDERLINE
T_STRIKE = fitz.PDF_ANNOT_STRIKE_OUT
T_REDACT = fitz.PDF_ANNOT_REDACT
T_STAMP = fitz.PDF_ANNOT_STAMP
T_INK = fitz.PDF_ANNOT_INK

RECT_TYPES = {T_FREETEXT, T_SQUARE, T_CIRCLE, T_STAMP, T_REDACT}   # set_rect supportato
REBUILD_TYPES = {T_INK, T_LINE}                                     # ricostruiti con nuovi punti
TEXT_TYPES = {T_FREETEXT}


class PdfError(Exception):
    pass


class PasswordRequired(PdfError):
    pass


@dataclass
class AnnotInfo:
    xref: int
    type: int
    kind: str
    rect: fitz.Rect                       # coordinate di visualizzazione (pagina ruotata)
    stroke: Optional[Color] = None
    fill: Optional[Color] = None
    width: float = 1.0
    opacity: float = 1.0
    text: str = ""
    fontsize: float = 12.0
    fontname: str = "helv"
    text_color: Color = (0, 0, 0)
    movable: bool = False
    resizable: bool = False


def _rgb(c) -> Optional[Color]:
    if c is None:
        return None
    c = tuple(float(x) for x in c)
    if len(c) == 3:
        return c
    if len(c) == 1:
        return (c[0],) * 3
    return None


def to_page_rect(page: fitz.Page, r) -> fitz.Rect:
    """Rettangolo di visualizzazione -> spazio pagina (non ruotato)."""
    return (fitz.Rect(r) * page.derotation_matrix).normalize()


def to_display_rect(page: fitz.Page, r) -> fitz.Rect:
    return (fitz.Rect(r) * page.rotation_matrix).normalize()


def to_page_pt(page: fitz.Page, p) -> fitz.Point:
    return fitz.Point(p) * page.derotation_matrix


def _parse_da(da: str):
    """Estrae (nome font, dimensione, colore testo) dalla stringa DA di un FreeText."""
    fontname, size, color = "helv", 12.0, (0.0, 0.0, 0.0)
    m = re.search(r"/(\w+)\s+([\d.]+)\s+Tf", da or "")
    if m:
        fontname = m.group(1).lower()
        size = float(m.group(2)) or 12.0
    m = re.search(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg", da or "")
    if m:
        color = tuple(float(x) for x in m.groups())
    else:
        m = re.search(r"([\d.]+)\s+g\b", da or "")
        if m:
            color = (float(m.group(1)),) * 3
    return fontname, size, color


def _font_from_span(font: str, flags: int) -> str:
    bold, italic = bool(flags & 16), bool(flags & 2)
    low = (font or "").lower()
    bold = bold or "bold" in low
    italic = italic or "italic" in low or "oblique" in low
    if flags & 8 or "cour" in low or "mono" in low:
        base = "co"
    elif flags & 4 or "times" in low or "serif" in low and "sans" not in low:
        base = "ti"
    else:
        base = "he"
    if base == "co":
        return {(0, 0): "cour", (1, 0): "cobo", (0, 1): "coit", (1, 1): "cobi"}[(int(bold), int(italic))]
    if base == "ti":
        return {(0, 0): "tiro", (1, 0): "tibo", (0, 1): "tiit", (1, 1): "tibi"}[(int(bold), int(italic))]
    return {(0, 0): "helv", (1, 0): "hebo", (0, 1): "heit", (1, 1): "hebi"}[(int(bold), int(italic))]


class PdfDocument:
    """Un documento PDF in modifica. Tutte le modifiche sono annotazioni/operazioni reali sul PDF."""

    MAX_UNDO_BYTES = 400 * 1024 * 1024

    def __init__(self) -> None:
        self.doc: fitz.Document = fitz.open()
        self.last_changed: Optional[list] = None
        self.path: Optional[str] = None
        self.modified = False
        self.version = 0                   # incrementa a ogni cambiamento (invalida cache di rendering)
        self.signed_count = 0
        self._orig: Optional[bytes] = None        # byte originali di un PDF firmato (base del salvataggio incrementale)
        self._password: Optional[str] = None
        self._undo: list[bytes] = []
        self._redo: list[bytes] = []
        self._last_label = ""
        self.standard: Optional[str] = None    # standard dichiarato all'apertura (es. «PDF/A-2b»)
        self.standard_warned = False
        self._destr: list[int] = []        # posizione nella pila di annulla delle operazioni permanenti non ancora salvate
        self._redo_destr: list[list[int]] = []

    # ------------------------------------------------------------------ operazioni permanenti
    _ALWAYS = 10 ** 9                      # per i documenti firmati (senza annulla): mai invalidata

    @property
    def has_permanent_changes(self) -> bool:
        """True se dall'ultimo salvataggio sono state fatte operazioni che eliminano contenuto dal file
        (redazioni, rimozione/modifica di testo, immagini e grafica): salvando sull'originale non sono recuperabili."""
        return bool(self._destr)

    def _mark_permanent(self) -> None:
        self._destr.append(len(self._undo) if not self.is_signed else self._ALWAYS)

    # ------------------------------------------------------------------ apertura/chiusura
    @classmethod
    def open(cls, path: str, password: Optional[str] = None) -> "PdfDocument":
        d = cls()
        doc = fitz.open(path)
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                doc.close()
                raise PasswordRequired(path)
        d._password = password
        d.signed_count = cls._count_signatures(doc)
        if d.signed_count:
            # il documento firmato si modifica in memoria come ogni altro (annulla/ripeti compresi); il salvataggio
            # accoda le differenze al file originale, che resta intatto (firme valide sulla loro revisione)
            doc.close()
            with open(path, "rb") as f:
                d._orig = f.read()
            doc = fitz.open("pdf", d._orig)
            if doc.needs_pass:
                doc.authenticate(password or "")
        d.doc = doc
        d.path = os.path.abspath(path)
        d.standard = pdfstd.detect_doc(doc)
        return d

    @classmethod
    def new(cls) -> "PdfDocument":
        d = cls()
        d.doc.new_page()
        return d

    @staticmethod
    def _count_signatures(doc: fitz.Document) -> int:
        try:
            if not doc.is_form_pdf:
                return 0
            n = 0
            for page in doc:
                for w in page.widgets() or []:
                    if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and w.is_signed:
                        n += 1
            return n
        except Exception:
            return 0

    def close(self) -> None:
        self.doc.close()

    # ------------------------------------------------------------------ proprietà
    @property
    def page_count(self) -> int:
        return self.doc.page_count

    @property
    def is_signed(self) -> bool:
        return self.signed_count > 0

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def page(self, pno: int) -> fitz.Page:
        return self.doc[pno]

    def page_size(self, pno: int) -> tuple[float, float]:
        r = self.doc[pno].rect
        return r.width, r.height

    def render(self, pno: int, scale: float) -> fitz.Pixmap:
        return self.doc[pno].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False, annots=True)

    # ------------------------------------------------------------------ annulla / ripeti
    def _snapshot(self) -> bytes:
        return self.doc.tobytes(garbage=0)

    def _begin(self, label: str = "") -> None:
        """Da chiamare PRIMA di ogni modifica: salva lo stato per annulla/ripeti."""
        self._undo.append(self._snapshot())
        total = sum(len(b) for b in self._undo)
        while len(self._undo) > 1 and total > self.MAX_UNDO_BYTES:
            total -= len(self._undo.pop(0))
            self._destr = [max(1, m - 1) if m != self._ALWAYS else m for m in self._destr]
        self._redo.clear()
        self._redo_destr.clear()
        self._last_label = label
        self.modified = True
        self.version += 1

    def _replace_doc(self, data: bytes) -> None:
        self.doc.close()
        self.doc = fitz.open("pdf", data)
        self.version += 1

    @staticmethod
    def _page_sigs(doc: fitz.Document) -> list:
        """Impronta di ogni pagina (contenuto, dizionario, annotazioni con aspetto): serve a sapere cosa cambia con annulla/ripeti."""
        import hashlib
        out = []
        for page in doc:
            h = hashlib.md5()
            h.update(doc.xref_object(page.xref, compressed=True).encode("utf-8", "replace"))
            h.update(page.read_contents())
            for a in page.annots() or []:
                h.update(doc.xref_object(a.xref, compressed=True).encode("utf-8", "replace"))
                ap = doc.xref_get_key(a.xref, "AP/N")
                if ap[0] == "xref":
                    try:
                        h.update(doc.xref_stream_raw(int(ap[1].split()[0])) or b"")
                    except Exception:
                        pass
            out.append((h.digest(), tuple(page.rect), page.rotation))
        return out

    def _swap_doc(self, data: bytes) -> None:
        """Sostituisce il documento e calcola `last_changed`: pagine modificate, o None se la struttura è cambiata."""
        try:
            old = self._page_sigs(self.doc)
        except Exception:
            old = None
        self._replace_doc(data)
        self.last_changed = None
        try:
            new = self._page_sigs(self.doc)
            if old is not None and len(old) == len(new) and all(o[1:] == n[1:] for o, n in zip(old, new)):
                self.last_changed = [i for i, (o, n) in enumerate(zip(old, new)) if o[0] != n[0]]
        except Exception:
            self.last_changed = None

    def undo(self) -> bool:
        if not self.can_undo:
            return False
        self._redo.append(self._snapshot())
        self._swap_doc(self._undo.pop())
        n = len(self._undo)
        self._redo_destr.append([m for m in self._destr if m > n and m != self._ALWAYS])
        self._destr = [m for m in self._destr if m <= n or m == self._ALWAYS]
        self.modified = True
        return True

    def redo(self) -> bool:
        if not self.can_redo:
            return False
        self._undo.append(self._snapshot())
        self._swap_doc(self._redo.pop())
        if self._redo_destr:
            self._destr += self._redo_destr.pop()
        self.modified = True
        return True

    # ------------------------------------------------------------------ annotazioni: creazione
    def _style(self, a: fitz.Annot, stroke=None, fill=None, width=None, opacity=None) -> None:
        if width is not None:
            a.set_border(width=float(width))
        if stroke is not None or fill is not None:
            a.set_colors(stroke=stroke, fill=fill)
        if opacity is not None and opacity < 0.999:
            a.set_opacity(float(opacity))
        a.update()

    def add_ink(self, pno: int, strokes: Sequence[Sequence[Point]], color: Color = (0, 0, 0),
                width: float = 2.0, opacity: float = 1.0, highlighter: bool = False) -> int:
        page = self.doc[pno]
        pts = [[tuple(to_page_pt(page, p)) for p in s] for s in strokes if len(s) >= 2]
        if not pts:
            raise PdfError("tratto vuoto")
        self._begin("tratto")
        a = page.add_ink_annot(pts)
        a.set_border(width=float(width))
        a.set_colors(stroke=color)
        if opacity < 0.999:
            a.set_opacity(float(opacity))
        if highlighter:
            try:
                a.set_blendmode("Multiply")
            except Exception:
                pass
        a.update()
        return a.xref

    def add_shape(self, pno: int, kind: str, rect, stroke: Optional[Color] = (0, 0, 0),
                  fill: Optional[Color] = None, width: float = 2.0, opacity: float = 1.0) -> int:
        page = self.doc[pno]
        r = to_page_rect(page, rect)
        if r.width < 1 or r.height < 1:
            raise PdfError("area troppo piccola")
        self._begin("forma")
        a = page.add_rect_annot(r) if kind == "rect" else page.add_circle_annot(r)
        self._style(a, stroke=stroke or (0, 0, 0), fill=fill, width=width if stroke else 0, opacity=opacity)
        return a.xref

    def add_line(self, pno: int, p1: Point, p2: Point, stroke: Color = (0, 0, 0), width: float = 2.0,
                 arrow: bool = False, opacity: float = 1.0) -> int:
        page = self.doc[pno]
        self._begin("linea")
        a = page.add_line_annot(to_page_pt(page, p1), to_page_pt(page, p2))
        if arrow:
            a.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
            a.set_colors(stroke=stroke, fill=stroke)
        else:
            a.set_colors(stroke=stroke)
        self._style(a, width=width, opacity=opacity)
        return a.xref

    def add_text(self, pno: int, rect, text: str, fontsize: float = 12, fontname: str = "helv",
                 color: Color = (0, 0, 0), fill: Optional[Color] = None, border: float = 0.0) -> int:
        page = self.doc[pno]
        r = to_page_rect(page, rect)
        custom = fonts.is_custom(fontname)
        path = None
        if custom:
            path = fonts.resolve(fontname)
            if not path:
                raise PdfError(f"Font «{fontname[1:]}» non disponibile: aggiungilo dalla libreria font.")
        self._begin("testo")
        a = page.add_freetext_annot(r, text, fontsize=float(fontsize), fontname="helv" if custom else fontname,
                                    text_color=color, fill_color=fill, border_width=float(border),
                                    rotate=page.rotation)
        xref = a.xref
        if custom:
            self.doc.xref_set_key(xref, "PDFDeskFont", fitz.get_pdf_str(fontname[1:]))
            self._regen_custom(pno, xref)
        return xref

    # -- caselle di testo con font TTF/OTF: l'aspetto è un XObject generato da textbox.build_ap
    def _custom_font(self, xref: int) -> Optional[str]:
        t, v = self.doc.xref_get_key(xref, "PDFDeskFont")
        return v if t == "string" and v else None

    def _regen_custom(self, pno: int, xref: int) -> None:
        page = self.doc[pno]
        a = self._find(page, xref)
        info = self._info(page, a)
        name = self._custom_font(xref)
        path = fonts.resolve("@" + name) if name else None
        if not path:
            raise PdfError(f"Font «{name}» non disponibile: aggiungilo dalla libreria font oppure scegli un altro carattere.")
        rect = fitz.Rect(a.rect)
        rot = page.rotation
        args = (rect.width, rect.height, info.text, path, info.fontsize, info.text_color, info.fill, info.width, rot)
        ap = textbox.build_ap(self.doc, *args)           # invalida page/a: si rileggono
        self.doc.xref_set_key(xref, "AP", f"<< /N {ap} 0 R >>")

    def add_image(self, pno: int, rect, png_bytes: bytes, keep_ratio: bool = True) -> int:
        """Timbro con immagine (PNG con trasparenza supportata): firma olografica, logo, foto."""
        page = self.doc[pno]
        r = to_page_rect(page, rect)
        self._begin("immagine")
        a = page.add_stamp_annot(r, stamp=png_bytes)
        if not keep_ratio:
            a.set_rect(r)
        return a.xref

    def add_markup(self, pno: int, kind: str, rect) -> int:
        """Evidenzia/sottolinea/barra il testo contenuto nel rettangolo."""
        page = self.doc[pno]
        r = to_page_rect(page, rect)
        quads = self._quads_in_rect(page, r)
        if not quads:
            raise PdfError("nessun testo nell'area selezionata")
        self._begin("marcatura")
        if kind == "hl":
            a = page.add_highlight_annot(quads=quads)
        elif kind == "ul":
            a = page.add_underline_annot(quads=quads)
        else:
            a = page.add_strikeout_annot(quads=quads)
        a.update()
        return a.xref

    @staticmethod
    def _quads_in_rect(page: fitz.Page, r: fitz.Rect):
        quads = []
        for w in page.get_text("words"):
            wr = fitz.Rect(w[:4])
            inter = wr & r
            if not inter.is_empty and inter.get_area() >= 0.3 * wr.get_area():
                quads.append(wr.quad)
        return quads

    def text_in_rect(self, pno: int, rect) -> str:
        page = self.doc[pno]
        r = to_page_rect(page, rect)
        words = [w for w in page.get_text("words")
                 if not (fitz.Rect(w[:4]) & r).is_empty and (fitz.Rect(w[:4]) & r).get_area() >= 0.3 * fitz.Rect(w[:4]).get_area()]
        words.sort(key=lambda w: (w[5], w[6], w[7]))
        out, last = [], None
        for w in words:
            key = (w[5], w[6])
            if last is not None and key != last:
                out.append("\n")
            elif out:
                out.append(" ")
            out.append(w[4])
            last = key
        return "".join(out)

    def search(self, needle: str) -> list[tuple[int, fitz.Rect]]:
        res = []
        if not needle:
            return res
        for pno in range(self.page_count):
            page = self.doc[pno]
            for r in page.search_for(needle):
                res.append((pno, to_display_rect(page, r)))
        return res

    # ------------------------------------------------------------------ redazione
    def add_redact(self, pno: int, rect) -> int:
        page = self.doc[pno]
        r = to_page_rect(page, rect)
        self._begin("area di redazione")
        a = page.add_redact_annot(r, fill=(0, 0, 0))
        return a.xref

    def redact_at(self, pno: int, pt) -> Optional[int]:
        """xref del segno di redazione (non ancora applicato) sotto il punto, o None."""
        page = self.doc[pno]
        p = fitz.Point(pt)
        for a in page.annots():
            if a.type[0] == T_REDACT and p in to_display_rect(page, a.rect):
                return a.xref
        return None

    def pending_redactions(self) -> int:
        n = 0
        for page in self.doc:
            n += sum(1 for a in page.annots() if a.type[0] == T_REDACT)
        return n

    def apply_redactions(self, strip_metadata: bool = False) -> int:
        """Applica in modo permanente tutte le redazioni: rimuove testo, immagini e grafica sottostanti."""
        total = 0
        self._begin("applica redazioni")
        for page in self.doc:
            areas = [fitz.Rect(a.rect) for a in page.annots() if a.type[0] == T_REDACT]
            if areas:
                self._purge_under(page, areas)
                page.apply_redactions()
                try:                                    # l'anteprima incorporata della pagina mostrerebbe ancora il contenuto
                    self.doc.xref_set_key(page.xref, "Thumb", "null")
                except Exception:
                    pass
                total += len(areas)
        if total:
            self._mark_permanent()
            if strip_metadata:
                self._clear_metadata()
        return total

    # ------------------------------------------------------------------ metadati
    STD_META = ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate")
    _INFO_KEY = {"title": "Title", "author": "Author", "subject": "Subject", "keywords": "Keywords", "creator": "Creator",
                 "producer": "Producer", "creationDate": "CreationDate", "modDate": "ModDate"}

    def _info_xref(self, create: bool = False) -> int:
        k = self.doc.xref_get_key(-1, "Info")
        if k[0] == "xref":
            return int(k[1].split()[0])
        if not create:
            return 0
        x = self.doc.get_new_xref()
        self.doc.update_object(x, "<<>>")
        self.doc.xref_set_key(-1, "Info", f"{x} 0 R")
        return x

    def get_metadata(self) -> dict:
        """Metadati del documento: «standard» (campi Info), «custom» (altre chiavi Info), «xmp» (testo XML o stringa vuota)."""
        std = {k: (self.doc.metadata or {}).get(k) or "" for k in self.STD_META}
        custom = {}
        x = self._info_xref()
        if x:
            known = set(self._INFO_KEY.values()) | {"Trapped", "Trapped"}
            for key in self.doc.xref_get_keys(x):
                if key in known:
                    continue
                t, v = self.doc.xref_get_key(x, key)
                if t == "null":
                    continue
                custom[key] = _pdf_str_decode(v) if t == "string" else v
        try:
            xmp = self.doc.get_xml_metadata() or ""
        except Exception:
            xmp = ""
        return {"standard": std, "custom": custom, "xmp": xmp}

    def set_metadata(self, standard: dict, custom: dict, xmp: Optional[str] = None, remove_xmp: bool = False) -> None:
        """Imposta i campi standard e quelli personalizzati (le chiavi non presenti in `custom` vengono eliminate);
        `xmp`: nuovo blocco XMP; `remove_xmp`: elimina il blocco XMP."""
        self._begin("metadati")
        info = {k: (standard.get(k) or "") for k in self.STD_META}
        self.doc.set_metadata(info)
        x = self._info_xref(create=True)
        known = set(self._INFO_KEY.values()) | {"Trapped"}
        for key in list(self.doc.xref_get_keys(x)):
            if key not in known and key not in custom:
                self.doc.xref_set_key(x, key, "null")
        for key, val in custom.items():
            key = str(key).strip().replace(" ", "_")
            if not key or key in known:
                continue
            self.doc.xref_set_key(x, key, fitz.get_pdf_str(str(val)))
        if remove_xmp:
            try:
                self.doc.del_xml_metadata()
            except Exception:
                pass
        elif xmp is not None:
            self.doc.set_xml_metadata(xmp)

    def _clear_metadata(self) -> None:
        """Svuota tutti i metadati (Info, chiavi personalizzate, XMP) senza creare uno stato di annulla a sé."""
        self.doc.set_metadata({})
        x = self._info_xref()
        if x:
            for key in list(self.doc.xref_get_keys(x)):
                self.doc.xref_set_key(x, key, "null")
        try:
            self.doc.del_xml_metadata()
        except Exception:
            pass

    @staticmethod
    def make_xmp(std: dict) -> str:
        """Blocco XMP minimo coerente con i campi Info (titolo, autore, oggetto, parole chiave, creatore, produttore, date)."""
        from xml.sax.saxutils import escape as esc

        def lang(v):
            return f'<rdf:Alt><rdf:li xml:lang="x-default">{esc(v)}</rdf:li></rdf:Alt>'
        parts = []
        if std.get("title"):
            parts.append(f"<dc:title>{lang(std['title'])}</dc:title>")
        if std.get("author"):
            parts.append(f"<dc:creator><rdf:Seq><rdf:li>{esc(std['author'])}</rdf:li></rdf:Seq></dc:creator>")
        if std.get("subject"):
            parts.append(f"<dc:description>{lang(std['subject'])}</dc:description>")
        if std.get("keywords"):
            parts.append(f"<pdf:Keywords>{esc(std['keywords'])}</pdf:Keywords>")
        if std.get("producer"):
            parts.append(f"<pdf:Producer>{esc(std['producer'])}</pdf:Producer>")
        if std.get("creator"):
            parts.append(f"<xmp:CreatorTool>{esc(std['creator'])}</xmp:CreatorTool>")
        for key, tag in (("creationDate", "xmp:CreateDate"), ("modDate", "xmp:ModifyDate")):
            iso = pdf_date_to_iso(std.get(key) or "")
            if iso:
                parts.append(f"<{tag}>{iso}</{tag}>")
        return ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:pdf="http://ns.adobe.com/pdf/1.3/" '
                'xmlns:xmp="http://ns.adobe.com/xap/1.0/">' + "".join(parts) +
                '</rdf:Description></rdf:RDF></x:xmpmeta>\n<?xpacket end="w"?>')

    def document_info(self) -> list[tuple[str, str]]:
        """Informazioni di sola lettura sul documento (per la finestra dei metadati)."""
        d = self.doc
        out = [("Pagine", str(d.page_count)), ("Versione PDF", (d.metadata or {}).get("format", "")),
               ("Cifratura", str((d.metadata or {}).get("encryption") or "nessuna"))]
        if self.path and os.path.exists(self.path):
            out.append(("File", self.path)); out.append(("Dimensione su disco", f"{os.path.getsize(self.path):,} byte".replace(",", ".")))
        r = d[0].rect if d.page_count else None
        if r is not None:
            out.append(("Dimensione prima pagina", f"{r.width:.0f} × {r.height:.0f} pt ({r.width / 72 * 25.4:.0f} × {r.height / 72 * 25.4:.0f} mm)"))
        out.append(("Firme digitali", str(self.signed_count)))
        out.append(("Standard dichiarato", self.standard or "nessuno"))
        try:
            out.append(("Campi del modulo", str(self.count_fields())))
        except Exception:
            pass
        out.append(("Allegati incorporati", str(d.embfile_count())))
        out.append(("Segnalibri", str(len(d.get_toc()))))
        return out

    @staticmethod
    def _purge_under(page: fitz.Page, areas: list) -> None:
        """Elimina ciò che apply_redactions non tocca ma che conserva il testo sotto l'area: note/commenti con testo
        e campi di modulo compilati che si sovrappongono alle aree."""
        for w in list(page.widgets() or []):
            if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                continue
            if str(w.field_value or "").strip() and any(w.rect.intersects(a) for a in areas):
                page.delete_widget(w)
        for a in list(page.annots() or []):
            if a.type[0] in (T_REDACT, fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_WIDGET):
                continue
            info = a.info or {}
            if (info.get("content") or "").strip() and any(a.rect.intersects(r) for r in areas):
                page.delete_annot(a)

    # ------------------------------------------------------------------ modifica testo esistente
    def text_block_at(self, pno: int, pt) -> Optional[dict]:
        """Blocco di testo sotto il punto (coordinate di visualizzazione)."""
        page = self.doc[pno]
        p = to_page_pt(page, pt)
        best = None
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            r = fitz.Rect(b["bbox"])
            if p in r + (-2, -2, 2, 2):
                lines = [" ".join(s["text"] for s in l["spans"]).strip() for l in b["lines"]]
                spans = [s for l in b["lines"] for s in l["spans"] if s["text"].strip()]
                if not spans:
                    continue
                s0 = spans[0]
                col = s0["color"]
                color = (((col >> 16) & 255) / 255, ((col >> 8) & 255) / 255, (col & 255) / 255)
                info = {"rect": to_display_rect(page, r), "text": "\n".join(l for l in lines if l),
                        "fontsize": round(float(s0["size"]), 1),
                        "fontname": _font_from_span(s0["font"], s0["flags"]), "color": color}
                if best is None or r.get_area() < best[0]:
                    best = (r.get_area(), info)
        return best[1] if best else None

    def replace_text_block(self, pno: int, rect, new_text: str, fontsize: float, fontname: str,
                           color: Color, dest=None) -> None:
        """Sostituisce il testo di un blocco: rimuove il testo originale (solo testo) e scrive il nuovo
        (in `dest`, se indicato: sposta/ridimensiona il blocco)."""
        page = self.doc[pno]
        self._begin("modifica testo")
        self._mark_permanent()
        self._erase(page, to_page_rect(page, rect), text=True)
        r = to_page_rect(page, dest if dest is not None else rect)
        size = float(fontsize)
        kw = {}
        if fonts.is_custom(fontname):
            path = fonts.resolve(fontname)
            if not path:
                raise PdfError(f"Font «{fontname[1:]}» non disponibile.")
            kw = {"fontname": "PdfdeskF", "fontfile": path}
        else:
            kw = {"fontname": fontname}
        while size >= 4:
            if page.insert_textbox(r, new_text, fontsize=size, color=color, **kw) >= 0:
                return
            size -= 0.5
        page.insert_textbox(r + (0, 0, 0, 200), new_text, fontsize=4, color=color, **kw)


    # ------------------------------------------------------------------ oggetti del contenuto della pagina
    @staticmethod
    def _erase(page: fitz.Page, r: fitz.Rect, text=False, images=False, graphics=False) -> None:
        """Rimuove dal contenuto solo ciò che si chiede, senza toccare le aree di redazione già segnate dall'utente
        (che vengono messe da parte e rimesse dopo) e senza riempire l'area."""
        parked = [(fitz.Rect(a.rect), a.colors.get("fill")) for a in page.annots() if a.type[0] == T_REDACT]
        for a in list(page.annots()):
            if a.type[0] == T_REDACT:
                page.delete_annot(a)
        page.add_redact_annot(r, fill=False)
        page.apply_redactions(
            images=fitz.PDF_REDACT_IMAGE_REMOVE if images else fitz.PDF_REDACT_IMAGE_NONE,
            graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED if graphics else fitz.PDF_REDACT_LINE_ART_NONE,
            text=fitz.PDF_REDACT_TEXT_REMOVE if text else fitz.PDF_REDACT_TEXT_NONE)
        for rr, fill in parked:
            page.add_redact_annot(rr, fill=fill or (0, 0, 0))

    @classmethod
    def _erase_graphics(cls, page: fitz.Page, r: fitz.Rect, n_expected: int) -> None:
        """MuPDF considera «coperta» una curva solo se l'area contiene anche i punti di controllo: si allarga l'area
        a gradini finché l'oggetto sparisce davvero (i tentativi a vuoto non cancellano nulla)."""
        before = len(page.get_drawings())
        for pad in (0, 3, 8, 16, 30):
            cls._erase(page, r + (-pad, -pad, pad, pad), graphics=True)
            if len(page.get_drawings()) <= before - n_expected:
                return

    @staticmethod
    def _stroke_dist(d: dict, p: fitz.Point) -> float:
        segs = []
        for it in d["items"]:
            if it[0] == "l":
                segs.append((it[1], it[2]))
            elif it[0] == "c":
                pts = [fitz.Point(it[i]) for i in range(1, 5)]
                prev = pts[0]
                for k in range(1, 9):
                    t = k / 8
                    u = 1 - t
                    q = fitz.Point(u**3 * pts[0].x + 3*u*u*t * pts[1].x + 3*u*t*t * pts[2].x + t**3 * pts[3].x,
                                   u**3 * pts[0].y + 3*u*u*t * pts[1].y + 3*u*t*t * pts[2].y + t**3 * pts[3].y)
                    segs.append((prev, q))
                    prev = q
            elif it[0] == "re":
                r = fitz.Rect(it[1])
                cs = [r.tl, r.tr, r.br, r.bl]
                segs += [(cs[i], cs[(i + 1) % 4]) for i in range(4)]
            elif it[0] == "qu":
                q = it[1]
                cs = [q.ul, q.ur, q.lr, q.ll]
                segs += [(cs[i], cs[(i + 1) % 4]) for i in range(4)]
        best = 1e9
        for a, b in segs:
            a, b = fitz.Point(a), fitz.Point(b)
            dx, dy = b.x - a.x, b.y - a.y
            L = dx * dx + dy * dy
            t = 0 if L == 0 else max(0, min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L))
            best = min(best, math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy)))
        return best

    def content_at(self, pno: int, pt) -> Optional[dict]:
        """Oggetto del contenuto (testo, immagine o grafica vettoriale) sotto il punto, in coordinate di visualizzazione.
        Restituisce un dizionario con `kind` ('text', 'image', 'vector') e `rect` (coordinate di visualizzazione)."""
        page = self.doc[pno]
        blk = self.text_block_at(pno, pt)
        if blk:
            blk["kind"] = "text"
            return blk
        p = to_page_pt(page, pt)
        pr = page.rect
        cands = []
        try:
            draws = page.get_drawings()
        except Exception:
            draws = []
        for d in draws:
            r = fitz.Rect(d["rect"])
            if r.get_area() > 0.9 * pr.get_area():          # sfondo a tutta pagina: non si tocca per sbaglio
                continue
            w = float(d.get("width") or 0)
            tol = max(2.5, w / 2 + 1.5)
            filled = d.get("fill") is not None
            if filled:
                hit = p in (r + (-tol, -tol, tol, tol))
            else:
                hit = p in (r + (-tol, -tol, tol, tol)) and self._stroke_dist(d, p) <= tol
            if hit:
                pad = max(w / 2, 0.5) + 0.5
                inf = r + (-pad, -pad, pad, pad)
                group = [x for x in draws if x["rect"][0] >= inf.x0 and x["rect"][1] >= inf.y0
                         and x["rect"][2] <= inf.x1 and x["rect"][3] <= inf.y1]
                u = fitz.Rect(group[0]["rect"])
                for x in group[1:]:
                    u |= fitz.Rect(x["rect"])
                cands.append((max(r.get_area(), 1.0), {"kind": "vector", "draws": group, "page_rect": u,
                                                       "rect": to_display_rect(page, u + (-pad, -pad, pad, pad))}))
        for im in page.get_image_info(xrefs=True):
            r = fitz.Rect(im["bbox"])
            if im.get("xref") and p in r and r.get_area() < 0.98 * pr.get_area() * 4:
                cands.append((r.get_area(), {"kind": "image", "xref": im["xref"], "page_rect": r,
                                             "rect": to_display_rect(page, r)}))
        if not cands:
            return None
        return min(cands, key=lambda x: x[0])[1]

    def delete_content(self, pno: int, obj: dict) -> None:
        page = self.doc[pno]
        self._begin("elimina oggetto")
        self._mark_permanent()
        k = obj["kind"]
        if k == "text":
            self._erase(page, to_page_rect(page, obj["rect"]), text=True)
        elif k == "vector":
            self._erase_graphics(page, obj["page_rect"] + (-1.5, -1.5, 1.5, 1.5), len(obj["draws"]))
        elif k == "image":
            r = fitz.Rect(obj["page_rect"])
            ins = 1.0 if min(r.width, r.height) > 4 else 0.0
            self._erase(page, r + (ins, ins, -ins, -ins), images=True)

    def move_content(self, pno: int, obj: dict, new_rect) -> None:
        """Sposta/ridimensiona un oggetto del contenuto (new_rect in coordinate di visualizzazione)."""
        page = self.doc[pno]
        k = obj["kind"]
        if k == "text":
            self.replace_text_block(pno, obj["rect"], obj["text"], obj["fontsize"], obj["fontname"], obj["color"], dest=new_rect)
            return
        nr = to_page_rect(page, new_rect)
        old = fitz.Rect(obj["page_rect"])
        if k == "image":
            if page.rotation:
                raise PdfError("Lo spostamento delle immagini del PDF non è supportato sulle pagine ruotate.")
            xref = obj["xref"]
            d = self.doc.extract_image(xref)
            if not d:
                raise PdfError("Immagine non estraibile.")
            try:
                args = {"pixmap": imgutil.image_pixmap(self.doc, xref)}       # conserva ogni forma di trasparenza
            except Exception:
                args = {"stream": d["image"]}
            self._begin("sposta immagine")
            ins = 1.0 if min(old.width, old.height) > 4 else 0.0
            self._erase(page, old + (ins, ins, -ins, -ins), images=True)
            page.insert_image(nr, keep_proportion=False, **args)
            return
        # grafica vettoriale: si cancella e si ridisegna trasformata
        sx = nr.width / old.width if old.width > 0.01 else 1.0
        sy = nr.height / old.height if old.height > 0.01 else 1.0

        def m(pt):
            pt = fitz.Point(pt)
            return fitz.Point(nr.x0 + (pt.x - old.x0) * sx, nr.y0 + (pt.y - old.y0) * sy)

        self._begin("sposta grafica")
        self._erase_graphics(page, old + (-1.5, -1.5, 1.5, 1.5), len(obj["draws"]))
        for d in obj["draws"]:
            sh = page.new_shape()
            for it in d["items"]:
                t = it[0]
                if t == "l":
                    sh.draw_line(m(it[1]), m(it[2]))
                elif t == "c":
                    sh.draw_bezier(m(it[1]), m(it[2]), m(it[3]), m(it[4]))
                elif t == "re":
                    r = fitz.Rect(it[1])
                    sh.draw_rect(fitz.Rect(m(r.tl), m(r.br)).normalize())
                elif t == "qu":
                    q = it[1]
                    sh.draw_quad(fitz.Quad(m(q.ul), m(q.ur), m(q.ll), m(q.lr)))
            cap = d.get("lineCap")
            kw = dict(fill=d.get("fill"), color=d.get("color"), width=float(d.get("width") or 0) or 1.0,
                      even_odd=bool(d.get("even_odd")), closePath=bool(d.get("closePath")),
                      fill_opacity=d.get("fill_opacity", 1) if d.get("fill_opacity") is not None else 1,
                      stroke_opacity=d.get("stroke_opacity", 1) if d.get("stroke_opacity") is not None else 1,
                      lineCap=int(cap[0]) if isinstance(cap, (tuple, list)) and cap else 0,
                      lineJoin=int(d.get("lineJoin") or 0))
            dash = d.get("dashes")
            if dash and dash.strip() not in ("[] 0", "[] 0.0"):
                kw["dashes"] = dash
            sh.finish(**kw)
            sh.commit()

    # ------------------------------------------------------------------ lettura / modifica annotazioni
    @staticmethod
    def _find(page: fitz.Page, xref: int) -> Optional[fitz.Annot]:
        """L'oggetto pagina deve restare vivo finché si usa l'annotazione (riferimento debole in PyMuPDF)."""
        for a in page.annots():
            if a.xref == xref:
                return a
        return None

    def annot_info(self, pno: int, xref: int) -> Optional[AnnotInfo]:
        page = self.doc[pno]
        a = self._find(page, xref)
        return self._info(page, a) if a else None

    def _info(self, page: fitz.Page, a: fitz.Annot) -> AnnotInfo:
        t = a.type[0]
        cols = a.colors or {}
        info = AnnotInfo(xref=a.xref, type=t, kind=a.type[1], rect=to_display_rect(page, a.rect),
                         opacity=a.opacity if a.opacity is not None and a.opacity >= 0 else 1.0,
                         movable=t in RECT_TYPES or t in REBUILD_TYPES,
                         resizable=t in RECT_TYPES or t in REBUILD_TYPES)
        try:
            info.width = float(a.border.get("width", 1.0)) if a.border else 1.0
        except Exception:
            pass
        if t == T_FREETEXT:
            da = self.doc.xref_get_key(a.xref, "DA")[1]
            info.fontname, info.fontsize, info.text_color = _parse_da(da)
            info.text = a.info.get("content", "")
            info.fill = _rgb(cols.get("stroke")) if cols.get("stroke") else None
            info.stroke = info.text_color
            cf = self._custom_font(a.xref)
            if cf:
                info.fontname = "@" + cf
        else:
            info.stroke = _rgb(cols.get("stroke")) if cols.get("stroke") else None
            info.fill = _rgb(cols.get("fill")) if cols.get("fill") else None
        return info

    def list_annots(self, pno: int) -> list[AnnotInfo]:
        page = self.doc[pno]
        return [self._info(page, a) for a in page.annots()]

    def annot_at(self, pno: int, pt, tol: float = 3.0) -> Optional[int]:
        """xref dell'annotazione sotto il punto (coordinate di visualizzazione); la più piccola vince."""
        page = self.doc[pno]
        p = fitz.Point(pt)
        hits = []
        for i, a in enumerate(page.annots()):
            r = to_display_rect(page, a.rect) + (-tol, -tol, tol, tol)
            if p in r:
                hits.append((r.get_area(), -i, a.xref))
        if not hits:
            return None
        hits.sort()
        return hits[0][2]

    def delete_annot(self, pno: int, xref: int) -> bool:
        page = self.doc[pno]
        a = self._find(page, xref)
        if not a:
            return False
        self._begin("elimina annotazione")
        page.delete_annot(a)
        return True

    def set_props(self, pno: int, xref: int, *, stroke=None, fill="__keep__", width=None, opacity=None,
                  text=None, fontsize=None, fontname=None, text_color=None) -> int:
        page = self.doc[pno]
        a = self._find(page, xref)
        if not a:
            raise PdfError("annotazione non trovata")
        t = a.type[0]
        self._begin("proprietà")
        if t == T_FREETEXT:
            cur = self._info(page, a)
            if text is not None:
                a.set_info(content=text)
            if width is not None:
                a.set_border(width=float(width))
            fillc = cur.fill if fill == "__keep__" else fill
            tc = text_color or stroke or cur.text_color
            newfont = fontname or cur.fontname
            custom = fonts.is_custom(newfont)
            if custom:
                if not fonts.resolve(newfont):
                    raise PdfError(f"Font «{newfont[1:]}» non disponibile: aggiungilo dalla libreria font.")
            a.update(fontsize=float(fontsize or cur.fontsize), fontname="helv" if custom else newfont,
                     text_color=tc, fill_color=fillc, opacity=opacity if opacity is not None else cur.opacity)
            xr = a.xref
            if custom:
                self.doc.xref_set_key(xr, "PDFDeskFont", fitz.get_pdf_str(newfont[1:]))
                self._regen_custom(pno, xr)
            else:
                self.doc.xref_set_key(xr, "PDFDeskFont", "null")
            return xr
        else:
            if width is not None:
                a.set_border(width=float(width))
            kw = {}
            if stroke is not None:
                kw["stroke"] = stroke
            if fill != "__keep__" and t in (T_SQUARE, T_CIRCLE):
                kw["fill"] = list(fill) if fill else []
            if kw:
                a.set_colors(**kw)
            if opacity is not None:
                a.set_opacity(float(opacity))
            a.update()
        return a.xref

    def set_rect(self, pno: int, xref: int, new_rect) -> int:
        """Sposta/ridimensiona un'annotazione. Restituisce l'xref (cambia per tratti e linee, ricostruiti)."""
        page = self.doc[pno]
        a = self._find(page, xref)
        if not a:
            raise PdfError("annotazione non trovata")
        t = a.type[0]
        nr = to_page_rect(page, new_rect)
        if nr.width < 1 or nr.height < 1:
            nr = fitz.Rect(nr.x0, nr.y0, nr.x0 + max(nr.width, 1), nr.y0 + max(nr.height, 1))
        if t in RECT_TYPES:
            self._begin("sposta")
            old = fitz.Rect(a.rect)
            a.set_rect(nr)
            xr = a.xref
            if t == T_FREETEXT:
                if self._custom_font(xr):
                    same = abs(nr.width - old.width) < 0.01 and abs(nr.height - old.height) < 0.01
                    if not (same and not fonts.resolve("@" + self._custom_font(xr))):   # semplice spostamento: l'aspetto resta valido
                        self._regen_custom(pno, xr)
                else:
                    self._refresh_freetext(page, a)
            return xr
        if t in REBUILD_TYPES:
            return self._rebuild_vertices(page, a, nr)
        raise PdfError("questo tipo di annotazione non si può spostare")

    def _refresh_freetext(self, page: fitz.Page, a: fitz.Annot) -> None:
        info = self._info(page, a)
        a.update(fontsize=info.fontsize, fontname=info.fontname, text_color=info.text_color,
                 fill_color=info.fill, opacity=info.opacity)

    def _rebuild_vertices(self, page: fitz.Page, a: fitz.Annot, nr: fitz.Rect) -> int:
        old = fitz.Rect(a.rect)
        verts = a.vertices
        allp = [p for stroke in verts for p in stroke] if a.type[0] == T_INK else list(verts)
        vb = fitz.Rect(min(p[0] for p in allp), min(p[1] for p in allp),
                       max(p[0] for p in allp), max(p[1] for p in allp))
        # l'ingombro dell'annotazione include lo spessore del tratto: lo si conserva intorno ai punti
        padx = max((old.width - vb.width) / 2, 0.0)
        pady = max((old.height - vb.height) / 2, 0.0)
        tgt = fitz.Rect(nr.x0 + padx, nr.y0 + pady, max(nr.x1 - padx, nr.x0 + padx), max(nr.y1 - pady, nr.y0 + pady))
        sx = tgt.width / vb.width if vb.width > 1e-3 else 1.0
        sy = tgt.height / vb.height if vb.height > 1e-3 else 1.0

        def m(p):
            return (tgt.x0 + (p[0] - vb.x0) * sx, tgt.y0 + (p[1] - vb.y0) * sy)

        t = a.type[0]
        info = self._info(page, a)
        verts = a.vertices
        cols = a.colors or {}
        ends = a.line_ends if t == T_LINE else None
        blend = None
        try:
            blend = self.doc.xref_get_key(a.xref, "BM")[1]
        except Exception:
            pass
        self._begin("sposta")
        page.delete_annot(a)
        if t == T_INK:
            na = page.add_ink_annot([[m(p) for p in stroke] for stroke in verts])
        else:
            na = page.add_line_annot(m(verts[0]), m(verts[1]))
            if ends:
                na.set_line_ends(*ends)
        na.set_border(width=info.width)
        kw = {"stroke": cols.get("stroke") or (0, 0, 0)}
        if cols.get("fill"):
            kw["fill"] = cols["fill"]
        na.set_colors(**kw)
        if info.opacity < 0.999:
            na.set_opacity(info.opacity)
        if blend and "Multiply" in blend:
            try:
                na.set_blendmode("Multiply")
            except Exception:
                pass
        na.update()
        return na.xref

    # ------------------------------------------------------------------ pagine
    def rotate_pages(self, pnos: Sequence[int], delta: int) -> None:
        self._begin("ruota pagine")
        for p in pnos:
            pg = self.doc[p]
            pg.set_rotation((pg.rotation + delta) % 360)
        for p in pnos:                                  # le caselle di testo seguono la nuova orientazione della pagina
            self._realign_freetext(p)

    def _realign_freetext(self, pno: int) -> None:
        page = self.doc[pno]
        items = [(a.xref, bool(self._custom_font(a.xref))) for a in page.annots() or [] if a.type[0] == T_FREETEXT]
        for xref, custom in items:
            if custom:
                try:
                    self._regen_custom(pno, xref)
                except PdfError:
                    pass                                # font assente: resta l'aspetto salvato
            else:
                page = self.doc[pno]
                a = self._find(page, xref)
                a.set_rotation(page.rotation)
                self._refresh_freetext(page, a)

    def delete_pages(self, pnos: Sequence[int]) -> None:
        if len(set(pnos)) >= self.page_count:
            raise PdfError("non si possono eliminare tutte le pagine")
        self._begin("elimina pagine")
        self.doc.delete_pages(sorted(set(pnos)))

    def move_page(self, src: int, dest_before: int) -> None:
        self._begin("sposta pagina")
        self.doc.move_page(src, -1 if dest_before >= self.page_count else dest_before)

    def duplicate_page(self, pno: int) -> None:
        if not 0 <= pno < self.page_count:
            raise PdfError("pagina inesistente")
        self._begin("duplica pagina")
        self.doc.fullcopy_page(pno, pno + 1 if pno + 1 < self.page_count else -1)      # -1 = in fondo

    def insert_blank(self, after: int) -> None:
        w, h = self.page_size(min(max(after, 0), self.page_count - 1))
        pg = self.doc[min(max(after, 0), self.page_count - 1)]
        self._begin("pagina vuota")
        self.doc.new_page(pno=after + 1, width=pg.mediabox.width, height=pg.mediabox.height)

    def insert_pdf(self, path: str, after: int, password: Optional[str] = None) -> int:
        src = fitz.open(path)
        if src.needs_pass and not src.authenticate(password or ""):
            raise PasswordRequired(path)
        self._begin("inserisci PDF")
        self.doc.insert_pdf(src, start_at=after + 1)
        n = src.page_count
        src.close()
        return n

    def extract_pages(self, pnos: Sequence[int], path: str) -> None:
        out = fitz.open()
        for p in sorted(set(pnos)):
            out.insert_pdf(self.doc, from_page=p, to_page=p)
        out.save(path, garbage=3, deflate=True)
        out.close()

    # ------------------------------------------------------------------ uscita
    def current_bytes(self) -> bytes:
        """Stato corrente come PDF. Per i PDF firmati: salvataggio incrementale (firme intatte)."""
        self._pending_drop = False
        if self.is_signed and self.has_permanent_changes:
            # un salvataggio incrementale conserverebbe la revisione precedente con il contenuto eliminato:
            # si riscrive il file per intero senza le firme (ormai invalide). Il documento aperto resta com'è
            # (annulla compreso) finché il salvataggio non va a buon fine: vedi mark_saved().
            cur = fitz.open("pdf", self.doc.tobytes(garbage=0))
            for page in cur:
                for w in list(page.widgets() or []):
                    if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                        page.delete_widget(w)
            out = cur.tobytes(garbage=1, deflate=True)
            cur.close()
            self._pending_drop = True
            return out
        if self.is_signed:
            return self._signed_incremental()
        return self.doc.tobytes(garbage=1, deflate=True)

    def _signed_incremental(self) -> bytes:
        """PDF firmato: i byte originali (con le firme) + una nuova revisione con soltanto gli oggetti cambiati."""
        if not self._undo:                       # nessuna modifica (o tutto annullato): il file resta identico all'originale
            return self._orig
        import tempfile
        cur = fitz.open("pdf", self.doc.tobytes(garbage=0))
        fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="pdfdesk-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(self._orig)
            base = fitz.open(tmp)
            if base.needs_pass:
                base.authenticate(self._password or "")
            nb, nc = base.xref_length(), cur.xref_length()
            while base.xref_length() < nc:
                base.get_new_xref()

            def safe(fn, *a):
                try:
                    return fn(*a)
                except Exception:
                    return None
            def ident(doc, x):
                """Identità semantica dell'oggetto: insieme chiave/valore se è un dizionario (l'ordine delle chiavi non conta)."""
                keys = safe(doc.xref_get_keys, x) or []
                if keys:
                    return ("d", frozenset((k, tuple(safe(doc.xref_get_key, x, k) or ())) for k in keys))
                return ("t", safe(doc.xref_object, x, False))
            for x in range(1, nc):
                oc = safe(cur.xref_object, x, False)
                if oc is None or oc.strip() == "null":
                    continue                                     # contenitori (ObjStm, XRef) e oggetti eliminati: non si toccano
                if x < nb:
                    tb = safe(base.xref_get_key, x, "Type")
                    if tb and tb[1] in ("ObjStm", "XRef", "/ObjStm", "/XRef"):
                        continue
                st = bool(cur.xref_is_stream(x))
                sc = cur.xref_stream_raw(x) if st else None
                if x < nb and safe(base.xref_object, x, False) is not None:
                    sb = safe(base.xref_stream_raw, x) if safe(base.xref_is_stream, x) else None
                    if ident(cur, x) == ident(base, x) and sc == sb:
                        continue
                base.update_object(x, oc)
                if st:
                    base.update_stream(x, sc, new=True, compress=False)
            for key in ("Info", "Root"):               # metadati nuovi o radice cambiata
                v = safe(cur.xref_get_key, -1, key)
                if v and v[0] == "xref" and v != safe(base.xref_get_key, -1, key):
                    base.xref_set_key(-1, key, v[1])
            base.saveIncr()
            base.close()
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            cur.close()
            try:
                os.remove(tmp)
            except OSError:
                pass

    def mark_saved(self, path: str) -> None:
        if getattr(self, "_pending_drop", False) and self.is_signed:
            self.drop_signatures()               # il file salvato non ha più le firme: il documento aperto si allinea
        self._pending_drop = False
        self.path = os.path.abspath(path)
        self.modified = False
        self._destr = []
        self._redo_destr.clear()

    def drop_signatures(self) -> None:
        """Rimuove i campi firma (dopo una riscrittura completa non sarebbero più validi) e il blocco firmato."""
        for page in self.doc:
            for w in list(page.widgets() or []):
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    page.delete_widget(w)
        data = self.doc.tobytes(garbage=1, deflate=True)
        self.signed_count = 0
        self._orig = None
        self._replace_doc(data)
        self._undo.clear()
        self._redo.clear()
        self.modified = True


# ====================================================================== moduli (campi compilabili)
@dataclass
class FieldInfo:
    xref: int
    name: str
    kind: str              # text | checkbox | radio | combo | list | button | signature
    rect: fitz.Rect       # coordinate di visualizzazione
    value: object = ""     # str per testo/scelte, bool per caselle e opzioni
    choices: list = field(default_factory=list)
    multiline: bool = False
    readonly: bool = False
    maxlen: int = 0
    signed: bool = False
    password: bool = False


_KIND = {fitz.PDF_WIDGET_TYPE_TEXT: "text", fitz.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
         fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "radio", fitz.PDF_WIDGET_TYPE_COMBOBOX: "combo",
         fitz.PDF_WIDGET_TYPE_LISTBOX: "list", fitz.PDF_WIDGET_TYPE_BUTTON: "button",
         fitz.PDF_WIDGET_TYPE_SIGNATURE: "signature"}


def _field_info(page: fitz.Page, w: fitz.Widget) -> FieldInfo:
    kind = _KIND.get(w.field_type, "other")
    flags = w.field_flags or 0
    info = FieldInfo(xref=w.xref, name=w.field_name or "", kind=kind, rect=to_display_rect(page, w.rect),
                     readonly=bool(flags & 1), multiline=bool(flags & (1 << 12)) and kind == "text",
                     password=bool(flags & (1 << 13)) and kind == "text", maxlen=int(w.text_maxlen or 0))
    if kind in ("checkbox", "radio"):
        try:
            info.value = w.field_value not in (False, None, "", "Off", "off")
        except Exception:
            info.value = False
    elif kind == "signature":
        info.signed = bool(getattr(w, "is_signed", False))
    elif kind in ("combo", "list"):
        info.choices = [c if isinstance(c, str) else (c[-1] if c else "") for c in (w.choice_values or [])]
        info.value = w.field_value if isinstance(w.field_value, str) else (w.field_value[0] if w.field_value else "")
    else:
        v = w.field_value
        info.value = "" if v in (None, False) else str(v)
    return info


def _find_widget(page: fitz.Page, xref: int) -> Optional[fitz.Widget]:
    for w in page.widgets() or []:
        if w.xref == xref:
            return w
    return None


def _pdf_forms_api(cls):
    def has_form(self) -> bool:
        try:
            return bool(self.doc.is_form_pdf)
        except Exception:
            return False

    def list_fields(self, pno: int) -> list:
        if not self.has_form():
            return []
        page = self.doc[pno]
        return [_field_info(page, w) for w in page.widgets() or []]

    def count_fields(self) -> int:
        return sum(len(self.list_fields(p)) for p in range(self.page_count)) if self.has_form() else 0

    def field_at(self, pno: int, pt, tol: float = 1.0):
        p = fitz.Point(pt)
        hits = [f for f in self.list_fields(pno) if p in (f.rect + (-tol, -tol, tol, tol))]
        hits.sort(key=lambda f: f.rect.get_area())
        return hits[0] if hits else None

    def set_field(self, pno: int, xref: int, value) -> None:
        page = self.doc[pno]
        w = _find_widget(page, xref)
        if w is None:
            raise PdfError("campo non trovato")
        if (w.field_flags or 0) & 1:
            raise PdfError("campo di sola lettura")
        kind = _KIND.get(w.field_type)
        on = None
        if kind in ("checkbox", "radio") and value:
            try:
                on = w.on_state()
            except Exception:
                on = None
            if not on:
                raise PdfError("campo non valido: stato «attivo» non definito nel modulo")
        if kind == "text" and w.text_maxlen and len(str(value)) > w.text_maxlen:
            raise PdfError(f"massimo {w.text_maxlen} caratteri")
        if kind not in ("checkbox", "radio", "combo", "list", "text"):
            raise PdfError("questo campo non è compilabile")
        self._begin("compila campo")
        if kind == "checkbox":
            w.field_value = on if value else "Off"
            w.update()
        elif kind == "radio":
            if value:
                for o in page.widgets() or []:
                    if o.xref != w.xref and o.field_type == w.field_type and o.field_name == w.field_name:
                        o.field_value = "Off"
                        o.update()
                w = _find_widget(page, xref)
                w.field_value = on
                w.update()
            else:
                w.field_value = "Off"
                w.update()
        elif kind in ("combo", "list"):
            w.field_value = str(value)
            w.update()
        elif kind == "text":
            text = str(value)
            if w.text_maxlen and len(text) > w.text_maxlen:
                raise PdfError(f"massimo {w.text_maxlen} caratteri")
            w.field_value = text
            w.update()
        else:
            raise PdfError("questo campo non è compilabile")

    def flatten_forms(self) -> int:
        n = self.count_fields()
        if n == 0:
            return 0
        self._begin("appiattisci moduli")
        for p in self.doc:                                    # i campi firma vuoti non vanno disegnati («SIGN»): si tolgono
            for w in list(p.widgets() or []):
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and not getattr(w, "is_signed", False):
                    try:
                        p.delete_widget(w)
                    except Exception:
                        pass
        self.doc.bake(annots=False, widgets=True)
        return n

    for f in (has_form, list_fields, count_fields, field_at, set_field, flatten_forms):
        setattr(cls, f.__name__, f)
    return cls


_pdf_forms_api(PdfDocument)
