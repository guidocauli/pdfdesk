# PDFDesk — Guido Cauli
# ocr.py: riconoscimento del testo (OCR) su PDF esistenti, singoli o in gruppo, e gestione delle lingue.
#
# Motore: Tesseract è già contenuto in PyMuPDF (MuPDF compilato con Tesseract), quindi su Windows, macOS e Linux non
# serve installare Tesseract: servono solo i dati delle lingue (file .traineddata, 1-8 MB ciascuno). Il programma li
# scarica nella propria cartella dei dati (nessun privilegio di amministratore) da tessdata_fast 4.1.0, con controllo
# SHA-256, oppure usa quelli di un Tesseract già installato nel sistema.
#
# Come funziona su una pagina: la pagina si disegna a 300 dpi, Tesseract produce un PDF con l'immagine e il testo
# invisibile; dall'esito si toglie l'immagine e il solo testo invisibile si sovrappone alla pagina originale. Grafica,
# immagini e qualità della pagina restano quelle di prima; il testo diventa selezionabile e ricercabile.
from __future__ import annotations

import glob
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

import pymupdf as fitz

from .i18n import tr
from .paths import data_dir

TESSDATA_VERSION = "4.1.0"
# più indirizzi: se una rete blocca il primo si prova il successivo (il controllo SHA-256 vale per tutti)
TESSDATA_URLS = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/{v}/{lang}.traineddata",
    "https://github.com/tesseract-ocr/tessdata_fast/raw/{v}/{lang}.traineddata",
    "https://cdn.jsdelivr.net/gh/tesseract-ocr/tessdata_fast@{v}/{lang}.traineddata",
)
# lingua: (byte, sha256) dei file di tessdata_fast 4.1.0
CATALOG = {
    "ara": (1432056, "e3206d3dc87fd50c24a0fb9f01838615911d25168f4e64415244b67d2bb3e729"),
    "bul": (1675212, "aebc9b0fcc8cfaf8a9f38a02bb7b85052bd850744696a2c11cf0081820e5b21e"),
    "cat": (1146012, "250db73cd5b380d2798581295dc12f20d0828cdb335a65d833d12dfdbf57117d"),
    "ces": (3795684, "934bcaf97ef3348413263331131c9fa7f55f30db333c711929c124fb635f7e1b"),
    "chi_sim": (2469156, "a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730"),
    "chi_tra": (2366642, "529c5b5797d64b126065cd55f2bb4c7fd7b15790798091b1ff259941a829330b"),
    "dan": (2580059, "acb1fd074487a31d1294fcdfd7d7c673467ffd8aeacb2ccd61ebcbf04eb4e2fa"),
    "deu": (1525436, "19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d"),
    "ell": (1419514, "4fba8a0b461038d51f1c20d043d4f2ac38c4e778f1b90830847f7bd8fa3ba726"),
    "eng": (4113088, "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"),
    "fin": (7865732, "61a04cd62b507c3d9ae0e1cda399e6715ebf49dea9df47897c8acdcd3bd3e13c"),
    "fra": (1130365, "ced037562e8c80c13122dece28dd477d399af80911a28791a66a63ac1e3445ca"),
    "heb": (961404, "11f9e43ab227f786352a50f75c94c2e9906f1baba86d93276da19da7ce0904db"),
    "hin": (1122751, "4c73ffc59d497c186b19d1e90f5d721d678ea6b2e277b719bee4e2af12271825"),
    "hrv": (4103348, "9e515d9832ce259dbab550b1cc6b998f8b929faf2edacaaca981b05adb130571"),
    "hun": (5296273, "35067e7cfe102dcdc953f9a758fdfaa6296b17a1ee6d874ee780fa306430b9fb"),
    "ita": (2701314, "b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827"),
    "jpn": (2471260, "1f5de9236d2e85f5fdf4b3c500f2d4926f8d9449f28f5394472d9e8d83b91b4d"),
    "kor": (1677415, "6b85e11d9bbf07863b97b3523b1b112844c43e713df8b66418a081fd1060b3b2"),
    "lat": (3187463, "3859d8ba60404f4b79830622625bbc76fb4ee2808eac1ad360ffa77f0a533328"),
    "nld": (6050296, "ced0e5e046a84c908a6aa7accbef9a232c4a5d9a8276691b81c6ee64d02963f6"),
    "nor": (3610079, "0451eb4f8049ae78196806bf878a389a2f40f1386fe038568cf4441226ba6ef2"),
    "pol": (4765518, "c4476cdbc0e33d898d32345122b7be1cbf85ace15f920f06c7714756e1ef79b2"),
    "por": (1982756, "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"),
    "ron": (2376323, "9adfde6b51ba4b97efd10ea37c3070fd3fc2bad7815e81f5c3c198cd96216cc9"),
    "rus": (3861738, "e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225"),
    "slk": (4427661, "fbcc400a9c74c6a13d922fcb1211b655d1b165387b675ed75cd2dbd756b974a5"),
    "slv": (3003829, "b937632c17ce5fdf20535d25feec044da10a0c4c8234f4302d5606fd671cf60d"),
    "spa": (2294433, "6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464"),
    "srp": (2149931, "aa41ae3d9cc705e60d398ab38a5c3cc8b772c0d420c7d4f0859beb13d0e321b6"),
    "swe": (4167034, "f7304988d41f833efebcc2d529df54b1903ecebbc3da1faabd19a0fddd4fe586"),
    "tur": (4550554, "7393381111e1152420fc4092cb44eef4237580d21b92bf30d7d221aad192c6b7"),
    "ukr": (3825102, "d59e53e2bded32f4445f124b4b00240fcac7e8044c003ab822ccb94f0b3db59b"),
}
NAMES = {
    "ara": "Arabo", "bul": "Bulgaro", "cat": "Catalano", "ces": "Ceco", "chi_sim": "Cinese semplificato",
    "chi_tra": "Cinese tradizionale", "dan": "Danese", "deu": "Tedesco", "ell": "Greco", "eng": "Inglese",
    "fin": "Finlandese", "fra": "Francese", "heb": "Ebraico", "hin": "Hindi", "hrv": "Croato", "hun": "Ungherese",
    "ita": "Italiano", "jpn": "Giapponese", "kor": "Coreano", "lat": "Latino", "nld": "Olandese", "nor": "Norvegese",
    "pol": "Polacco", "por": "Portoghese", "ron": "Rumeno", "rus": "Russo", "slk": "Slovacco", "slv": "Sloveno",
    "spa": "Spagnolo", "srp": "Serbo", "swe": "Svedese", "tur": "Turco", "ukr": "Ucraino",
    # possibili lingue di un Tesseract di sistema (non nel catalogo da scaricare)
    "ind": "Indonesiano", "jpn_vert": "Giapponese verticale", "chi_sim_vert": "Cinese semplificato verticale",
    "chi_tra_vert": "Cinese tradizionale verticale", "kor_vert": "Coreano verticale", "tha": "Thailandese",
    "vie": "Vietnamita", "est": "Estone", "lav": "Lettone", "lit": "Lituano", "isl": "Islandese", "gle": "Irlandese",
    "eus": "Basco", "glg": "Galiziano", "mlt": "Maltese", "sqi": "Albanese", "mkd": "Macedone", "bel": "Bielorusso",
    "fas": "Persiano", "urd": "Urdu", "ben": "Bengalese", "tam": "Tamil", "msa": "Malese", "frk": "Tedesco fraktur",
    "equ": "Formule", "enm": "Inglese medio", "frm": "Francese medio", "ita_old": "Italiano antico",
    "spa_old": "Spagnolo antico", "grc": "Greco antico",
}
DEFAULT_LANGS = ("ita", "eng")
DEFAULT_DPI = 300
DEFAULT_SUFFIX = "_ocr"


