# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# export_fixed.py: esportazione DOCX/ODT/TXT fedele all'impaginazione del PDF.
# Ogni blocco di testo diventa un riquadro di testo (ancorato alla pagina) nella stessa posizione e con le stesse dimensioni,
# con le stesse interruzioni di riga, font, dimensione, colore; immagini, filetti e rettangoli sono riposizionati come nel PDF.
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from typing import Optional
from xml.sax.saxutils import escape, quoteattr

import pymupdf as fitz

from .export import Progress, Run, _CTRL, _NS_DOCX, _clean, _family, _image_bytes, _rgb, _tick

_EMU = 12700
_WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


@dataclass
class TBox:
    x: float; y: float; w: float; h: float
    lines: list                      # righe: ciascuna è una lista di Run
    pitch: float                     # passo tra le righe (pt)
    align: str = "left"


@dataclass
class IBox:
    x: float; y: float; w: float; h: float
    data: bytes; ext: str


@dataclass
class SBox:
    kind: str                        # "rect" | "line"
    x: float; y: float; w: float; h: float
    fill: Optional[str] = None
    stroke: Optional[str] = None
    width: float = 0.5
    flip_v: bool = False             # linee: dal basso a sinistra all'alto a destra
    flip_h: bool = False


@dataclass
class FPage:
    width: float
    height: float
    items: list = field(default_factory=list)       # SBox, IBox, TBox nell'ordine di sovrapposizione


def _hex(c) -> Optional[str]:
    if c is None:
        return None
    r, g, b = (max(0, min(255, int(round(v * 255)))) for v in (list(c) + [0, 0, 0])[:3])
    return f"{r:02X}{g:02X}{b:02X}"


_KNOWN = {"arial", "helvetica", "times new roman", "times", "courier new", "courier", "calibri", "cambria", "georgia", "verdana", "tahoma",
          "garamond", "palatino", "palatino linotype", "book antiqua", "century", "century gothic", "trebuchet ms", "comic sans ms",
          "segoe ui", "consolas", "lucida console", "dejavu sans", "dejavu serif", "liberation sans", "liberation serif", "noto sans",
          "noto serif", "open sans", "roboto", "symbol", "wingdings", "cambria math", "candara", "constantia", "corbel", "impact",
          "arial narrow", "arial black", "bookman old style", "franklin gothic", "gill sans mt", "rockwell"}


def _pdf_family(font: str, flags: int) -> str:
    fam = _family(font)
    if fam.lower() in _KNOWN:
        return fam
    if flags & 8 or "mono" in font.lower() or "courier" in font.lower():
        return "Courier New"
    if flags & 4 or "serif" in font.lower() and "sans" not in font.lower() or "times" in font.lower():
        return "Times New Roman"
    return "Arial"


def _runs_of(spans: list) -> list[Run]:
    runs: list[Run] = []
    for s in spans:
        t = _clean(s.get("text") or "")
        if not t:
            continue
        fl = s.get("flags", 0)
        font = s.get("font", "")
        r = Run(t, _pdf_family(font, fl), round(s.get("size", 11), 1), bool(fl & 16) or "bold" in font.lower(),
                bool(fl & 2) or "italic" in font.lower() or "oblique" in font.lower(), _rgb(s.get("color", 0)))
        if runs and (runs[-1].font, runs[-1].size, runs[-1].bold, runs[-1].italic, runs[-1].color) == \
                (r.font, r.size, r.bold, r.italic, r.color):
            runs[-1].text += r.text
        else:
            runs.append(r)
    if runs:
        runs[-1].text = runs[-1].text.rstrip()
        if not "".join(r.text for r in runs).strip():
            return []
    return runs


def _segments(ln: dict) -> list[list]:
    """Divide una riga in segmenti separati da grandi spazi orizzontali (celle di tabella, colonne sulla stessa riga)."""
    spans = [s for s in ln.get("spans", []) if (s.get("text") or "")]
    segs: list[list] = []
    for s in spans:
        if segs:
            prev = segs[-1][-1]
            gap = s["bbox"][0] - prev["bbox"][2]
            if gap > 1.5 * max(s.get("size", 10), prev.get("size", 10)):
                segs.append([s])
                continue
        if not segs:
            segs.append([s])
        else:
            segs[-1].append(s)
    return segs


