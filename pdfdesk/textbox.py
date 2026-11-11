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


def _wrap_long_words(text: str, fontbytes: bytes, size: float, avail: float) -> str:
    """HTML del testo; le parole più larghe della casella sono spezzate (altrimenti il motore non scrive nulla)."""
    try:
        font = fitz.Font(fontbuffer=fontbytes)
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


def build_ap(doc: fitz.Document, w: float, h: float, text: str, fontpath: str, fontsize: float,
             color, fill, border: float, rotation: int = 0) -> int:
    """Crea l'XObject di aspetto e ne restituisce l'xref.

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
    with open(fontpath, "rb") as f:
        fontbytes = f.read()
    arch = fitz.Archive()
    arch.add(fontbytes, "pdfdesk-font.ttf")
    css = "@font-face {font-family: PdfdeskFont; src: url(pdfdesk-font.ttf);} body {margin: 0; overflow-wrap: anywhere; word-wrap: break-word;}"
    pad = 3 + b
    body = _wrap_long_words(text, fontbytes, float(fontsize), dw - 2 * pad - 1)
    box = fitz.Rect(pad, pad, max(dw - pad, pad + 1), tall - pad)
    markup = (f'<div style="font-family: PdfdeskFont; font-size: {float(fontsize)}pt; color: {_hex(color)}; '
              f'line-height: 1.15;">{body}</div>')
    tp.insert_htmlbox(box, markup, css=css, archive=arch, scale_low=1)
    scratch = doc.new_page(-1, width=w, height=h)
    scratch.show_pdf_page(fitz.Rect(0, 0, w, h), tmp, 0, clip=fitz.Rect(0, 0, dw, dh), rotate=rot)
    xref = scratch.get_xobjects()[0][0]
    doc.delete_page(doc.page_count - 1)
    tmp.close()
    return xref
