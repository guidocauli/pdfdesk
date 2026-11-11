# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# pdfstd.py: conformità agli standard di archiviazione e stampa (PDF/A-1b/2b/3b, PDF/X-1a/3/4).
#
# La conversione riscrive il documento con Ghostscript (font incorporati, spazi colore, trasparenze, profilo di
# destinazione) e poi completa metadati/riquadri con pikepdf. La verifica usa veraPDF per PDF/A quando è
# installato (variabile PDFDESK_VERAPDF o comando `verapdf`) e sempre un controllo interno, per PDF/A e PDF/X.
from __future__ import annotations

import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

import pikepdf
import pymupdf as fitz


class StandardError(Exception):
    pass


@dataclass(frozen=True)
class Standard:
    key: str
    label: str
    family: str            # "A" | "X"
    part: int              # A: 1/2/3 ; X: 1 (X-1a), 3 (X-3), 4 (X-4)
    conformance: str       # "B" per PDF/A, "" per PDF/X
    pdf_version: str       # CompatibilityLevel di Ghostscript
    transparency: bool     # trasparenze ammesse
    cmyk: bool             # destinazione CMYK (PDF/X) o RGB (PDF/A)
    note: str = ""


STANDARDS: dict[str, Standard] = {s.key: s for s in (
    Standard("pdfa-1b", "PDF/A-1b", "A", 1, "B", "1.4", False, False, "archiviazione a lungo termine (ISO 19005-1)"),
    Standard("pdfa-2b", "PDF/A-2b", "A", 2, "B", "1.7", True, False, "archiviazione, consente trasparenze (ISO 19005-2)"),
    Standard("pdfa-3b", "PDF/A-3b", "A", 3, "B", "1.7", True, False, "come A-2 e consente allegati (ISO 19005-3)"),
    Standard("pdfx-1a", "PDF/X-1a:2001", "X", 1, "", "1.3", False, True, "stampa: solo CMYK/grigi, senza trasparenze (ISO 15930-1)"),
    Standard("pdfx-3", "PDF/X-3:2002", "X", 3, "", "1.3", False, True, "stampa con colore gestito (ISO 15930-3)"),
    Standard("pdfx-4", "PDF/X-4", "X", 4, "", "1.6", True, True, "stampa moderna, con trasparenze (ISO 15930-7)"),
)}


# ---------------------------------------------------------------------- ricerca di Ghostscript
def _meipass() -> Optional[str]:
    return getattr(sys, "_MEIPASS", None)


def find_gs() -> Optional[str]:
    """Ghostscript incluso nel pacchetto, indicato da PDFDESK_GS, nel PATH o nelle cartelle di installazione note."""
    exe = "gswin64c.exe" if os.name == "nt" else "gs"
    cands = []
    mp = _meipass()
    if mp:
        cands += [os.path.join(mp, "gs", "bin", exe), os.path.join(mp, "gs", exe)]
    here = os.path.dirname(os.path.abspath(__file__))
    cands += [os.path.join(here, "..", "gs", "bin", exe)]
    env = os.environ.get("PDFDESK_GS")
    if env:
        cands.insert(0, env)
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    for name in ("gs", "gswin64c", "gswin32c", "gsc"):
        p = shutil.which(name)
        if p:
            return p
    for pat in (r"C:\Program Files\gs\gs*\bin\gswin64c.exe", r"C:\Program Files (x86)\gs\gs*\bin\gswin32c.exe",
                "/opt/homebrew/bin/gs", "/usr/local/bin/gs", "/Library/Frameworks/Ghostscript.framework/Versions/Current/bin/gs"):
        g = sorted(glob.glob(pat))
        if g:
            return g[-1]
    return None


def gs_available() -> bool:
    return find_gs() is not None


def _gs_env(gs: str) -> dict:
    env = dict(os.environ)
    base = os.path.dirname(os.path.dirname(gs))                 # .../gs/bin/gs -> .../gs
    share = os.path.join(base, "share")
    if os.path.isdir(share):                                    # copia inclusa nel pacchetto: percorsi di ricerca espliciti
        libs = [os.path.join(share, d) for d in ("Resource/Init", "lib", "Resource/Font", "Resource", "iccprofiles", "fonts")]
        env["GS_LIB"] = os.pathsep.join(p for p in libs if os.path.isdir(p))
        env["GS_FONTPATH"] = os.path.join(share, "fonts")
    return env