def extract_fixed(doc: fitz.Document, pages: list[int], progress: Progress = None) -> list[FPage]:
    res: list[FPage] = []
    n = len(pages)
    for k, p in enumerate(pages):
        _tick(progress, k, n)
        page = doc[p]
        rm = page.rotation_matrix if page.rotation else None
        W, H = page.rect.width, page.rect.height

        def R(bb):
            r = fitz.Rect(bb)
            return (r * rm).normalize() if rm is not None else r

        fp = FPage(W, H)
        # filetti e rettangoli
        shapes: list[SBox] = []
        try:
            drawings = page.get_drawings()
        except Exception:
            drawings = []
        if len(drawings) <= 3000:
            for d in drawings:
                fill, col, wd = _hex(d.get("fill")), _hex(d.get("color")), float(d.get("width") or 0.5)
                for it in d.get("items", []):
                    if it[0] == "re":
                        r = R(it[1])
                        if fill and fill == "FFFFFF" and r.width * r.height > 0.85 * W * H:
                            continue
                        shapes.append(SBox("rect", r.x0, r.y0, r.width, r.height, fill, col, wd))
                    elif it[0] == "l" and col:
                        p1, p2 = fitz.Point(it[1]), fitz.Point(it[2])
                        if rm is not None:
                            p1, p2 = p1 * rm, p2 * rm
                        x0, x1 = sorted((p1.x, p2.x)); y0, y1 = sorted((p1.y, p2.y))
                        flip_v = (p2.x - p1.x) * (p2.y - p1.y) < 0
                        shapes.append(SBox("line", x0, y0, x1 - x0, y1 - y0, None, col, wd, flip_v=flip_v))
                    elif it[0] == "qu" and (fill or col):
                        r = R(fitz.Quad(it[1]).rect)
                        shapes.append(SBox("rect", r.x0, r.y0, r.width, r.height, fill, col, wd))
                if len(shapes) > 600:
                    break
        fp.items += shapes[:600]
        d = page.get_text("dict", sort=True)
        texts = []
        for b in d["blocks"]:
            bb = R(b["bbox"])
            if b["type"] == 1 and b.get("image"):
                data, ext = _image_bytes(b["image"], b.get("ext", ""))
                if data and bb.width > 2 and bb.height > 2:
                    fp.items.append(IBox(bb.x0, bb.y0, bb.width, bb.height, data, ext))
            elif b["type"] == 0:
                glines = [ln for ln in b["lines"] if _runs_of(ln.get("spans", []))]
                if not glines:
                    continue
                lb = [R(ln["bbox"]) for ln in glines]
                split = any(len(_segments(ln)) > 1 for ln in glines) or any(
                    abs(lb[i + 1].y0 - lb[i].y0) < 0.5 * min(lb[i].height, lb[i + 1].height) for i in range(len(lb) - 1))
                if split:                                 # tabelle / colonne in riga: un riquadro per ogni cella
                    for ln, lr in zip(glines, lb):
                        for seg in _segments(ln):
                            runs = _runs_of(seg)
                            if not runs:
                                continue
                            sr = R((min(x["bbox"][0] for x in seg), min(x["bbox"][1] for x in seg),
                                    max(x["bbox"][2] for x in seg), max(x["bbox"][3] for x in seg)))
                            extra = max(30.0, sr.width * 0.6)
                            texts.append(TBox(sr.x0, sr.y0, sr.width + extra, sr.height + 1, [runs], max(sr.height, 1.0), "left"))
                    continue
                lines = [_runs_of(ln.get("spans", [])) for ln in glines]
                if len(lb) > 1:
                    pitch = (lb[-1].y0 - lb[0].y0) / (len(lb) - 1)
                else:
                    pitch = lb[0].height
                pitch = max(pitch, 1.0)
                align = "left"
                cx = (bb.x0 + bb.x1) / 2
                if all(abs((l.x0 + l.x1) / 2 - cx) < 3 for l in lb) and abs(cx - W / 2) < W * 0.03 and bb.width < W * 0.8 and bb.x0 > W * 0.12:
                    align = "center"
                elif bb.x0 > W * 0.45 and bb.x1 > W * 0.8 and all(abs(l.x1 - bb.x1) < 3 for l in lb) and bb.width < W * 0.5:
                    align = "right"
                extra = max(30.0, bb.width * 0.6)
                x, w = bb.x0, bb.width + extra
                if align == "right":
                    x = max(0.0, bb.x0 - extra)
                    w = bb.x1 - x
                elif align == "center":
                    x, w = max(0.0, bb.x0 - extra / 2), bb.width + extra
                texts.append(TBox(x, bb.y0, w, bb.height + 1, lines, pitch, align))
        # le immagini stanno dietro il testo: già in ordine (shapes, immagini, testi)
        fp.items += texts
        res.append(fp)
    _tick(progress, n, n)
    return res