class OcrError(Exception):
    pass


def lang_name(code: str) -> str:
    return tr(NAMES[code]) if code in NAMES else code


# ---------------------------------------------------------------------- dove sono i dati delle lingue
def user_dir() -> str:
    """Cartella dei dati delle lingue scaricati dal programma (per utente, senza privilegi)."""
    return data_dir("tessdata")


def _app_dirs() -> list[str]:
    """Accanto all'eseguibile (l'installatore Windows con il componente «OCR» li mette lì)."""
    if not getattr(sys, "frozen", False):
        return []
    app = os.path.dirname(sys.executable)
    return [os.path.join(app, "tesseract", "tessdata"), os.path.join(app, "tessdata")]


def _system_dirs() -> list[str]:
    """Dati di un Tesseract installato nel sistema: si usano senza copiarli."""
    d = []
    if os.environ.get("TESSDATA_PREFIX"):
        p = os.environ["TESSDATA_PREFIX"]
        d += [p, os.path.join(p, "tessdata")]
    try:
        from . import scan
        t = scan.tesseract_path()
        if t:
            base = os.path.dirname(os.path.realpath(t))
            d += [os.path.join(base, "tessdata"), os.path.join(os.path.dirname(base), "share", "tessdata")]
    except Exception:
        pass
    if sys.platform == "win32":
        for v in ("PROGRAMFILES", "PROGRAMW6432", "PROGRAMFILES(X86)"):
            if os.environ.get(v):
                d.append(os.path.join(os.environ[v], "Tesseract-OCR", "tessdata"))
    elif sys.platform == "darwin":
        d += ["/opt/homebrew/share/tessdata", "/usr/local/share/tessdata", "/opt/local/share/tessdata"]
    else:
        d += sorted(glob.glob("/usr/share/tesseract-ocr/*/tessdata"), reverse=True)
        d += ["/usr/share/tessdata", "/usr/local/share/tessdata", "/usr/share/tesseract/tessdata"]
    return d