def _icc_dir(gs: str) -> Optional[str]:
    base = os.path.dirname(os.path.dirname(gs))
    # copia inclusa nel pacchetto, poi installazione di sistema: con e senza la cartella della versione (Homebrew recente
    # installa in share/ghostscript/iccprofiles, senza «10.x»), accanto all'eseguibile gs trovato e nei percorsi usuali
    fixed = [os.path.join(base, "share", "iccprofiles"), os.path.join(base, "share", "ghostscript", "iccprofiles"),
             os.path.join(base, "iccprofiles"), "/usr/share/color/icc/ghostscript", "/usr/share/ghostscript/iccprofiles",
             "/opt/homebrew/share/ghostscript/iccprofiles", "/usr/local/share/ghostscript/iccprofiles"]
    for p in fixed:
        if os.path.isfile(os.path.join(p, "srgb.icc")):
            return p
    for p in sorted(glob.glob(os.path.join(base, "share", "ghostscript", "*", "iccprofiles"))) \
            + sorted(glob.glob("/usr/share/ghostscript/*/iccprofiles")) + sorted(glob.glob("/opt/homebrew/share/ghostscript/*/iccprofiles")) \
            + sorted(glob.glob("/usr/local/share/ghostscript/*/iccprofiles")) + sorted(glob.glob(r"C:\Program Files\gs\gs*\iccprofiles")):
        if os.path.isfile(os.path.join(p, "srgb.icc")):
            return p
    return None


# ---------------------------------------------------------------------- riconoscimento
_RE_PART = re.compile(rb"pdfaid:part[>=\"'\s]+(\d)", re.I)
_RE_CONF = re.compile(rb"pdfaid:conformance[>=\"'\s]+([ABUabu])", re.I)
_RE_X = re.compile(rb"pdfxid:GTS_PDFXVersion[>=\"'\s]+([^<\"']+)", re.I)


def detect(data: bytes) -> Optional[str]:
    """Etichetta dello standard dichiarato dal file (es. «PDF/A-2b», «PDF/X-4»), oppure None.
    Dichiara soltanto: la conformità effettiva si verifica con check()."""
    try:
        with pikepdf.open(io.BytesIO(data)) as pdf:
            xmp = b""
            md = pdf.Root.get("/Metadata")
            if md is not None:
                xmp = bytes(md.read_bytes())
            m = _RE_PART.search(xmp)
            if m:
                c = _RE_CONF.search(xmp)
                return f"PDF/A-{m.group(1).decode()}{c.group(1).decode().lower() if c else ''}"
            m = _RE_X.search(xmp)
            if m:
                return m.group(1).decode().strip()
            v = pdf.docinfo.get("/GTS_PDFXVersion") if pdf.trailer.get("/Info") is not None else None
            if v is not None:
                return str(v)
    except Exception:
        return None
    return None


def detect_doc(doc: fitz.Document) -> Optional[str]:
    """Come detect(), ma su un documento già aperto (veloce: legge solo XMP e Info)."""
    try:
        xmp = (doc.get_xml_metadata() or "").encode("utf-8", "replace")
        m = _RE_PART.search(xmp)
        if m:
            c = _RE_CONF.search(xmp)
            return f"PDF/A-{m.group(1).decode()}{c.group(1).decode().lower() if c else ''}"
        m = _RE_X.search(xmp)
        if m:
            return m.group(1).decode().strip()
        t, v = doc.xref_get_key(-1, "Info")
        if t == "xref":
            ix = int(v.split()[0])
            t2, v2 = doc.xref_get_key(ix, "GTS_PDFXVersion")
            if t2 != "null":
                return v2.strip("()")
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------- conversione
def _ps_str(s: str) -> str:
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def _def_ps(std: Standard, icc: str, ncomp: int, title: str, ident: str, condition: str) -> str:
    s = "GTS_PDFA1" if std.family == "A" else "GTS_PDFX"
    extra = ""
    if std.family == "X":
        extra = f"/OutputCondition {_ps_str(condition)} "
    path = icc.replace("\\", "/")
    return (
        "%!\n"
        f"[ /Title {_ps_str(title)} /DOCINFO pdfmark\n"
        "[/_objdef {icc_out} /type /stream /OBJ pdfmark\n"
        f"[{{icc_out}} << /N {ncomp} >> /PUT pdfmark\n"
        f"[{{icc_out}} {_ps_str(path)} (r) file /PUT pdfmark\n"
        "[/_objdef {oi_out} /type /dict /OBJ pdfmark\n"
        f"[{{oi_out}} << /Type /OutputIntent /S /{s} /DestOutputProfile {{icc_out}} {extra}"
        f"/OutputConditionIdentifier {_ps_str(ident)} /Info {_ps_str(condition)} "
        "/RegistryName (http://www.color.org) >> /PUT pdfmark\n"
        "[{Catalog} << /OutputIntents [ {oi_out} ] >> /PUT pdfmark\n"
    )