# ====================================================================== DOCX
def _drun(r: Run) -> str:
    props = f'<w:rFonts w:ascii={quoteattr(r.font)} w:hAnsi={quoteattr(r.font)} w:cs={quoteattr(r.font)}/>' if r.font else ""
    if r.bold:
        props += "<w:b/>"
    if r.italic:
        props += "<w:i/>"
    if r.color != "000000":
        props += f'<w:color w:val="{r.color}"/>'
    props += f'<w:sz w:val="{max(2, int(round(r.size * 2)))}"/>'
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{escape(r.text)}</w:t></w:r>'


def _anchor(idx: int, x: float, y: float, w: float, h: float, behind: bool, inner: str, name: str) -> str:
    cx, cy = max(1, int(w * _EMU)), max(1, int(h * _EMU))
    return (f'<w:r><w:drawing><wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="{idx}" '
            f'behindDoc="{1 if behind else 0}" locked="0" layoutInCell="1" allowOverlap="1"><wp:simplePos x="0" y="0"/>'
            f'<wp:positionH relativeFrom="page"><wp:posOffset>{int(x * _EMU)}</wp:posOffset></wp:positionH>'
            f'<wp:positionV relativeFrom="page"><wp:posOffset>{int(y * _EMU)}</wp:posOffset></wp:positionV>'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/>'
            f'<wp:docPr id="{idx}" name="{name} {idx}"/><wp:cNvGraphicFramePr/>{inner}</wp:anchor></w:drawing></w:r>')


def _wsp(cx: int, cy: int, geom: str, fill: Optional[str], stroke: Optional[str], width: float, content: str = "",
         flip_v: bool = False, txbox: bool = False) -> str:
    fl = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    ln = (f'<a:ln w="{max(1, int(width * _EMU))}"><a:solidFill><a:srgbClr val="{stroke}"/></a:solidFill></a:ln>' if stroke
          else "<a:ln><a:noFill/></a:ln>")
    flip = ' flipV="1"' if flip_v else ""
    tx = f"<wps:txbx><w:txbxContent>{content}</w:txbxContent></wps:txbx>" if content else ""
    body = ('<wps:bodyPr rot="0" vert="horz" wrap="square" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t" anchorCtr="0"><a:noAutofit/></wps:bodyPr>'
            if content else "<wps:bodyPr/>")
    return (f'<a:graphic><a:graphicData uri="{_WPS}"><wps:wsp><wps:cNvSpPr{" txBox=\"1\"" if txbox else ""}/>'
            f'<wps:spPr><a:xfrm{flip}><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="{geom}"><a:avLst/></a:prstGeom>'
            f'{fl}{ln}</wps:spPr>{tx}{body}</wps:wsp></a:graphicData></a:graphic>')


