# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# compress.py: salvataggio a qualità/compressione diverse. Il testo resta sempre testo (mai rasterizzato).
from __future__ import annotations

import os
import re
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
    # --- font: "keep" (come sono), "subset" (ridotti ai caratteri usati), "embed" (incorpora anche i mancanti, ridotti),
    #     "unembed" (toglie i font incorporati dove il visualizzatore può sostituirli). subset_fonts=True equivale a "subset".
    font_mode: str = "keep"
    report: Optional[dict] = None         # se è un dizionario, optimize_bytes vi scrive cosa ha fatto (font incorporati/rimossi)


FONT_MODES = [
    ("keep", "Lascia i font come sono"),
    ("subset", "Riduci i font incorporati ai soli caratteri usati"),
    ("embed", "Incorpora tutti i font (anche quelli mancanti), ridotti ai caratteri usati"),
    ("unembed", "Non incorporare i font (file più piccolo; il visualizzatore usa i font di sistema)"),
]


def font_mode(opts: SaveOptions) -> str:
    return "subset" if opts.font_mode == "keep" and opts.subset_fonts else opts.font_mode


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
    fmode = "keep" if opts.standard else font_mode(opts)     # gli standard decidono da soli (PDF/A e PDF/X incorporano tutto)
    rep = opts.report if isinstance(opts.report, dict) else {}
    if fmode == "embed":                                      # prima di tutto: Ghostscript riscrive il file
        data = embed_fonts(data, runner=opts.runner, report=rep)
    doc = fitz.open("pdf", data)
    try:
        if thr is not None or opts.grayscale:
            doc.rewrite_images(dpi_threshold=thr, dpi_target=target, quality=quality, lossy=opts.lossy, lossless=opts.lossless,
                               color=opts.kinds[0], gray=opts.kinds[1], bitonal=opts.kinds[2], set_to_gray=opts.grayscale)
        if fmode == "subset":
            try:
                doc.subset_fonts()
            except Exception:
                pass
        elif fmode == "unembed":
            removed, kept = unembed_fonts(doc)
            rep["fonts_removed"], rep["fonts_kept"] = removed, kept
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
        conservative = opts.preset == "original" and not opts.strip_metadata and fmode == "keep"
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


# ---------------------------------------------------------------------- font: inventario, incorporazione, rimozione
_REF = re.compile(r"(\d+)\s+0\s+R")
_SUBSET = re.compile(r"^/?[A-Z]{6}\+")
_SIMPLE_ENC = ("/WinAnsiEncoding", "/MacRomanEncoding", "/StandardEncoding", "/MacExpertEncoding")


def _font_parts(doc: fitz.Document, x: int):
    """(sottotipo, xref del descrittore o 0) di un dizionario /Font; None se l'oggetto non è un font."""
    if doc.xref_get_key(x, "Type") != ("name", "/Font"):
        return None
    sub = doc.xref_get_key(x, "Subtype")[1]
    if sub in ("/CIDFontType0", "/CIDFontType2"):              # parte di un font composto: si conta il font /Type0
        return None
    owner = x
    if sub == "/Type0":
        t, v = doc.xref_get_key(x, "DescendantFonts")
        m = _REF.search(v or "")
        if t == "xref" and m:                                   # l'array stesso è un oggetto indiretto
            m = _REF.search(doc.xref_object(int(m.group(1)), compressed=True) or "")
        if not m:
            return sub, 0
        owner = int(m.group(1))
    t, v = doc.xref_get_key(owner, "FontDescriptor")
    m = _REF.search(v or "") if t == "xref" else None
    return sub, (int(m.group(1)) if m else 0)


def _embedded(doc: fitz.Document, fd: int) -> bool:
    return bool(fd) and any(doc.xref_get_key(fd, k)[0] != "null" for k in ("FontFile", "FontFile2", "FontFile3"))


def font_inventory(doc: fitz.Document) -> dict:
    """Font del file: quanti incorporati e quali no (i Type3 sono disegni, sempre «incorporati»)."""
    emb, missing = 0, []
    for x in range(1, doc.xref_length()):
        try:
            parts = _font_parts(doc, x)
        except Exception:
            continue
        if not parts or parts[0] == "/Type3":
            continue
        if _embedded(doc, parts[1]):
            emb += 1
        else:
            missing.append(_SUBSET.sub("", doc.xref_get_key(x, "BaseFont")[1] or "?").lstrip("/"))
    return {"embedded": emb, "missing": sorted(set(missing))}