def _mix(c, a: float):
    """Colore c con opacità a mescolato sul bianco (il fondo tipico della pagina)."""
    if not c:
        return c
    return tuple(a * v + (1 - a) for v in c)


def _flatten_annot_transparency(doc: fitz.Document) -> None:
    """Per gli standard senza trasparenze: evidenziazioni (fusione «Multiply») e opacità parziali diventano colori
    pieni equivalenti su fondo bianco, così Ghostscript non rasterizza la pagina."""
    for page in doc:
        for a in list(page.annots() or []):
            try:
                t = a.type[0]
                op = a.opacity if a.opacity is not None and a.opacity >= 0 else 1.0
                cols = a.colors or {}
                if t == fitz.PDF_ANNOT_HIGHLIGHT:
                    col = _mix(cols.get("stroke") or (1, 1, 0), op)
                    quads = a.vertices
                    for i in range(0, len(quads or []), 4):
                        r = fitz.Quad(quads[i:i + 4]).rect
                        page.draw_rect(r, color=None, fill=col, overlay=False)      # sotto il testo, come con Multiply
                    page.delete_annot(a)
                elif t in (fitz.PDF_ANNOT_UNDERLINE, fitz.PDF_ANNOT_STRIKE_OUT, fitz.PDF_ANNOT_SQUIGGLY):
                    a.set_colors(stroke=_mix(cols.get("stroke") or (0, 0, 0), op))
                    a.set_opacity(1)
                    a.update()
                elif op < 1 and t != fitz.PDF_ANNOT_STAMP:
                    a.set_colors(stroke=_mix(cols.get("stroke"), op) if cols.get("stroke") else None,
                                 fill=_mix(cols.get("fill"), op) if cols.get("fill") else None)
                    a.set_opacity(1)
                    a.update()
            except Exception:
                continue


def _flatten_image_alpha(doc: fitz.Document) -> None:
    """Immagini con canale alfa (PNG trasparenti, firme): composte su bianco, senza maschera."""
    try:
        from PIL import Image
    except Exception:
        return
    done = set()
    for page in doc:
        for img in page.get_images(full=True):
            xref, smask = img[0], img[1]
            if not smask or xref in done:
                continue
            done.add(xref)
            try:
                base = fitz.Pixmap(doc, xref)
                if base.colorspace is None or base.colorspace.n not in (1, 3):
                    base = fitz.Pixmap(fitz.csRGB, base)
                mask = fitz.Pixmap(doc, smask)
                if (mask.width, mask.height) != (base.width, base.height):
                    mask = fitz.Pixmap(mask, 0) if mask.alpha else mask
                    scaled = Image.frombytes("L", (mask.width, mask.height), mask.samples).resize((base.width, base.height))
                else:
                    scaled = Image.frombytes("L", (mask.width, mask.height), mask.samples)
                mode = "RGB" if base.colorspace.n == 3 else "L"
                rgb = Image.frombytes(mode, (base.width, base.height), base.samples if not base.alpha else fitz.Pixmap(base, 0).samples)
                bg = Image.new(mode, rgb.size, 255 if mode == "L" else (255, 255, 255))
                bg.paste(rgb, mask=scaled)
                buf = io.BytesIO()
                bg.save(buf, "PNG")
                page.replace_image(xref, stream=buf.getvalue())
            except Exception:
                continue


def _prepare(data: bytes, keep_attachments: bool, transparency: bool = True) -> bytes:
    """Prima di Ghostscript: appiattisce annotazioni e moduli (le annotazioni non conformi rovinerebbero lo standard),
    toglie azioni/JavaScript. Il testo resta testo."""
    try:
        doc = fitz.open("pdf", data)
    except Exception as e:
        raise StandardError("il file non è un PDF valido o è danneggiato") from e
    try:
        if doc.needs_pass:
            raise StandardError("documento protetto da password")
        try:
            sigs = sum(1 for p in doc for w in (p.widgets() or []) if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and getattr(w, "is_signed", False))
        except Exception:
            sigs = 0
        if sigs:
            raise StandardError("il documento contiene firme digitali: la conversione le invaliderebbe. "
                                "Converti prima e firma dopo (Firma → Firma digitale).")
        for p in doc:                                                  # i campi firma vuoti non hanno senso in un file archiviato
            for w in list(p.widgets() or []):
                if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE:
                    try:
                        p.delete_widget(w)
                    except Exception:
                        pass
        if not transparency:
            _flatten_annot_transparency(doc)
        try:
            doc.bake(annots=True, widgets=True)
        except Exception:
            pass
        if not transparency:
            _flatten_image_alpha(doc)
        try:
            doc.xref_set_key(doc.pdf_catalog(), "AA", "null")
            doc.xref_set_key(doc.pdf_catalog(), "OpenAction", "null")
        except Exception:
            pass
        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()