def export_docx_fixed(doc: fitz.Document, pages: list[int], target: str, progress: Progress = None) -> str:
    fpages = extract_fixed(doc, pages, progress)
    media: list[tuple[str, bytes]] = []
    rels: list[str] = []
    body: list[str] = []
    uid = 100
    for k, fp in enumerate(fpages):
        parts = []
        for it in fp.items:
            uid += 1
            if isinstance(it, SBox):
                geom = "line" if it.kind == "line" else "rect"
                inner = _wsp(max(1, int(it.w * _EMU)), max(1, int(it.h * _EMU)), geom, it.fill, it.stroke, it.width, flip_v=it.flip_v)
                parts.append(_anchor(uid, it.x, it.y, it.w, it.h, True, inner, "Forma"))
            elif isinstance(it, IBox):
                idx = len(media) + 1
                name = f"image{idx}.{it.ext}"
                media.append((name, it.data))
                rels.append(f'<Relationship Id="rIdImg{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>')
                cx, cy = max(1, int(it.w * _EMU)), max(1, int(it.h * _EMU))
                inner = (f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
                         f'<pic:nvPicPr><pic:cNvPr id="{uid}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
                         f'<pic:blipFill><a:blip r:embed="rIdImg{idx}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                         f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                         f'</pic:pic></a:graphicData></a:graphic>')
                parts.append(_anchor(uid, it.x, it.y, it.w, it.h, True, inner, "Immagine"))
            else:
                jc = {"center": '<w:jc w:val="center"/>', "right": '<w:jc w:val="right"/>'}.get(it.align, "")
                sp = f'<w:spacing w:before="0" w:after="0" w:line="{max(20, int(round(it.pitch * 20)))}" w:lineRule="exact"/>'
                runs = []
                for i, line in enumerate(it.lines):
                    if i:
                        runs.append("<w:r><w:br/></w:r>")
                    runs.append("".join(_drun(r) for r in line))
                para = f'<w:p><w:pPr>{sp}{jc}</w:pPr>{"".join(runs)}</w:p>'
                inner = _wsp(max(1, int(it.w * _EMU)), max(1, int(it.h * _EMU)), "rect", None, None, 0, para, txbox=True)
                parts.append(_anchor(uid, it.x, it.y, it.w, it.h, False, inner, "Testo"))
        sect = (f'<w:sectPr><w:pgSz w:w="{int(fp.width * 20)}" w:h="{int(fp.height * 20)}"/>'
                '<w:pgMar w:top="0" w:right="0" w:bottom="0" w:left="0" w:header="0" w:footer="0" w:gutter="0"/></w:sectPr>')
        last = k == len(fpages) - 1
        ppr = '<w:spacing w:before="0" w:after="0" w:line="20" w:lineRule="exact"/><w:rPr><w:sz w:val="2"/></w:rPr>' + ("" if last else sect)
        body.append(f'<w:p><w:pPr>{ppr}</w:pPr>{"".join(parts)}</w:p>')
        if last:
            final = sect
    first = fpages[0]
    ns = _NS_DOCX + f' xmlns:wps="{_WPS}"'
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns}><w:body>{"".join(body)}{final}</w:body></w:document>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style></w:styles>')
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
def _odt_text(t: str) -> str:
    """Testo ODT: gli spazi multipli e iniziali vanno espressi con <text:s/>; le tabulazioni con <text:tab/>."""
    def sp(m) -> str:
        n = len(m.group(0))
        return f'<text:s text:c="{n}"/>' if m.start() == 0 else (" " + (f'<text:s text:c="{n - 1}"/>' if n > 1 else ""))
    return re.sub(r" +", lambda m: sp(m) if (m.start() == 0 or len(m.group(0)) > 1) else " ", escape(t)).replace("\t", "<text:tab/>")