def search_dirs() -> list[str]:
    """Nell'ordine: dati scaricati dal programma, accanto al programma, sistema."""
    out, seen = [], set()
    for p in [user_dir()] + _app_dirs() + _system_dirs():
        rp = os.path.realpath(p)
        if rp not in seen and os.path.isdir(p):
            seen.add(rp); out.append(p)
    return out


def installed() -> dict[str, str]:
    """Lingue disponibili → cartella (la prima in cui si trovano)."""
    out: dict[str, str] = {}
    for d in search_dirs():
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if n.endswith(".traineddata"):
                code = n[:-len(".traineddata")]
                if code != "osd" and code not in out and os.path.getsize(os.path.join(d, n)) > 1000:
                    out[code] = d
    return out


def languages() -> list[str]:
    inst = installed()
    return sorted(inst, key=lambda c: lang_name(c).lower())


def available() -> bool:
    return bool(installed()) and engine_ok()


_ENGINE: Optional[bool] = None


def engine_ok() -> bool:
    """Il motore OCR integrato in PyMuPDF è presente?"""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = hasattr(fitz.Pixmap, "pdfocr_tobytes")
    return _ENGINE


def resolve(langs) -> tuple[str, str]:
    """(«ita+eng», cartella) per le lingue chieste. Il motore vuole tutte le lingue nella stessa cartella: se sono
    sparse (p.es. una scaricata, una di sistema) si copiano nella cartella del programma."""
    codes = [c for c in (langs.split("+") if isinstance(langs, str) else list(langs)) if c]
    if not codes:
        raise OcrError(tr("Scegli almeno una lingua per l'OCR"))
    inst = installed()
    missing = [c for c in codes if c not in inst]
    if missing:
        raise OcrError(tr("Lingue OCR non disponibili: {l}. Scaricale da Preferenze → Scansione e OCR.").format(
            l=", ".join(lang_name(c) for c in missing)))
    dirs = {inst[c] for c in codes}
    if len(dirs) == 1:
        return "+".join(codes), dirs.pop()
    ud = user_dir()
    for c in codes:
        dst = os.path.join(ud, c + ".traineddata")
        if not os.path.isfile(dst):
            shutil.copyfile(os.path.join(inst[c], c + ".traineddata"), dst)
    return "+".join(codes), ud