# ---------------------------------------------------------------------- correzioni dopo Ghostscript
_RE_BFCHAR = re.compile(rb"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>")
_RE_BFRANGE = re.compile(rb"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>")


def _tou_codes(cmap: bytes) -> dict:
    """Legge un ToUnicode e restituisce {codice: testo}."""
    out = {}
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", cmap, re.S):
        for a, b in _RE_BFCHAR.findall(block):
            out[int(a, 16)] = bytes.fromhex(b.decode()).decode("utf-16-be", "replace")
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", cmap, re.S):
        for a, b, c in _RE_BFRANGE.findall(block):
            lo, hi, base = int(a, 16), int(b, 16), bytes.fromhex(c.decode()).decode("utf-16-be", "replace")
            for i in range(lo, min(hi, lo + 65535) + 1):
                out[i] = base[:-1] + chr(ord(base[-1]) + (i - lo)) if base else ""
    return out


def _make_tou(mapping: dict) -> bytes:
    lines = ["/CIDInit /ProcSet findresource begin", "12 dict begin", "begincmap", "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
             "/CMapName /Adobe-Identity-UCS def", "/CMapType 2 def", "1 begincodespacerange", "<0000> <FFFF>", "endcodespacerange"]
    items = sorted(mapping.items())
    for i in range(0, len(items), 100):
        chunk = items[i:i + 100]
        lines.append(f"{len(chunk)} beginbfchar")
        lines += [f"<{c:04X}> <{t.encode('utf-16-be').hex().upper()}>" for c, t in chunk]
        lines.append("endbfchar")
    lines += ["endcmap", "CMapName currentdict /CMap defineresource pop", "end", "end"]
    return ("\n".join(lines) + "\n").encode("ascii")


def _fix_tounicode(pdf: pikepdf.Pdf) -> int:
    """Ghostscript 10.02 scrive mappature ToUnicode sbagliate per cirillico & co. nei font TrueType/OpenType incorporati.
    Si ricostruiscono dai nomi dei glifi del font (AGL / uniXXXX). Restituisce il numero di font corretti."""
    try:
        from fontTools.agl import toUnicode
        from fontTools.ttLib import TTFont
    except Exception:
        return 0
    fixed = 0
    seen = set()
    for obj in pdf.objects:
        try:
            if not isinstance(obj, pikepdf.Dictionary) or obj.get("/Subtype") != "/Type0" or "/ToUnicode" not in obj:
                continue
            if obj.objgen in seen:
                continue
            seen.add(obj.objgen)
            fd = obj.DescendantFonts[0].get("/FontDescriptor")
            ff = fd.get("/FontFile2") if fd is not None else None
            if ff is None:
                ff = fd.get("/FontFile3") if fd is not None else None
            if ff is None:
                continue
            tt = TTFont(io.BytesIO(ff.read_bytes()), lazy=True)
            order = tt.getGlyphOrder()
            old = _tou_codes(obj.ToUnicode.read_bytes())
            new, changed = {}, False
            for code, txt in old.items():
                name = order[code] if 0 <= code < len(order) else ""
                u = toUnicode(name) if name and not re.fullmatch(r"(glyph|g|cid|gid)\d+|\.notdef|\.null", name) else ""
                if u and u != txt:
                    new[code], changed = u, True
                else:
                    new[code] = txt
            if changed:
                obj["/ToUnicode"] = pdf.make_stream(_make_tou(new))
                fixed += 1
        except Exception:
            continue
    return fixed


def _collect_links(data: bytes) -> list:
    """Collegamenti ipertestuali delle pagine non ruotate: [(pagina, x0, y0, x1, y1 [PDF], tipo, valore)]."""
    links = []
    doc = fitz.open("pdf", data)
    try:
        for p in doc:
            if p.rotation or p.cropbox != p.mediabox:
                continue
            h = p.mediabox.height
            for l in p.get_links():
                r = l["from"]
                box = (r.x0, h - r.y1, r.x1, h - r.y0)
                if l.get("kind") == fitz.LINK_URI and l.get("uri"):
                    links.append((p.number, box, "uri", l["uri"]))
                elif l.get("kind") == fitz.LINK_GOTO and l.get("page", -1) >= 0:
                    to = l.get("to") or fitz.Point(0, 0)
                    links.append((p.number, box, "goto", (l["page"], to.x, h - to.y)))
    finally:
        doc.close()
    return links