def export_odt_fixed(doc: fitz.Document, pages: list[int], target: str, progress: Progress = None) -> str:
    fpages = extract_fixed(doc, pages, progress)
    tstyles: dict[tuple, str] = {}
    pstyles: dict[tuple, str] = {}
    gstyles: dict[tuple, str] = {}
    sizes: dict[tuple, int] = {}
    media: list[tuple[str, bytes]] = []
    body: list[str] = []

    def ts(r: Run) -> str:
        key = (r.font, r.size, r.bold, r.italic, r.color)
        return tstyles.setdefault(key, f"T{len(tstyles) + 1}")

    def ps(align: str, pitch: float) -> str:
        key = (align, round(pitch, 1))
        return pstyles.setdefault(key, f"TP{len(pstyles) + 1}")

    def gs(kind: str, fill, stroke, width) -> str:
        key = (kind, fill, stroke, round(width, 2))
        return gstyles.setdefault(key, f"G{len(gstyles) + 1}")

    z = 0
    for k, fp in enumerate(fpages):
        sk = (round(fp.width, 1), round(fp.height, 1))
        sizes.setdefault(sk, len(sizes) + 1)
        parts = []
        for it in fp.items:
            z += 1
            pos = f'text:anchor-type="page" text:anchor-page-number="{k + 1}" draw:z-index="{z}"'
            if isinstance(it, SBox):
                st = gs(it.kind, it.fill, it.stroke, it.width)
                if it.kind == "line":
                    y1, y2 = (it.y + it.h, it.y) if it.flip_v else (it.y, it.y + it.h)
                    parts.append(f'<draw:line draw:style-name="{st}" {pos} svg:x1="{it.x:.2f}pt" svg:y1="{y1:.2f}pt" '
                                 f'svg:x2="{it.x + it.w:.2f}pt" svg:y2="{y2:.2f}pt"/>')
                else:
                    parts.append(f'<draw:rect draw:style-name="{st}" {pos} svg:x="{it.x:.2f}pt" svg:y="{it.y:.2f}pt" '
                                 f'svg:width="{it.w:.2f}pt" svg:height="{it.h:.2f}pt"/>')
            elif isinstance(it, IBox):
                name = f"Pictures/img{len(media) + 1}.{it.ext}"
                media.append((name, it.data))
                parts.append(f'<draw:frame draw:style-name="frI" {pos} svg:x="{it.x:.2f}pt" svg:y="{it.y:.2f}pt" svg:width="{it.w:.2f}pt" '
                             f'svg:height="{it.h:.2f}pt"><draw:image xlink:href="{name}" xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame>')
            else:
                pst = ps(it.align, it.pitch)
                lines = []
                for line in it.lines:
                    lines.append("".join(f'<text:span text:style-name="{ts(r)}">{_odt_text(r.text)}</text:span>' for r in line if r.text))
                txt = "<text:line-break/>".join(lines)
                parts.append(f'<draw:frame draw:style-name="frT" {pos} svg:x="{it.x:.2f}pt" svg:y="{it.y:.2f}pt" svg:width="{it.w:.2f}pt" '
                             f'svg:height="{it.h:.2f}pt"><draw:text-box><text:p text:style-name="{pst}">{txt}</text:p></draw:text-box></draw:frame>')
        body.append(f'<text:p text:style-name="Pg{sizes[sk]}{"b" if k else "a"}">{"".join(parts)}</text:p>')

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
    for (align, pitch), nm in pstyles.items():
        al = f' fo:text-align="{align}"' if align != "left" else ""
        auto.append(f'<style:style style:name="{nm}" style:family="paragraph"><style:paragraph-properties fo:margin="0pt" fo:line-height="{pitch}pt"{al}/></style:style>')
    for sk, i in sizes.items():
        for sfx, brk in (("a", ""), ("b", ' fo:break-before="page"')):
            auto.append(f'<style:style style:name="Pg{i}{sfx}" style:family="paragraph" style:master-page-name="MP{i}">'
                        f'<style:paragraph-properties fo:margin="0pt" fo:line-height="1pt"{brk}/><style:text-properties fo:font-size="1pt"/></style:style>')
    common = ('style:wrap="run-through" style:vertical-pos="from-top" style:vertical-rel="page" style:horizontal-pos="from-left" '
              'style:horizontal-rel="page" fo:padding="0pt" fo:border="none" ')
    auto.append(f'<style:style style:name="frT" style:family="graphic"><style:graphic-properties {common}style:run-through="foreground" draw:fill="none" '
                'draw:stroke="none" draw:auto-grow-height="false" draw:auto-grow-width="false" draw:textarea-vertical-align="top" '
                'fo:min-height="0pt"/></style:style>')
    auto.append(f'<style:style style:name="frI" style:family="graphic"><style:graphic-properties {common}style:run-through="background" '
                'draw:stroke="none"/></style:style>')
    for (kind, fill, stroke, width), nm in gstyles.items():
        st = (f'draw:stroke="solid" svg:stroke-width="{width}pt" svg:stroke-color="#{stroke}"' if stroke else 'draw:stroke="none"')
        fl = f'draw:fill="solid" draw:fill-color="#{fill}"' if fill else 'draw:fill="none"'
        auto.append(f'<style:style style:name="{nm}" style:family="graphic"><style:graphic-properties {common}style:run-through="background" {st} {fl}/></style:style>')
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
    layouts = "".join(
        f'<style:page-layout style:name="pm{i}"><style:page-layout-properties fo:page-width="{w:.2f}pt" fo:page-height="{h:.2f}pt" '
        'fo:margin-top="0pt" fo:margin-bottom="0pt" fo:margin-left="0pt" fo:margin-right="0pt"/></style:page-layout>'
        for (w, h), i in sizes.items())
    masters = "".join(f'<style:master-page style:name="MP{i}" style:page-layout-name="pm{i}"/>' for i in sizes.values())
    styles = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-styles {ns} office:version="1.2">'
              '<office:styles><style:default-style style:family="paragraph"><style:paragraph-properties fo:margin="0pt"/>'
              '<style:text-properties style:font-name="Arial" fo:font-size="11pt"/></style:default-style>'
              '<style:style style:name="Standard" style:family="paragraph" style:class="text"/></office:styles>'
              f'<office:automatic-styles>{layouts}</office:automatic-styles><office:master-styles>{masters}</office:master-styles>'
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
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/manifest.xml", manifest)
        zf.writestr("content.xml", content)
        zf.writestr("styles.xml", styles)
        zf.writestr("meta.xml", meta)
        for name, data in media:
            zf.writestr(name, data)
    return target