def unembed_fonts(doc: fitz.Document) -> tuple[int, int]:
    """Toglie i file dei font semplici con codifica nota e non simbolici: il visualizzatore li sostituisce con un font
    di sistema dalla stessa metrica (le larghezze restano nel PDF). I font composti (CID, tipici di testi non latini) e
    quelli simbolici restano incorporati, perché senza il loro file i caratteri non sarebbero più riconoscibili.
    Restituisce (rimossi, lasciati incorporati)."""
    removed = kept = 0
    done: set[int] = set()
    for x in range(1, doc.xref_length()):
        try:
            parts = _font_parts(doc, x)
            if not parts or parts[0] == "/Type3":
                continue
            sub, fd = parts
            if not _embedded(doc, fd):
                continue
            # serve una codifica che il visualizzatore sappia applicare a un font sostitutivo: un nome standard, oppure
            # un dizionario con /BaseEncoding (le sole /Differences si appoggerebbero alla codifica interna del font)
            et, ev = doc.xref_get_key(x, "Encoding")
            if et == "xref":
                m = _REF.search(ev or "")
                ev = doc.xref_object(int(m.group(1)), compressed=True) if m else ""
            enc_ok = (et == "name" and ev in _SIMPLE_ENC) or (et in ("dict", "xref") and "/BaseEncoding" in (ev or "")
                                                               and any(e in ev for e in _SIMPLE_ENC))
            base = _SUBSET.sub("", doc.xref_get_key(x, "BaseFont")[1] or "").lstrip("/")
            if sub not in ("/Type1", "/TrueType", "/MMType1") or not enc_ok or base.startswith(("Symbol", "ZapfDingbats", "Wingdings")):
                kept += 1
                continue
            if fd not in done:
                for k in ("FontFile", "FontFile2", "FontFile3"):
                    if doc.xref_get_key(fd, k)[0] != "null":
                        doc.xref_set_key(fd, k, "null")
                fn = doc.xref_get_key(fd, "FontName")
                if fn[0] == "name" and _SUBSET.match(fn[1]):
                    doc.xref_set_key(fd, "FontName", "/" + _SUBSET.sub("", fn[1]).lstrip("/"))
                fl = doc.xref_get_key(fd, "Flags")[1]          # il sostituto è un font di testo: «non simbolico»
                if fl.isdigit():
                    doc.xref_set_key(fd, "Flags", str((int(fl) & ~4) | 32))
                doc.xref_set_key(fd, "CharSet", "null")         # descriveva il sottoinsieme ormai tolto
                done.add(fd)
            bf = doc.xref_get_key(x, "BaseFont")
            if bf[0] == "name" and _SUBSET.match(bf[1]):
                doc.xref_set_key(x, "BaseFont", "/" + _SUBSET.sub("", bf[1]).lstrip("/"))
            removed += 1
        except Exception:
            continue
    return removed, kept