def _restore_links(pdf: pikepdf.Pdf, links: list) -> int:
    n = 0
    for pno, box, kind, val in links:
        try:
            page = pdf.pages[pno]
            ann = pikepdf.Dictionary(Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link, Rect=list(box), Border=[0, 0, 0], F=4)
            if kind == "uri":
                ann["/A"] = pikepdf.Dictionary(S=pikepdf.Name.URI, URI=pikepdf.String(val))
            else:
                tp, x, y = val
                ann["/Dest"] = pikepdf.Array([pdf.pages[tp].obj, pikepdf.Name.XYZ, x, y, None])
            arr = page.obj.get("/Annots")
            if arr is None:
                page.obj["/Annots"] = pikepdf.Array()
                arr = page.obj["/Annots"]
            arr.append(pdf.make_indirect(ann))
            n += 1
        except Exception:
            continue
    return n


def convert(data: bytes, key: str, icc_profile: Optional[str] = None, condition: str = "", title: str = "",
            keep_attachments: bool = False, runner=None) -> bytes:
    """Converte il PDF allo standard richiesto e restituisce i nuovi byte. Solleva StandardError."""
    std = STANDARDS.get(key)
    if std is None:
        raise StandardError(f"standard sconosciuto: {key}")
    gs = find_gs()
    if not gs:
        raise StandardError("Ghostscript non trovato. È incluso nei pacchetti ufficiali; da sorgente installalo "
                            "(apt install ghostscript, brew install ghostscript, oppure ghostscript.com) o imposta PDFDESK_GS.")
    icc_dir = _icc_dir(gs)
    if icc_profile and not os.path.isfile(icc_profile):
        raise StandardError("profilo ICC non trovato")
    if not icc_profile:
        if not icc_dir:
            raise StandardError("profili colore di Ghostscript non trovati")
        icc_profile = os.path.join(icc_dir, "default_cmyk.icc" if std.cmyk else "srgb.icc")
    ncomp = 4 if std.cmyk else 3
    try:                                                          # numero di componenti dal profilo scelto
        with open(icc_profile, "rb") as f:
            head = f.read(24)
        space = head[16:20]
        ncomp = {b"CMYK": 4, b"RGB ": 3, b"GRAY": 1}.get(space, ncomp)
    except OSError as e:
        raise StandardError(f"profilo ICC illeggibile: {e}") from e
    if std.family == "A" and ncomp != 3:
        raise StandardError("per PDF/A serve un profilo RGB (la conversione porta il documento in RGB)")
    if std.family == "X" and ncomp not in (4, 1):
        raise StandardError("per PDF/X serve un profilo di stampa CMYK (o in scala di grigi)")
    src = _prepare(data, keep_attachments, std.transparency)
    links = _collect_links(src) if std.family == "A" else []        # in PDF/X le annotazioni stampabili sono vietate
    ident = os.path.splitext(os.path.basename(icc_profile))[0]
    cond = condition or ("sRGB IEC61966-2.1" if std.family == "A" else ident)
    tmp = tempfile.mkdtemp(prefix="pdfdesk-std-")
    try:
        pin, pout, pdef = (os.path.join(tmp, n) for n in ("in.pdf", "out.pdf", "def.ps"))
        with open(pin, "wb") as f:
            f.write(src)
        with open(pdef, "w", encoding="latin-1", errors="replace") as f:
            f.write(_def_ps(std, icc_profile, ncomp, title or "Documento", ident, cond))
        args = [gs, "-dBATCH", "-dNOPAUSE", "-dQUIET", "-sDEVICE=pdfwrite", f"-dCompatibilityLevel={std.pdf_version}",
                "-dEmbedAllFonts=true", "-dSubsetFonts=true", "-dPDFSETTINGS=/prepress", "-dAutoRotatePages=/None",
                "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
                "-dColorImageFilter=/FlateEncode", "-dGrayImageFilter=/FlateEncode", "-dAutoFilterColorImages=false",
                "-dAutoFilterGrayImages=false", "-dPreserveAnnots=true",
                f"--permit-file-read={icc_profile}", f"--permit-file-read={pdef}", f"-sOutputFile={pout}"]
        if std.family == "A":
            args += [f"-dPDFA={std.part}", "-dPDFACompatibilityPolicy=1", "-sColorConversionStrategy=RGB", "-sProcessColorModel=DeviceRGB"]
        else:
            args += [f"-sColorConversionStrategy={'Gray' if ncomp == 1 else 'CMYK'}",
                     f"-sProcessColorModel={'DeviceGray' if ncomp == 1 else 'DeviceCMYK'}"]
        args += [pdef, pin]
        call = lambda: subprocess.run(args, capture_output=True, env=_gs_env(gs), timeout=900,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        r = runner(call) if runner else call()          # runner: l'interfaccia esegue la parte lunga in un thread
        if r.returncode != 0 or not os.path.isfile(pout) or os.path.getsize(pout) == 0:
            msg = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()[-400:]
            raise StandardError(f"Ghostscript non è riuscito a convertire il documento: {msg or 'errore sconosciuto'}")
        with open(pout, "rb") as f:
            out = f.read()
    except subprocess.TimeoutExpired as e:
        raise StandardError("conversione troppo lunga (oltre 15 minuti)") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _finalize(out, std, title, cond, links)


def _xmp(std: Standard, title: str, producer: str) -> bytes:
    from xml.sax.saxutils import escape
    t = escape(title or "Documento")
    if std.family == "X":
        ver = {1: "PDF/X-1a:2001", 3: "PDF/X-3:2002", 4: "PDF/X-4"}[std.part]
        conf = '\n   <pdfx:GTS_PDFXConformance>PDF/X-1a:2001</pdfx:GTS_PDFXConformance>' if std.part == 1 else ""
        extra = (f'<rdf:Description rdf:about="" xmlns:pdfxid="http://www.npes.org/pdfx/ns/id/">\n'
                 f'   <pdfxid:GTS_PDFXVersion>{ver}</pdfxid:GTS_PDFXVersion>\n  </rdf:Description>\n'
                 f'  <rdf:Description rdf:about="" xmlns:pdfx="http://ns.adobe.com/pdfx/1.3/">\n'
                 f'   <pdfx:GTS_PDFXVersion>{ver}</pdfx:GTS_PDFXVersion>{conf}\n  </rdf:Description>\n')
    else:
        extra = ""
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{t}</rdf:li></rdf:Alt></dc:title>\n  </rdf:Description>\n'
        '  <rdf:Description rdf:about="" xmlns:pdf="http://ns.adobe.com/pdf/1.3/">\n'
        f'   <pdf:Producer>{escape(producer)}</pdf:Producer>\n  </rdf:Description>\n'
        f'  {extra}'
        ' </rdf:RDF>\n</x:xmpmeta>\n<?xpacket end="w"?>').encode("utf-8")