# ====================================================================== testo con impaginazione
def layout_text(page: fitz.Page) -> str:
    """Testo di una pagina mantenendo colonne, rientri e spaziature verticali (come `pdftotext -layout`)."""
    d = page.get_text("dict")
    rm = page.rotation_matrix if page.rotation else None
    lines = []                                           # (y_centro, x0, x1, altezza, testo)
    sizes = []
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            txt = _clean("".join(s.get("text", "") for s in ln.get("spans", [])))
            if not txt.strip():
                continue
            r = fitz.Rect(ln["bbox"])
            if rm is not None:
                r = (r * rm).normalize()
            sz = max((s.get("size", 10) for s in ln["spans"]), default=10)
            sizes.append((sz, len(txt)))
            lines.append((r.y0 + r.height / 2, r.x0, r.x1, r.height, txt.rstrip(), sz))
    if not lines:
        return ""
    tot = sum(n for _, n in sizes) or 1
    body = sorted(sizes)[len(sizes) // 2][0] if sizes else 10
    cw = max(3.0, body * 0.5)                           # larghezza di un carattere a passo fisso
    lines.sort(key=lambda t: (t[0], t[1]))
    rows: list[list] = []                                # righe visive (testi sulla stessa linea di base)
    for ln in lines:
        if rows and abs(rows[-1][0][0] - ln[0]) <= max(2.0, 0.45 * min(rows[-1][0][3], ln[3])):
            rows[-1].append(ln)
        else:
            rows.append([ln])
    minx = min(l[1] for l in lines)
    pitch = sorted(max(l[3] for l in r) for r in rows)[len(rows) // 2] or body * 1.2
    out: list[str] = []
    prev = None
    for r in rows:
        r.sort(key=lambda t: t[1])
        y = sum(l[0] for l in r) / len(r)
        if prev is not None:
            gap = y - prev
            out.extend([""] * max(0, int(round(gap / pitch)) - 1))
        prev = y
        s = ""
        for l in r:
            col = int(round((l[1] - minx) / cw))
            if col <= len(s):
                col = len(s) + (1 if s and not s.endswith(" ") else 0)
            s += " " * (col - len(s)) + l[4]
        out.append(s.rstrip())
    return "\n".join(out)