def embed_fonts(data: bytes, runner=None, report: Optional[dict] = None) -> bytes:
    """Incorpora i font mancanti (ridotti ai caratteri usati) riscrivendo il file con Ghostscript. Immagini JPEG copiate
    senza ricompressione, le altre senza perdita; annotazioni e collegamenti conservati. Se non manca nessun font il file
    resta com'è."""
    import shutil
    import subprocess
    import tempfile
    from . import pdfstd
    rep = report if report is not None else {}
    with fitz.open("pdf", data) as d:
        before = font_inventory(d)["missing"]
        nlinks = sum(len(p.get_links()) for p in d)
    rep["fonts_embedded"], rep["fonts_missing"] = 0, []
    if not before:
        return data
    gs = pdfstd.find_gs()
    if not gs:
        raise pdfstd.StandardError("per incorporare i font serve Ghostscript (incluso nei pacchetti ufficiali; da sorgente "
                                   "installalo o imposta PDFDESK_GS)")
    links = pdfstd._collect_links(data) if nlinks else []
    tmp = tempfile.mkdtemp(prefix="pdfdesk-font-")
    try:
        pin, pout = os.path.join(tmp, "in.pdf"), os.path.join(tmp, "out.pdf")
        with open(pin, "wb") as f:
            f.write(data)
        args = [gs, "-dBATCH", "-dNOPAUSE", "-dQUIET", "-dSAFER", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
                "-dEmbedAllFonts=true", "-dSubsetFonts=true", "-dAutoRotatePages=/None", "-dPreserveAnnots=true",
                "-dDownsampleColorImages=false", "-dDownsampleGrayImages=false", "-dDownsampleMonoImages=false",
                "-dAutoFilterColorImages=false", "-dAutoFilterGrayImages=false",
                "-dColorImageFilter=/FlateEncode", "-dGrayImageFilter=/FlateEncode",
                "-dPassThroughJPEGImages=true", "-dPassThroughJPXImages=true",
                "-sColorConversionStrategy=LeaveColorUnchanged", f"-sOutputFile={pout}",
                "-c", "<< /NeverEmbed [ ] >> setdistillerparams", "-f", pin]   # anche i 14 font standard
        call = lambda: subprocess.run(args, capture_output=True, env=pdfstd._gs_env(gs), timeout=900,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        r = runner(call) if runner else call()
        if r.returncode != 0 or not os.path.isfile(pout) or os.path.getsize(pout) == 0:
            msg = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip()[-400:]
            raise pdfstd.StandardError(f"Ghostscript non è riuscito a incorporare i font: {msg or 'errore sconosciuto'}")
        with open(pout, "rb") as f:
            out = f.read()
    except subprocess.TimeoutExpired as e:
        raise pdfstd.StandardError("incorporazione dei font troppo lunga (oltre 15 minuti)") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    out = _repair_after_gs(out, data, links)
    with fitz.open("pdf", out) as d:
        after = font_inventory(d)["missing"]
    rep["fonts_embedded"], rep["fonts_missing"] = len(set(before) - set(after)), after
    return out


def _repair_after_gs(out: bytes, src: bytes, links: list) -> bytes:
    """Dopo Ghostscript: testo copiabile (ToUnicode), metadati di base e collegamenti se sono andati persi."""
    import io
    import pikepdf
    from . import pdfstd
    with fitz.open("pdf", src) as s:
        meta = {k: v for k, v in (s.metadata or {}).items() if v and k in ("title", "author", "subject", "keywords")}
    try:
        with pikepdf.open(io.BytesIO(out)) as pdf:
            try:
                pdfstd._fix_tounicode(pdf)
            except Exception:
                pass
            if links and not any(a.get("/Subtype") == "/Link" for p in pdf.pages for a in (p.obj.get("/Annots") or [])):
                pdfstd._restore_links(pdf, links)
            buf = io.BytesIO()
            # i metadati XMP scritti da alcune versioni di Ghostscript non si lasciano aggiornare: si lasciano com'erano
            pdf.save(buf, fix_metadata_version=False)
            out = buf.getvalue()
    except Exception:
        pass                                   # la sistemazione è un di più: resta il file di Ghostscript
    d = fitz.open("pdf", out)
    try:
        if meta:
            m = d.metadata or {}
            m.update(meta)
            d.set_metadata(m)
        return d.tobytes(garbage=1, deflate=True)
    finally:
        d.close()


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
        try:
            finv = font_inventory(doc)
        except Exception:
            finv = {"embedded": 0, "missing": []}
        return {"total": len(data), "categories": cat, "counts": counts, "images": imgs[:top], "image_count": len(imgs),
                "fonts": finv}
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
    f = a.get("fonts")
    if f:
        lines.append(f"Font: {f['embedded']} incorporati, {len(f['missing'])} non incorporati"
                     + (f" ({', '.join(f['missing'][:8])}{'…' if len(f['missing']) > 8 else ''})" if f["missing"] else ""))
    if a["images"]:
        lines.append(f"Immagini più pesanti ({a['image_count']} in totale):")
        for i in a["images"]:
            lines.append(f"  pag. {i['page']}: {i['w']}×{i['h']} px, {human_size(i['bytes'])}" + (f", ~{i['dpi']} dpi" if i["dpi"] else ""))
    return "\n".join(lines)


def write_atomic(path: str, data: bytes) -> None:
    """Scrive su un file temporaneo e lo sostituisce all'originale. Su Windows antivirus e indicizzatore tengono a volte il file
    aperto per un attimo: si riprova qualche volta; se non riesce si toglie il temporaneo e si segnala l'errore."""
    import time
    tmp = path + ".pdfdesk-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    for attempt in range(6):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 5:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            time.sleep(0.25 * (attempt + 1))
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"
