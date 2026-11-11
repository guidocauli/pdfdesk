# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# textbox.py: aspetto (appearance stream) delle caselle di testo con font TTF/OTF incorporato.
#
# La casella resta un'annotazione FreeText (spostabile, eliminabile, rieditabile) ma il suo aspetto è disegnato
# con il font scelto; nel PDF finisce solo il sottoinsieme di caratteri usati.
from __future__ import annotations

import html

import pymupdf as fitz


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v * 255))) for v in c)


# famiglie base-14 per il motore HTML e codici dei font nelle varianti, per misurare le parole
FAMILY = {"helv": "Helvetica", "tiro": "Times", "cour": "Courier"}
_VARIANT = {"helv": ("helv", "hebo", "heit", "hebi"), "tiro": ("tiro", "tibo", "tiit", "tibi"), "cour": ("cour", "cobo", "coit", "cobi")}


def base_code(code: str) -> str:
    """Riporta una variante (hebo, tiit, cobi…) al codice base (helv, tiro, cour)."""
    for base, vs in _VARIANT.items():
        if code in vs:
            return base
    return code if code in FAMILY else "helv"


def _wrap_long_words(text: str, fontbytes: bytes | None, size: float, avail: float, fontcode: str = "helv") -> str:
    """HTML del testo; le parole più larghe della casella sono spezzate (altrimenti il motore non scrive nulla)."""
    try:
        font = fitz.Font(fontbuffer=fontbytes) if fontbytes else fitz.Font(fontcode)
        width = lambda t: font.text_length(t, fontsize=size)
    except Exception:
        return html.escape(text).replace("\n", "<br>")
    out_lines = []
    for line in text.split("\n"):
        words = []
        for word in line.split(" "):
            if avail > 0 and width(word) > avail:
                chunk = ""
                parts = []
                for ch in word:
                    if chunk and width(chunk + ch) > avail:
                        parts.append(chunk)
                        chunk = ch
                    else:
                        chunk += ch
                parts.append(chunk)
                words.append("<br>".join(html.escape(p) for p in parts))
            else:
                words.append(html.escape(word))
        out_lines.append(" ".join(words))
    return "<br>".join(out_lines)


def build_ap(doc: fitz.Document, w: float, h: float, text: str, fontpath: str | None, fontsize: float,
             color, fill, border: float, rotation: int = 0, style: str = "", basefont: str = "helv") -> int:
    """Crea l'XObject di aspetto e ne restituisce l'xref.

    `fontpath`: file TTF/OTF, oppure None per un font base-14 (`basefont`: helv/tiro/cour). `style`: lettere tra
    b (grassetto), i (corsivo), u (sottolineato), s (barrato); grassetto e corsivo valgono solo per i font base-14.

    ATTENZIONE: aggiunge e rimuove una pagina di servizio, quindi gli oggetti Page/Annot già in mano al
    chiamante diventano non validi: vanno riletti dopo la chiamata.
    """
    rot = rotation % 360
    dw, dh = (h, w) if rot in (90, 270) else (w, h)          # la casella è disegnata nell'orientamento di lettura
    tmp = fitz.open()
    tall = dh + 3000                                          # il testo che non entra viene ritagliato, non perso
    tp = tmp.new_page(width=dw, height=tall)
    b = float(border or 0)
    if fill or b:
        tp.draw_rect(fitz.Rect(b / 2, b / 2, dw - b / 2, dh - b / 2), color=color if b else None, fill=fill, width=b)
    style = style or ""
    arch = None
    if fontpath:
        with open(fontpath, "rb") as f:
            fontbytes = f.read()
        arch = fitz.Archive()
        arch.add(fontbytes, "pdfdesk-font.ttf")
        css = "@font-face {font-family: PdfdeskFont; src: url(pdfdesk-font.ttf);} body {margin: 0; overflow-wrap: anywhere; word-wrap: break-word;}"
        family, bold, italic, measure = "PdfdeskFont", False, False, "helv"
    else:
        fontbytes = None
        base = base_code(basefont)
        bold, italic = "b" in style, "i" in style
        family = FAMILY[base]
        measure = _VARIANT[base][(1 if bold else 0) + (2 if italic else 0)]
        css = "body {margin: 0; overflow-wrap: anywhere; word-wrap: break-word;}"
    pad = 3 + b
    body = _wrap_long_words(text, fontbytes, float(fontsize), dw - 2 * pad - 1, measure)
    box = fitz.Rect(pad, pad, max(dw - pad, pad + 1), tall - pad)

    def markup(deco: str) -> str:
        inner = body
        if deco == "u":
            inner = f"<u>{inner}</u>"
        elif deco == "s":
            inner = f"<s>{inner}</s>"
        wt = "bold" if bold else "normal"
        it = "italic" if italic else "normal"
        return (f'<div style="font-family: {family}; font-weight: {wt}; font-style: {it}; font-size: {float(fontsize)}pt; '
                f'color: {_hex(color)}; line-height: 1.15;">{inner}</div>')
    kw = dict(css=css, scale_low=1)
    if arch is not None:
        kw["archive"] = arch
    # il motore HTML applica una sola decorazione per volta: con sottolineato + barrato il testo si disegna due volte
    for deco in [d for d in ("u", "s") if d in style] or [""]:
        tp.insert_htmlbox(box, markup(deco), **kw)
    scratch = doc.new_page(-1, width=w, height=h)
    scratch.show_pdf_page(fitz.Rect(0, 0, w, h), tmp, 0, clip=fitz.Rect(0, 0, dw, dh), rotate=rot)
    xref = scratch.get_xobjects()[0][0]
    doc.delete_page(doc.page_count - 1)
    tmp.close()
    return xref