def _finalize(data: bytes, std: Standard, title: str, condition: str, links: Optional[list] = None) -> bytes:
    """Completa quello che Ghostscript non scrive o scrive male: ToUnicode, collegamenti, metadati e riquadri PDF/X."""
    import datetime
    with pikepdf.open(io.BytesIO(data)) as pdf:
        _fix_tounicode(pdf)
        if links:
            _restore_links(pdf, links)
        if std.family == "X":
            info = pdf.docinfo
            if not str(info.get("/Title", "")).strip():
                info["/Title"] = title or "Documento"
            now = datetime.datetime.now(datetime.timezone.utc).strftime("D:%Y%m%d%H%M%S+00'00'")
            for k in ("/CreationDate", "/ModDate"):
                if k not in info:
                    info[k] = now
            info["/Trapped"] = pikepdf.Name("/False")
            ver = {1: "PDF/X-1:2001", 3: "PDF/X-3:2002", 4: "PDF/X-4"}[std.part]
            info["/GTS_PDFXVersion"] = ver
            if std.part == 1:
                info["/GTS_PDFXConformance"] = "PDF/X-1a:2001"
            info["/Producer"] = "PDFDesk — Guido Cauli <guido.cauli@gmail.com> + Ghostscript"
            for page in pdf.pages:
                if "/TrimBox" not in page and "/ArtBox" not in page:
                    page["/TrimBox"] = list(page.MediaBox)
                if "/BleedBox" not in page:
                    page["/BleedBox"] = list(page.MediaBox)
                if "/Annots" in page.obj:        # in stampa i collegamenti non servono e le annotazioni stampabili sono vietate
                    del page.obj["/Annots"]
            pdf.Root["/Metadata"] = pdf.make_stream(_xmp(std, str(info["/Title"]), str(info["/Producer"])))
            pdf.Root.Metadata["/Type"] = pikepdf.Name("/Metadata")
            pdf.Root.Metadata["/Subtype"] = pikepdf.Name("/XML")
        out = io.BytesIO()
        ver = std.pdf_version if std.family == "X" else None
        pdf.save(out, object_stream_mode=pikepdf.ObjectStreamMode.disable, compress_streams=True, deterministic_id=False,
                 fix_metadata_version=False,        # evita il parser XMP di pikepdf (richiede lxml, non incluso nel pacchetto)
                 **({"min_version": ver, "force_version": ver} if ver else {}))
        return out.getvalue()