# ---------------------------------------------------------------------- scaricamento
def download_size(codes) -> int:
    return sum(CATALOG[c][0] for c in codes if c in CATALOG)


def download(codes, progress: Optional[Callable[[str, int, int], bool]] = None, dest: str = "") -> list[str]:
    """Scarica le lingue `codes` (con controllo SHA-256) in `dest` (predefinita: la cartella del programma).
    Restituisce le lingue scaricate; quelle già presenti e integre si saltano."""
    import hashlib
    from .scan import ScanError, _download
    dest = dest or user_dir()
    os.makedirs(dest, exist_ok=True)
    done = []
    for c in codes:
        if c not in CATALOG:
            raise OcrError(tr("Lingua OCR sconosciuta: {c}").format(c=c))
        size, sha = CATALOG[c]
        final = os.path.join(dest, c + ".traineddata")
        if os.path.isfile(final) and os.path.getsize(final) == size:
            with open(final, "rb") as f:
                if hashlib.sha256(f.read()).hexdigest() == sha:
                    continue
        part = final + ".part"
        last: Optional[Exception] = None
        for url in TESSDATA_URLS:
            try:
                _download(url.format(v=TESSDATA_VERSION, lang=c), part,
                          (lambda a, b, c=c: progress(lang_name(c), a, b or size)) if progress else None, sha)
                os.replace(part, final)
                last = None
                break
            except ScanError as e:
                last = e
                if str(e) == tr("Operazione annullata"):
                    raise OcrError(str(e)) from e
        if last is not None:
            raise OcrError(tr("Scaricamento della lingua {l} non riuscito: {e}").format(l=lang_name(c), e=last))
        done.append(c)
    return done


def remove(code: str) -> bool:
    """Toglie una lingua scaricata dal programma (quelle di sistema non si toccano)."""
    p = os.path.join(user_dir(), code + ".traineddata")
    if os.path.isfile(p):
        os.remove(p)
        return True
    return False


def is_user_lang(code: str) -> bool:
    return os.path.isfile(os.path.join(user_dir(), code + ".traineddata"))


# ---------------------------------------------------------------------- riconoscimento
@dataclass
class Report:
    pages: int = 0
    recognized: int = 0             # pagine a cui è stato aggiunto il testo
    skipped_text: int = 0           # pagine che avevano già testo
    empty: int = 0                  # pagine in cui non è stato trovato testo
    words: int = 0
    errors: list = field(default_factory=list)

    def text(self) -> str:
        t = tr("{r} pagine riconosciute su {n}").format(r=self.recognized, n=self.pages)
        if self.skipped_text:
            t += "; " + tr("{s} avevano già testo").format(s=self.skipped_text)
        if self.empty:
            t += "; " + tr("{e} senza testo riconoscibile").format(e=self.empty)
        if self.errors:
            t += "; " + tr("{e} con errori").format(e=len(self.errors))
        return t


def page_has_text(page: fitz.Page) -> bool:
    try:
        return bool(page.get_text("words"))
    except Exception:
        return False


def ocr_page(page: fitz.Page, langs: str, tessdata: str, dpi: int = DEFAULT_DPI) -> int:
    """Aggiunge alla pagina il testo invisibile riconosciuto; restituisce il numero di parole aggiunte (0 = niente)."""
    rot = page.rotation
    if rot:
        page.set_rotation(0)              # si riconosce e si sovrappone nel sistema di coordinate della pagina
    try:
        pix = page.get_pixmap(dpi=dpi, alpha=False, annots=False)
        data = pix.pdfocr_tobytes(compress=True, language=langs, tessdata=tessdata)
        pix = None
        res = fitz.open("pdf", data)
        try:
            rp = res[0]
            words = len(rp.get_text("words"))
            if not words:
                return 0
            for im in rp.get_images(full=True):
                rp.delete_image(im[0])        # resta solo il testo invisibile: la pagina originale non cambia aspetto
            page.show_pdf_page(page.rect, res, 0, overlay=True)
            return words
        finally:
            res.close()
    finally:
        if rot:
            page.set_rotation(rot)


def ocr_document(doc: fitz.Document, langs, only_missing: bool = True, dpi: int = DEFAULT_DPI,
                 pages: Optional[list] = None, progress: Optional[Callable[[int, int], bool]] = None) -> Report:
    """Riconosce il testo nelle pagine di `doc` (modificato sul posto). Con `only_missing` si saltano le pagine che
    hanno già testo. `progress(i, n)` → False per annullare (le pagine già fatte restano)."""
    if not engine_ok():
        raise OcrError(tr("Il motore OCR non è disponibile in questa installazione"))
    code, td = resolve(langs)
    todo = list(range(doc.page_count)) if pages is None else [p for p in pages if 0 <= p < doc.page_count]
    rep = Report(pages=len(todo))
    for i, pno in enumerate(todo):
        if progress and progress(i, len(todo)) is False:
            raise OcrError(tr("Operazione annullata"))
        page = doc[pno]
        if only_missing and page_has_text(page):
            rep.skipped_text += 1
            continue
        try:
            n = ocr_page(page, code, td, dpi)
        except Exception as e:  # noqa: BLE001
            rep.errors.append((pno + 1, str(e)))
            continue
        if n:
            rep.recognized += 1; rep.words += n
        else:
            rep.empty += 1
    if progress:
        progress(len(todo), len(todo))
    return rep


def output_name(src: str, suffix: str = DEFAULT_SUFFIX, folder: str = "", overwrite: bool = False) -> str:
    """«cartella/nome<suffisso>.pdf»; senza `overwrite`, se esiste già si aggiunge un numero."""
    stem = os.path.splitext(os.path.basename(src))[0]
    folder = folder or os.path.dirname(os.path.abspath(src))
    suffix = suffix if suffix is not None else DEFAULT_SUFFIX
    out = os.path.join(folder, f"{stem}{suffix}.pdf")
    n = 2
    while not overwrite and os.path.exists(out):
        out = os.path.join(folder, f"{stem}{suffix}-{n}.pdf"); n += 1
    return out


def ocr_bytes(data: bytes, langs, only_missing: bool = True, dpi: int = DEFAULT_DPI, password: str = "",
              progress: Optional[Callable[[int, int], bool]] = None) -> tuple[bytes, Report]:
    doc = fitz.open("pdf", data)
    try:
        if doc.needs_pass and not doc.authenticate(password):
            raise OcrError(tr("PDF protetto da password"))
        rep = ocr_document(doc, langs, only_missing, dpi, progress=progress)
        return doc.tobytes(garbage=4, deflate=True), rep
    finally:
        doc.close()


def ocr_file(src: str, dst: str, langs, only_missing: bool = True, dpi: int = DEFAULT_DPI, password: str = "",
             progress: Optional[Callable[[int, int], bool]] = None) -> Report:
    """OCR di un file in un nuovo file (scrittura atomica). Il file d'origine non viene modificato."""
    if os.path.abspath(src) == os.path.abspath(dst):
        raise OcrError(tr("Il file di uscita deve essere diverso dall'originale"))
    with open(src, "rb") as f:
        data = f.read()
    out, rep = ocr_bytes(data, langs, only_missing, dpi, password, progress)
    from .compress import write_atomic
    if os.path.dirname(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
    write_atomic(dst, out)
    return rep