# ---------------------------------------------------------------------- verifica
@dataclass
class Report:
    standard: str
    declared: Optional[str]
    ok: bool
    issues: list = field(default_factory=list)       # (gravità, testo)
    validator: str = "controllo interno"

    def text(self) -> str:
        head = f"{self.standard}: {'CONFORME' if self.ok else 'NON conforme'} ({self.validator})"
        return "\n".join([head] + [f"- {s}: {t}" for s, t in self.issues])


def find_verapdf() -> Optional[str]:
    env = os.environ.get("PDFDESK_VERAPDF")
    if env and os.path.isfile(env):
        return env
    return shutil.which("verapdf") or (("/opt/verapdf/verapdf") if os.path.isfile("/opt/verapdf/verapdf") else None)


def _verapdf(data: bytes, std: Standard) -> Optional[list]:
    exe = find_verapdf()
    if not exe or std.family != "A":
        return None
    flavour = f"{std.part}{std.conformance.lower()}"
    with tempfile.TemporaryDirectory(prefix="pdfdesk-vera-") as d:
        p = os.path.join(d, "f.pdf")
        with open(p, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run([exe, "--flavour", flavour, "--format", "xml", "--maxfailuresdisplayed", "30", p],
                               capture_output=True, timeout=300)
        except Exception:
            return None
    try:
        root = ET.fromstring(r.stdout.decode("utf-8", "replace"))
    except ET.ParseError:
        return None
    issues = []
    for rule in root.iter("rule"):
        if rule.get("status") == "failed":
            desc = (rule.findtext("description") or "").strip()
            issues.append(("errore", f"{rule.get('specification', '')} {rule.get('clause', '')}: {desc}".strip()))
    comp = any(v.get("isCompliant") == "true" for v in root.iter("validationReport"))
    return [comp, issues]


def _xobject_has_transparency(pdf: pikepdf.Pdf) -> list:
    out = []
    for page in pdf.pages:
        grp = page.obj.get("/Group")
        if grp is not None and grp.get("/S") == "/Transparency":
            out.append("gruppo di trasparenza sulla pagina")
    seen = set()
    for obj in pdf.objects:
        try:
            if not isinstance(obj, pikepdf.Dictionary) and not isinstance(obj, pikepdf.Stream):
                continue
            if "/SMask" in obj and obj.get("/SMask") != pikepdf.Name("/None"):
                out.append("maschera di trasparenza (SMask)")
            if "/ca" in obj and float(obj.get("/ca")) < 1 or "/CA" in obj and float(obj.get("/CA")) < 1:
                out.append("opacità inferiore al 100%")
            bm = obj.get("/BM")
            if bm is not None and str(bm) not in ("/Normal", "/Compatible"):
                out.append("modo di fusione non normale")
        except Exception:
            continue
    return sorted(set(out))


def _unembedded_fonts(pdf) -> set:
    """Nomi dei font non incorporati in qualunque punto del file (pagine, aspetto delle annotazioni e dei campi, XObject)."""
    bad = set()
    for obj in pdf.objects:
        try:
            if not isinstance(obj, pikepdf.Dictionary) or obj.get("/Type") != "/Font":
                continue
            sub = str(obj.get("/Subtype", ""))
            if sub == "/Type3":
                continue
            f = obj
            if sub == "/Type0":
                desc = obj.get("/DescendantFonts")
                if not desc or len(desc) == 0:
                    continue
                f = desc[0]
            fd = f.get("/FontDescriptor")
            if fd is None or not any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                bad.add(str(obj.get("/BaseFont", "?")).lstrip("/"))
        except Exception:
            continue
    return bad


def check(data: bytes, key: str) -> Report:
    """Verifica la conformità allo standard indicato. Per PDF/A usa veraPDF se disponibile, più il controllo interno."""
    std = STANDARDS[key]
    declared = detect(data)
    issues: list = []
    try:
        pdf = pikepdf.open(io.BytesIO(data))
    except Exception as e:
        return Report(std.label, declared, False, [("errore", f"file non leggibile: {e}")])
    with pdf:
        if pdf.is_encrypted:
            issues.append(("errore", "documento cifrato"))
        root = pdf.Root
        if "/OutputIntents" not in root or len(root.OutputIntents) == 0:
            issues.append(("errore", "manca l'OutputIntent (profilo colore di destinazione)"))
        else:
            sub = str(root.OutputIntents[0].get("/S", ""))
            want = "/GTS_PDFA1" if std.family == "A" else "/GTS_PDFX"
            if sub != want:
                issues.append(("errore", f"OutputIntent di tipo {sub}, atteso {want}"))
            if "/DestOutputProfile" not in root.OutputIntents[0] and std.family == "A":
                issues.append(("errore", "OutputIntent senza profilo ICC incorporato"))
        if "/Metadata" not in root:
            issues.append(("errore", "mancano i metadati XMP"))
        if "/AA" in root or "/JavaScript" in (root.get("/Names") or {}):
            issues.append(("errore", "JavaScript o azioni automatiche presenti"))
        nf = _unembedded_fonts(pdf)                  # tutti i font del file, anche nelle annotazioni (non solo nelle pagine)
        if nf:
            issues.append(("errore", "font non incorporati: " + ", ".join(sorted(nf)[:6])))
        if std.family == "A":
            want = f"PDF/A-{std.part}{std.conformance.lower()}"
            if declared != want:
                issues.append(("errore", f"il file dichiara «{declared or 'nessuno standard'}», atteso {want}"))
            if std.part < 3 and "/Names" in root and "/EmbeddedFiles" in root.Names:
                issues.append(("errore", "allegati non ammessi in questo livello"))
        else:
            info = pdf.docinfo
            wantv = {1: "PDF/X-1:2001", 3: "PDF/X-3:2002", 4: "PDF/X-4"}[std.part]
            if str(info.get("/GTS_PDFXVersion", "")) != wantv:
                issues.append(("errore", f"GTS_PDFXVersion è «{info.get('/GTS_PDFXVersion', 'assente')}», atteso {wantv}"))
            if not str(info.get("/Title", "")).strip():
                issues.append(("errore", "manca il titolo"))
            if str(info.get("/Trapped", "")) not in ("/True", "/False"):
                issues.append(("errore", "Trapped deve essere True o False"))
            if "/ID" not in pdf.trailer:
                issues.append(("errore", "manca l'ID del documento"))
            for i, page in enumerate(pdf.pages):
                if "/TrimBox" not in page and "/ArtBox" not in page:
                    issues.append(("errore", f"pagina {i + 1}: manca TrimBox/ArtBox"))
                    break
            for i, page in enumerate(pdf.pages):
                bad = [a for a in page.obj.get("/Annots", []) if a.get("/Subtype") not in ("/TrapNet", "/PrinterMark")
                       and int(a.get("/F", 0)) & 4 and not int(a.get("/F", 0)) & 2]
                if bad:
                    issues.append(("errore", f"pagina {i + 1}: annotazioni stampabili non ammesse in PDF/X"))
                    break
        # font incorporati e colori (via PyMuPDF)
        doc = fitz.open("pdf", data)
        try:
            bad = set()
            for p in doc:
                for f in p.get_fonts(full=True):
                    if f[1] in ("n/a", "") and f[2] != "Type3":
                        bad.add(f[3])
            if bad and not nf:
                issues.append(("errore", "font non incorporati: " + ", ".join(sorted(bad)[:6])))
            if not std.cmyk:
                pass
            else:
                rgb = 0
                for p in doc:
                    for img in p.get_images(full=True):
                        cs = img[5] if len(img) > 5 else ""
                        if "RGB" in str(cs) and std.part == 1:
                            rgb += 1
                    c = p.read_contents()
                    if std.part == 1 and re.search(rb"\s(rg|RG)\s", c):
                        rgb += 1
                if rgb:
                    issues.append(("errore", "colori RGB presenti: PDF/X-1a ammette solo CMYK, grigi e tinte piatte"))
        finally:
            doc.close()
        if not std.transparency:
            for t in _xobject_has_transparency(pdf):
                issues.append(("errore", "trasparenza non ammessa: " + t))
    validator = "controllo interno"
    vp = _verapdf(data, std)
    if vp is not None:
        validator = "veraPDF + controllo interno"
        seen = {t for _, t in issues}
        for sev, t in vp[1]:
            if t not in seen:
                issues.append((sev, t))
        if not vp[0] and not any(s == "errore" for s, _ in issues):
            issues.append(("errore", "veraPDF segnala non conformità"))
    if std.family == "X":
        issues.append(("avviso", "PDF/X: verificato solo con il controllo interno (nessun validatore indipendente incluso); "
                                 "per la stampa professionale ricontrolla con il preflight della tipografia"))
    ok = not any(s == "errore" for s, _ in issues)
    return Report(std.label, declared, ok, issues, validator)
