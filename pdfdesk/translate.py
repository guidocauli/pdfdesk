# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Traduzione dei PDF: il testo di ogni casella (blocco di testo: paragrafo, cella, didascalia) viene tradotto e riscritto nello
# stesso riquadro, rimpicciolendolo se non entra. Immagini e grafica restano come sono.
#
# Motori:
#   - «locale» (predefinito): modelli Argos/OPUS-MT eseguiti con CTranslate2, senza internet; il testo non lascia il computer.
#     I modelli (circa 90 MB per direzione) si scaricano al primo uso; le coppie senza modello diretto passano per l'inglese.
#   - «deepl»: API DeepL con chiave dell'utente (il testo viene inviato ai server DeepL).
#   - «libretranslate»: un server LibreTranslate (anche installato in proprio), con chiave facoltativa.
# Nessuna dipendenza da Qt: usato dall'interfaccia e dalla riga di comando.
from __future__ import annotations

import html
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

import pymupdf as fitz

from .i18n import tr
from .paths import data_dir

INDEX_URL = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
ENGINES = ("local", "deepl", "libretranslate")
DEFAULT_PATTERN = "{name}_translated_{lang}"
MIN_SCALE = 0.5                     # il testo può scendere fino a metà della dimensione originale

# lingue (codice ISO 639-1 → nome); quelle del motore locale sono le lingue dei modelli Argos
LANGS = {
    "ar": "Arabo", "az": "Azero", "bg": "Bulgaro", "bn": "Bengalese", "ca": "Catalano", "cs": "Ceco", "da": "Danese",
    "de": "Tedesco", "el": "Greco", "en": "Inglese", "eo": "Esperanto", "es": "Spagnolo", "et": "Estone", "eu": "Basco",
    "fa": "Persiano", "fi": "Finlandese", "fr": "Francese", "ga": "Irlandese", "gl": "Galiziano", "he": "Ebraico",
    "hi": "Hindi", "hu": "Ungherese", "id": "Indonesiano", "it": "Italiano", "ja": "Giapponese", "ko": "Coreano",
    "lt": "Lituano", "lv": "Lettone", "ms": "Malese", "nb": "Norvegese", "nl": "Olandese", "pl": "Polacco",
    "pt": "Portoghese", "ro": "Rumeno", "ru": "Russo", "sk": "Slovacco", "sl": "Sloveno", "sq": "Albanese",
    "sv": "Svedese", "th": "Thailandese", "tr": "Turco", "uk": "Ucraino", "ur": "Urdu", "vi": "Vietnamita",
    "zh": "Cinese",
}
RTL = {"ar", "he", "fa", "ur"}       # scrittura da destra a sinistra: non ancora supportata nella riscrittura


class TranslateError(Exception):
    pass


def lang_name(code: str) -> str:
    return tr(LANGS.get(code, code))


# ------------------------------------------------------------------------------------------------ rilevamento lingua
def detect_language(text: str) -> Optional[str]:
    """Lingua prevalente del testo (codice ISO), senza internet. None se il testo è troppo corto."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if len(re.findall(r"[^\W\d_]", t)) < 20:
        return None
    try:
        from langdetect import DetectorFactory, detect
        DetectorFactory.seed = 0                         # risultato ripetibile
        code = detect(t[:20000])
    except Exception:
        return None
    return {"no": "nb", "zh-cn": "zh", "zh-tw": "zh"}.get(code, code)


def detect_pdf_language(doc: fitz.Document, max_pages: int = 8) -> Optional[str]:
    """Rileva la lingua dal testo di alcune pagine distribuite nel documento (non solo la prima)."""
    n = doc.page_count
    if n == 0:
        return None
    idx = sorted({int(i * (n - 1) / max(1, max_pages - 1)) for i in range(min(n, max_pages))})
    return detect_language(" ".join(doc[i].get_text() for i in idx))


# ------------------------------------------------------------------------------------------------ frasi
_ABBR = r"(?<!\b[A-Z])(?<!\bes)(?<!\becc)(?<!\bpag)(?<!\bart)(?<!\bn)(?<!\bp)(?<!\bSig)(?<!\bDr)(?<!\bMr)(?<!\bMrs)(?<!\bvs)(?<!\betc)(?<!\be\.g)(?<!\bi\.e)"
_SPLIT = re.compile(_ABBR + r"(?<=[.!?;])\s+(?=[\"«“(\[]?[A-ZÀ-ÖØ-Þ0-9])")


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SPLIT.split(text) if p.strip()]
    out = []
    for p in parts:                                   # frasi lunghissime: si spezzano ancora ai due punti / punto e virgola
        out.extend([p] if len(p) < 600 else [q for q in re.split(r"(?<=[:;])\s+", p) if q])
    return out or ([text] if text.strip() else [])


# ------------------------------------------------------------------------------------------------ motori
class Engine:
    name = ""

    def ready(self, src: str, dst: str) -> bool:          # True se può tradurre subito (modelli presenti, chiave impostata…)
        return True

    def translate(self, texts: list[str], src: str, dst: str, progress: Optional[Callable[[int, int], bool]] = None) -> list[str]:
        raise NotImplementedError


def models_dir() -> str:
    return data_dir("translate-models")


@dataclass
class ModelInfo:
    src: str
    dst: str
    version: str
    url: str

    @property
    def folder(self) -> str:
        return os.path.join(models_dir(), f"{self.src}_{self.dst}")


def installed_pairs() -> set:
    out = set()
    for d in os.listdir(models_dir()):
        p = os.path.join(models_dir(), d)
        if re.fullmatch(r"[a-z]{2,3}_[a-z]{2,3}", d) and os.path.isfile(os.path.join(p, "sentencepiece.model")) \
                and os.path.isdir(os.path.join(p, "model")):
            out.add(tuple(d.split("_")))
    return out


def fetch_index(timeout: int = 30) -> list[ModelInfo]:
    import urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request(INDEX_URL, headers={"User-Agent": "PDFDesk"}), timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise TranslateError(tr("Impossibile scaricare l'elenco dei modelli di traduzione: {}").format(e)) from e
    best: dict = {}
    for p in data:
        if not p.get("links"):
            continue
        k = (p["from_code"], p["to_code"])
        v = tuple(int(x) for x in re.findall(r"\d+", str(p.get("package_version", "0"))))
        if k not in best or v > best[k][0]:
            best[k] = (v, ModelInfo(k[0], k[1], str(p.get("package_version", "")), p["links"][0]))
    return [m for _, m in best.values()]


def route(src: str, dst: str, available: set) -> Optional[list]:
    """Coppie di modelli da usare: diretta, oppure passando per l'inglese."""
    if src == dst:
        return []
    if (src, dst) in available:
        return [(src, dst)]
    if src != "en" and dst != "en" and (src, "en") in available and ("en", dst) in available:
        return [(src, "en"), ("en", dst)]
    return None


def models_needed(src: str, dst: str, index: list[ModelInfo]) -> list[ModelInfo]:
    """Modelli da scaricare per tradurre src→dst (vuoto se già presenti). Errore se la coppia non è disponibile."""
    have = installed_pairs()
    r = route(src, dst, have)
    if r is not None:
        return []
    avail = {(m.src, m.dst): m for m in index}
    r = route(src, dst, set(avail) | have)
    if r is None:
        raise TranslateError(tr("Nessun modello per tradurre da {a} a {b}").format(a=lang_name(src), b=lang_name(dst)))
    return [avail[p] for p in r if p not in have]


def install_model(m: ModelInfo, progress: Optional[Callable[[int, int], bool]] = None) -> None:
    """Scarica ed estrae un modello Argos (.argosmodel = zip con il modello CTranslate2 e il tokenizzatore sentencepiece)."""
    from .scan import ScanError, _download
    tmp = tempfile.mkdtemp(prefix="pdfdesk-model-")
    try:
        z = os.path.join(tmp, "m.zip")
        try:
            _download(m.url, z, progress)
        except ScanError as e:
            raise TranslateError(str(e)) from e
        try:
            with zipfile.ZipFile(z) as zf:
                for n in zf.namelist():                     # niente percorsi assoluti o con «..»
                    if n.startswith("/") or ".." in n.split("/"):
                        raise TranslateError(tr("Archivio del modello non valido"))
                zf.extractall(os.path.join(tmp, "x"))
        except zipfile.BadZipFile as e:
            raise TranslateError(tr("Archivio del modello non valido")) from e
        root = None
        for dp, dn, fn in os.walk(os.path.join(tmp, "x")):
            if "sentencepiece.model" in fn and "model" in dn:
                root = dp
                break
        if root is None:
            raise TranslateError(tr("Archivio del modello non valido"))
        if os.path.isdir(m.folder):
            shutil.rmtree(m.folder)
        shutil.move(root, m.folder)
        shutil.rmtree(os.path.join(m.folder, "stanza"), ignore_errors=True)     # serve solo ad Argos, non a PDFDesk
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def remove_model(src: str, dst: str) -> None:
    shutil.rmtree(os.path.join(models_dir(), f"{src}_{dst}"), ignore_errors=True)


class LocalEngine(Engine):
    name = "local"
    _cache: dict = {}

    def ready(self, src, dst):
        return route(src, dst, installed_pairs()) is not None

    @classmethod
    def _load(cls, pair):
        if pair not in cls._cache:
            if os.name == "nt":
                os.environ.setdefault("KMP_AFFINITY", "disabled")     # OpenMP: evita una funzione assente in Wine
            import ctranslate2
            import sentencepiece
            from . import parallel
            d = os.path.join(models_dir(), f"{pair[0]}_{pair[1]}")
            sp = sentencepiece.SentencePieceProcessor(model_file=os.path.join(d, "sentencepiece.model"))
            tr_ = ctranslate2.Translator(os.path.join(d, "model"), device="cpu", compute_type="int8",
                                         inter_threads=1, intra_threads=max(1, parallel.max_workers()))
            cls._cache[pair] = (sp, tr_)
        return cls._cache[pair]

    @classmethod
    def unload(cls):
        cls._cache.clear()

    def _one(self, pair, sents, progress, done, total):
        sp, model = self._load(pair)
        out = []
        for i in range(0, len(sents), 16):
            chunk = sents[i:i + 16]
            res = model.translate_batch([sp.encode(s, out_type=str) for s in chunk], beam_size=2,
                                        max_decoding_length=512, max_input_length=512)
            out += [sp.decode(r.hypotheses[0]) for r in res]
            done[0] += len(chunk)
            if progress and progress(done[0], total) is False:
                raise TranslateError(tr("Operazione annullata"))
        return out

    def translate(self, texts, src, dst, progress=None):
        r = route(src, dst, installed_pairs())
        if r is None:
            raise TranslateError(tr("Modello di traduzione non installato"))
        # ogni testo si divide in frasi; si traducono tutte insieme e poi si ricompongono
        sents, owner = [], []
        for i, t in enumerate(texts):
            for s in split_sentences(t):
                sents.append(s); owner.append(i)
        total = len(sents) * max(1, len(r)); done = [0]
        for pair in r:
            sents = self._one(pair, sents, progress, done, total)
        out = [[] for _ in texts]
        for i, s in zip(owner, sents):
            out[i].append(s)
        return [" ".join(x) for x in out]


def _http_json(url: str, payload: dict, headers: dict, timeout: int = 60):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": "PDFDesk", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise TranslateError(tr("Errore del servizio di traduzione ({c}): {m}").format(c=e.code, m=body)) from e
    except Exception as e:
        raise TranslateError(tr("Servizio di traduzione non raggiungibile: {}").format(e)) from e


class DeepLEngine(Engine):
    name = "deepl"

    def __init__(self, key: str):
        self.key = (key or "").strip()

    def ready(self, src, dst):
        return bool(self.key)

    def translate(self, texts, src, dst, progress=None):
        if not self.key:
            raise TranslateError(tr("Chiave API di DeepL non impostata (Preferenze → Traduzione)"))
        host = "api-free.deepl.com" if self.key.endswith(":fx") else "api.deepl.com"
        target = {"en": "EN-GB", "pt": "PT-PT", "zh": "ZH"}.get(dst, dst.upper())
        out = []
        for i in range(0, len(texts), 40):
            chunk = texts[i:i + 40]
            payload = {"text": chunk, "target_lang": target}
            if src:
                payload["source_lang"] = src.upper()
            r = _http_json(f"https://{host}/v2/translate", payload, {"Authorization": "DeepL-Auth-Key " + self.key})
            out += [t["text"] for t in r.get("translations", [])]
            if progress and progress(len(out), len(texts)) is False:
                raise TranslateError(tr("Operazione annullata"))
        if len(out) != len(texts):
            raise TranslateError(tr("Risposta del servizio di traduzione non valida"))
        return out


class LibreTranslateEngine(Engine):
    name = "libretranslate"

    def __init__(self, url: str, key: str = ""):
        self.url = (url or "").strip().rstrip("/"); self.key = (key or "").strip()

    def ready(self, src, dst):
        return bool(self.url)

    def translate(self, texts, src, dst, progress=None):
        if not self.url:
            raise TranslateError(tr("Indirizzo del server LibreTranslate non impostato (Preferenze → Traduzione)"))
        out = []
        for i in range(0, len(texts), 20):
            chunk = texts[i:i + 20]
            payload = {"q": chunk, "source": src or "auto", "target": dst, "format": "text"}
            if self.key:
                payload["api_key"] = self.key
            r = _http_json(self.url + "/translate", payload, {})
            t = r.get("translatedText")
            out += t if isinstance(t, list) else [t]
            if progress and progress(len(out), len(texts)) is False:
                raise TranslateError(tr("Operazione annullata"))
        if len(out) != len(texts):
            raise TranslateError(tr("Risposta del servizio di traduzione non valida"))
        return out


def make_engine(name: str, deepl_key: str = "", lt_url: str = "", lt_key: str = "") -> Engine:
    if name == "deepl":
        return DeepLEngine(deepl_key)
    if name == "libretranslate":
        return LibreTranslateEngine(lt_url, lt_key)
    return LocalEngine()


# ------------------------------------------------------------------------------------------------ PDF
@dataclass
class Options:
    min_scale: float = MIN_SCALE
    annotations: bool = True          # commenti e caselle di testo
    bookmarks: bool = True            # segnalibri
    metadata: bool = True             # titolo e oggetto


@dataclass
class Report:
    src: str = ""
    dst: str = ""
    blocks: int = 0
    shrunk: int = 0
    overflow: list = field(default_factory=list)      # (pagina, inizio del testo) dei blocchi che non entrano
    skipped_rotated: int = 0
    numbers_changed: list = field(default_factory=list)   # (pagina, testo) in cui la traduzione ha cambiato le cifre

    def text(self) -> str:
        s = tr("{n} caselle tradotte ({a} → {b})").format(n=self.blocks, a=lang_name(self.src), b=lang_name(self.dst))
        if self.shrunk:
            s += "\n" + tr("{n} caselle con il testo rimpicciolito").format(n=self.shrunk)
        if self.overflow:
            s += "\n" + tr("{n} caselle in cui il testo non entra del tutto (pagine: {p})").format(
                n=len(self.overflow), p=", ".join(str(p) for p in sorted({p for p, _ in self.overflow})[:12]))
        if self.numbers_changed:
            s += "\n" + tr("{n} caselle in cui la traduzione ha cambiato dei numeri: da controllare (pagine: {p})").format(
                n=len(self.numbers_changed), p=", ".join(str(p) for p in sorted({p for p, _ in self.numbers_changed})[:12]))
        if self.skipped_rotated:
            s += "\n" + tr("{n} caselle di testo ruotato lasciate nella lingua originale").format(n=self.skipped_rotated)
        return s


_SERIF = re.compile(r"times|serif|roman|georgia|garamond|minion|cambria|palatino|book|bodoni|caslon", re.I)
_MONO = re.compile(r"courier|mono|consol|menlo|code", re.I)
_LETTER = re.compile(r"[^\W\d_]{2,}")


@dataclass
class _Block:
    page: int
    rect: fitz.Rect
    text: str
    size: float
    color: int
    bold: bool
    italic: bool
    family: str
    align: str
    lines: int = 1
    line_rects: list = field(default_factory=list)
    protected: list = field(default_factory=list)      # pezzi da non tradurre (testo a spaziatura fissa)
    marker_rects: list = field(default_factory=list)   # simbolo dell'elenco (•, 1.): resta dov'è
    baseline: float = 0.0                              # linea di base della prima riga (y dell'origine dei caratteri)


def _clusters(line: dict) -> list[list[dict]]:
    """Divide una riga in gruppi separati da un grande spazio orizzontale (celle di una tabella, colonne).
    Si guardano i singoli caratteri: PyMuPDF unisce in un solo span testi lontani riempiendo lo spazio di blank.
    Ogni gruppo è una lista di pezzi di span (testo, dimensione, colore, font, riquadro)."""
    groups: list[list[dict]] = []
    last_x1 = None
    pending_space = False                                       # spazio prima di un cambio di stile (es. «testo» + « con»)
    for sp in line["spans"]:
        piece = None
        for ch in sp.get("chars") or []:
            c = ch["c"]; bx = ch["bbox"]
            if c.strip():
                if last_x1 is None or bx[0] - last_x1 > sp["size"] * 1.6:
                    groups.append([]); piece = None; pending_space = False   # primo carattere o salto grande: nuovo gruppo
                elif piece is None and groups and groups[-1] and bx[0] - last_x1 > sp["size"] * 0.2:
                    pending_space = True                        # spazio visibile tra due stili
                if piece is None:
                    piece = {"text": " " if pending_space else "", "size": sp["size"], "color": sp["color"], "font": sp["font"],
                             "flags": sp["flags"], "bbox": list(bx), "origin": ch.get("origin", (bx[0], bx[3]))}
                    groups[-1].append(piece)
                    pending_space = False
                piece["text"] += c
                piece["bbox"] = [min(piece["bbox"][0], bx[0]), min(piece["bbox"][1], bx[1]),
                                 max(piece["bbox"][2], bx[2]), max(piece["bbox"][3], bx[3])]
                last_x1 = bx[2]
            elif piece is not None:
                piece["text"] += c                                  # spazio dentro il gruppo
            elif groups and groups[-1]:
                pending_space = True
    for g in groups:
        for pc in g:
            pc["text"] = pc["text"].rstrip() if pc is g[-1] else pc["text"]
    return [g for g in groups if g]


def _only_numbers(t: str) -> bool:
    """Importi, codici e simili: numeri con al più una sigla corta (es. «35.500 EUR», «12 kg», «N. 4»)."""
    if not re.search(r"\d", t):
        return False
    words = re.findall(r"[^\W\d_]+", t)
    return len(words) <= 1 and all(len(w) <= 4 for w in words)


def _free_right(page_rect: fitz.Rect, b: "_Block", others: list, drawings: list, left_margin: float) -> float:
    """Fin dove una casella di una riga può allargarsi a destra senza toccare altro testo o grafica (linee di tabelle…)."""
    limit = page_rect.x1 - max(left_margin - page_rect.x0, 18)          # margine destro simmetrico a quello sinistro del testo
    band = fitz.Rect(b.rect.x1, b.rect.y0 + 1, limit, b.rect.y1 - 1)
    for r in others + drawings:
        if r.x0 >= b.rect.x1 - 0.5 and r.y1 > band.y0 and r.y0 < band.y1:
            limit = min(limit, r.x0 - 2)
        elif r.x0 < b.rect.x1 - 0.5 < r.x1 and r.y1 > band.y0 and r.y0 < band.y1 and (r.width < 2 or r.height < 2) is False \
                and not r.contains(b.rect):
            limit = min(limit, r.x1 - 2)
    return max(limit, b.rect.x1)


def _make_block(pno: int, groups: list[list[dict]]) -> Optional["_Block"]:
    """Un blocco da una sequenza di righe (ogni riga: lista di span)."""
    parts, weight = [], {}
    x0 = y0 = 1e9; x1 = y1 = -1e9
    for spans in groups:
        t = "".join(sp["text"] for sp in spans).strip()
        if not t:
            continue
        if parts and parts[-1].endswith("-") and t[:1].islower():
            parts[-1] = parts[-1][:-1] + t                             # parola spezzata a fine riga
        else:
            parts.append(t)
        for sp in spans:
            k = (round(sp["size"], 1), sp["color"], sp["font"], sp["flags"])
            weight[k] = weight.get(k, 0) + len(sp["text"].strip())
            bx = sp["bbox"]; x0 = min(x0, bx[0]); y0 = min(y0, bx[1]); x1 = max(x1, bx[2]); y1 = max(y1, bx[3])
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if not weight or not _LETTER.search(text) or _only_numbers(text):
        return None                                                    # numeri, importi, simboli: non si traducono
    size, color, font, flags = max(weight, key=weight.get)
    bold = bool(flags & 16) or bool(re.search(r"bold|black|heavy|semibold", font, re.I))
    italic = bool(flags & 2) or bool(re.search(r"italic|oblique", font, re.I))
    # il PDF dichiara se il carattere ha le grazie (flag 4) o è a spaziatura fissa (flag 8); il nome serve da riserva
    fam = ("monospace" if (flags & 8) or _MONO.search(font) else
           "serif" if (flags & 4) or _SERIF.search(font) else "sans-serif")
    mono = [sp["text"].strip() for g in groups for sp in g
            if sp["text"].strip() and ((sp["flags"] & 8) or _MONO.search(sp["font"])) and fam != "monospace"]
    lrs = []
    for spans in groups:
        if any(sp["text"].strip() for sp in spans):
            lrs.append(fitz.Rect(min(sp["bbox"][0] for sp in spans), min(sp["bbox"][1] for sp in spans),
                                 max(sp["bbox"][2] for sp in spans), max(sp["bbox"][3] for sp in spans)))
    if fam == "monospace":
        return None                                                    # codice, comandi: si lasciano com'è
    first_pc = next((pc for g in groups for pc in g if pc["text"].strip()), None)
    base = first_pc["origin"][1] if first_pc and first_pc.get("origin") else y1
    return _Block(pno, fitz.Rect(x0, y0, x1, y1), text, size, color, bold, italic, fam, "left", 1, lrs, mono, [], base)


_MARKER = re.compile(r"^\s*([•·◦▪▫‣⁃●○■□–—\-*]|\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|[ivxIVX]{1,4}[.)])\s+")


def _paragraphs(lines: list, cl: list) -> list:
    """Divide le righe di un blocco in paragrafi: nuova voce quando una riga inizia con un simbolo o un numero di elenco,
    oppure quando lo spazio verticale è più grande della normale interlinea. Ogni paragrafo: lista di (riga, gruppi)."""
    paras: list = []
    prev = None
    for l, c in zip(lines, cl):
        if not c:
            continue
        t = "".join(pc["text"] for g in c for pc in g)
        size = max(pc["size"] for g in c for pc in g)
        new = prev is None or bool(_MARKER.match(t))
        if prev is not None and not new:
            gap = l["bbox"][1] - prev["bbox"][3]
            if gap > size * 0.6:
                new = True
        if new:
            paras.append([])
        paras[-1].append((l, c))
        prev = l
    return paras


def _para_block(pno: int, para: list, keep: list) -> Optional["_Block"]:
    """Blocco da un paragrafo. Il simbolo iniziale dell'elenco resta dov'è (protetto) e il testo tradotto parte dalla
    posizione del testo, con il rientro delle righe successive."""
    groups = [g for _, c in para for g in c]
    if not groups:
        return None
    first = groups[0]
    t0 = "".join(pc["text"] for pc in first)
    m = _MARKER.match(t0)
    marker_rects = []
    text_x = None
    if m:
        mk = m.group(1)
        # riquadro del simbolo: i primi caratteri del primo pezzo; il testo comincia dopo
        lchars = [ch for sp in para[0][0]["spans"] for ch in (sp.get("chars") or [])]
        mchars = []
        need = len(mk)
        for ch in lchars:
            if not ch["c"].strip():
                if mchars:
                    break
                continue
            mchars.append(ch)
            if len("".join(c["c"] for c in mchars)) >= need:
                break
        text_x = None
        if mchars:
            seen = False
            for ch in lchars:                                     # primo carattere del testo dopo il simbolo
                if ch is mchars[-1]:
                    seen = True; continue
                if seen and ch["c"].strip():
                    text_x = ch["bbox"][0]; break
        if mchars:
            mr = fitz.Rect(mchars[0]["bbox"])
            for ch in mchars[1:]:
                mr |= fitz.Rect(ch["bbox"])
            marker_rects.append(mr); keep.append(mr)
        # toglie il simbolo dal primo pezzo (o il pezzo intero, se contiene solo il simbolo)
        p0 = first[0]["text"]
        m0 = _MARKER.match(p0) or _MARKER.match(p0 + " ")
        if m0:
            rest = p0[m0.end():]
            first = ([dict(first[0], text=rest)] if rest.strip() else []) + first[1:]
            if first:
                first[0] = dict(first[0], text=first[0]["text"].lstrip())
            groups = ([first] if first else []) + groups[1:]
    blk = _make_block(pno, groups)
    if blk is None:
        return None
    blk.marker_rects = marker_rects
    if marker_rects:
        # il testo inizia dopo il simbolo: stesso rientro delle righe successive (se ce ne sono)
        xs = [l["bbox"][0] for l, _ in para[1:]]
        x0 = min(xs) if xs else None
        start = text_x if text_x is not None else blk.rect.x0
        blk.rect.x0 = max(marker_rects[0].x1 + 1, x0 if x0 is not None and x0 > marker_rects[0].x1 else start)
        blk.line_rects = [fitz.Rect(max(r.x0, marker_rects[0].x1 + 0.3), r.y0, r.x1, r.y1) if i == 0 else r
                          for i, r in enumerate(blk.line_rects)]
    blk.lines = len(para)
    return blk


def _blocks(page: fitz.Page, keep: Optional[list] = None) -> tuple[list[_Block], int]:
    """Caselle di testo da tradurre. In `keep` (se data) finiscono i riquadri del testo che resta com'è (ruotato, importi)."""
    out, rotated = [], 0
    keep = keep if keep is not None else []
    d = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
    for blk in d["blocks"]:                                       # rawdict: il testo degli span si ricava dai caratteri
        for l in blk.get("lines", []):
            for sp in l["spans"]:
                sp["text"] = "".join(c["c"] for c in sp.get("chars", []))
    for b in d["blocks"]:
        if b.get("type") != 0 or not b.get("lines"):
            continue
        lines = b["lines"]
        if any(abs(l["dir"][0] - 1) > 0.01 or abs(l["dir"][1]) > 0.01 for l in lines):
            if _LETTER.search(" ".join(s["text"] for l in lines for s in l["spans"])):
                rotated += 1
            keep += [fitz.Rect(l["bbox"]) for l in lines]
            continue
        cl = [_clusters(l) for l in lines]
        groups = [g for c in cl for g in c]

        def gbox(g):
            return (min(pc["bbox"][0] for pc in g), min(pc["bbox"][1] for pc in g),
                    max(pc["bbox"][2] for pc in g), max(pc["bbox"][3] for pc in g))
        boxes = [gbox(g) for g in groups]
        side_by_side = any(
            min(a[3], c[3]) - max(a[1], c[1]) > 0.5 * min(a[3] - a[1], c[3] - c[1])     # stessa altezza…
            and (c[0] >= a[2] - 1 or a[0] >= c[2] - 1)                                 # …e affiancati
            for i, a in enumerate(boxes) for c in boxes[i + 1:])
        if side_by_side or any(len(c) > 1 for c in cl):
            # righe con più gruppi distanti (tabella, colonne): ogni gruppo è una casella a sé
            for c in cl:
                for g in c:
                    blk = _make_block(page.number, [g])
                    if blk:
                        out.append(blk)
                    else:
                        keep.append(fitz.Rect(min(pc["bbox"][0] for pc in g), min(pc["bbox"][1] for pc in g),
                                              max(pc["bbox"][2] for pc in g), max(pc["bbox"][3] for pc in g)))
            continue
        paras = _paragraphs(lines, cl)
        if len(paras) > 1:
            for para in paras:
                blk = _para_block(page.number, para, keep)
                if blk:
                    out.append(blk)
            continue
        blk = _para_block(page.number, paras[0], keep) if paras else None
        if blk is None:
            keep += [fitz.Rect(l["bbox"]) for l in lines]
            continue
        # allineamento: righe tutte centrate rispetto al blocco (e di larghezza diversa) → centrato
        blk.lines = len([c for c in cl if c])
        r = blk.rect
        pw = page.rect.width
        if blk.lines == 1 and abs((r.x0 + r.x1) / 2 - pw / 2) < 4 and r.width < pw * 0.8:
            blk.align = "center"                                       # titolo centrato nella pagina
        mids = [((l["bbox"][0] + l["bbox"][2]) / 2) for l in lines]
        lefts = [l["bbox"][0] for l in lines]
        if len(lines) > 1 and all(abs(m - (r.x0 + r.x1) / 2) < 2 for m in mids) and max(lefts) - min(lefts) > 4:
            blk.align = "center"
        out.append(blk)
    return out, rotated


_PROTECT = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"                                   # e-mail
    r"|(?:https?://|www\.)[^\s<>«»\"]+"                                 # indirizzi web
    r"|(?:[A-Za-z]:\\|\\\\|~/|/)[^\s,;«»\"]*[\\/][^\s,;«»\"]*"           # percorsi
    r"|\b[\w.<>…-]+\.(?:pdf|exe|zip|cmd|bat|sh|py|txt|docx?|odt|xlsx?|png|jpe?g|tiff?|cer|p12|pfx|svg|json|xml|html?|md|gz|tar|ini|cfg|icc|ttf|otf)\b",
    re.I)


def _segments(text: str, protected: list) -> list:
    """Divide il testo in pezzi da tradurre e pezzi da lasciare intatti (e-mail, indirizzi, percorsi, nomi di file,
    testo a spaziatura fissa). Restituisce [(testo, protetto)]."""
    spans = [(m.start(), m.end()) for m in _PROTECT.finditer(text)]
    for tok in sorted(set(t for t in protected if len(t) > 1), key=len, reverse=True):
        start = 0
        while True:
            i = text.find(tok, start)
            if i < 0:
                break
            if not any(a < i + len(tok) and i < b for a, b in spans):
                spans.append((i, i + len(tok)))
            start = i + len(tok)
    spans.sort()
    out, pos = [], 0
    for a, b in spans:
        if a < pos:
            continue
        if a > pos:
            out.append((text[pos:a], False))
        out.append((text[a:b], True)); pos = b
    if pos < len(text):
        out.append((text[pos:], False))
    return out or [(text, False)]


def _join_translated(segs: list, tx: dict) -> str:
    """Ricompone i pezzi: quelli da tradurre con la loro traduzione (spazi originali ai bordi), gli altri com'erano."""
    out = []
    for t, prot in segs:
        core = t.strip()
        if prot or not core or core not in tx:
            out.append(t)
        else:
            lead = t[:len(t) - len(t.lstrip())]; trail = t[len(t.rstrip()):]
            out.append(lead + tx[core] + trail)
    return re.sub(r"\s{2,}", " ", "".join(out)).strip()


def _avoid(r: fitz.Rect, keep: list) -> fitz.Rect:
    """Accorcia la zona da cancellare perché non tocchi il testo che resta (ruotato, importi): la redazione toglie
    ogni carattere che la sfiora."""
    r = fitz.Rect(r)
    for k in keep:
        if not r.intersects(k):
            continue
        if k.x1 - r.x0 < r.x1 - k.x0:                  # il testo da tenere sporge dal lato sinistro
            r.x0 = max(r.x0, k.x1 + 0.2)
        else:
            r.x1 = min(r.x1, k.x0 - 0.2)
    return r


def _digits(t: str) -> list:
    """Cifre di ogni numero (senza separatori): «35.500» e «35,500» sono lo stesso numero."""
    return sorted(re.sub(r"\D", "", n) for n in re.findall(r"\d[\d.,\s]*\d|\d", t))


_ASC: dict = {}


def _first_baseline(family: str, bold: bool, italic: bool) -> float:
    """Distanza tra il bordo superiore del riquadro e la linea di base della prima riga, per ogni punto di corpo,
    con l'impaginazione HTML usata per il testo tradotto (si misura una volta per famiglia/stile)."""
    k = (family, bold, italic)
    if k not in _ASC:
        b = _Block(0, fitz.Rect(0, 0, 400, 300), "Hg", 100.0, 0, bold, italic, family, "left")
        d = fitz.open(); pg = d.new_page(width=500, height=400)
        h, css = _html(b, "Hg")
        pg.insert_htmlbox(fitz.Rect(0, 0, 400, 300), h, css=css)
        try:
            sp = pg.get_text("dict")["blocks"][0]["lines"][0]["spans"][0]
            _ASC[k] = sp["origin"][1] / 100.0
        except Exception:
            _ASC[k] = 0.9
        d.close()
    return _ASC[k]


def _html(b: _Block, text: str) -> tuple[str, str]:
    css = ("body, p { margin: 0; padding: 0; } "
           f"* {{ font-family: {b.family}; font-size: {b.size:.2f}px; line-height: 1.12; margin: 0; padding: 0;"
           f" color: #{b.color:06x}; text-align: {b.align};"
           + (" font-weight: bold;" if b.bold else "") + (" font-style: italic;" if b.italic else "")
           + (" white-space: nowrap;" if b.lines == 1 else "") + " }")
    return f"<body style='margin:0'><p>{html.escape(text)}</p></body>", css


def translate_document(data: bytes, src: Optional[str], dst: str, engine: Engine, opts: Optional[Options] = None,
                       progress: Optional[Callable[[str, int, int], bool]] = None) -> tuple[bytes, Report]:
    """Traduce il PDF `data` da `src` (None = rileva) a `dst`. Restituisce i byte del nuovo PDF e il resoconto."""
    opts = opts or Options()
    if dst in RTL:
        raise TranslateError(tr("La traduzione verso lingue scritte da destra a sinistra non è ancora supportata"))
    doc = fitz.open("pdf", data)
    if doc.needs_pass:
        raise TranslateError(tr("Il PDF è protetto da password"))
    try:
        src = src or detect_pdf_language(doc)
        if not src:
            raise TranslateError(tr("Impossibile rilevare la lingua del documento: sceglila a mano"))
        rep = Report(src=src, dst=dst)
        if src == dst:
            raise TranslateError(tr("La lingua di partenza e quella di destinazione coincidono"))
        pages, keeps = [], []
        for p in doc:
            kp: list = []
            bl, rot = _blocks(p, kp)
            pages.append(bl); keeps.append(kp); rep.skipped_rotated += rot
        # testi da tradurre (senza ripetizioni): blocchi, commenti, segnalibri, metadati
        texts: list[str] = []
        pos: dict = {}

        def want(t: str) -> None:
            if t and t not in pos and _LETTER.search(t):
                pos[t] = len(texts); texts.append(t)
        segs = {}
        for bl in pages:
            for b in bl:
                sg = _segments(b.text, b.protected)
                segs[id(b)] = sg
                for t, prot in sg:
                    if not prot:
                        want(t.strip())
        annots = []
        if opts.annotations:
            for p in doc:
                for a in p.annots():
                    c = (a.info or {}).get("content", "")
                    if c.strip() and a.type[0] in (fitz.PDF_ANNOT_TEXT, fitz.PDF_ANNOT_FREE_TEXT, fitz.PDF_ANNOT_SQUARE,
                                                   fitz.PDF_ANNOT_CIRCLE, fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE):
                        annots.append((p.number, a.xref, c))
                        for t, prot in _segments(c, []):
                            if not prot:
                                want(t.strip())
        toc = doc.get_toc(simple=False) if opts.bookmarks else []
        for t in toc:
            for x, prot in _segments(t[1], []):
                if not prot:
                    want(x.strip())
        meta = doc.metadata or {}
        if opts.metadata:
            for k in ("title", "subject"):
                for x, prot in _segments(meta.get(k) or "", []):
                    if not prot:
                        want(x.strip())
        if not texts:
            raise TranslateError(tr("Il PDF non contiene testo da tradurre (se è una scansione serve prima l'OCR)"))

        def tp(a, b):
            return progress(tr("Traduzione"), a, b) if progress else True
        out = engine.translate(texts, src, dst, tp)
        tx = {t: out[i] for t, i in pos.items()}

        def tr_text(t: str, protected=()) -> str:
            return _join_translated(_segments(t, list(protected)), tx)

        # riscrittura: via il testo originale (immagini e grafica restano), poi il testo tradotto nello stesso riquadro
        for pno, bl in enumerate(pages):
            if progress and progress(tr("Impaginazione"), pno, doc.page_count) is False:
                raise TranslateError(tr("Operazione annullata"))
            if not bl:
                continue
            page = doc[pno]
            drawings = []
            for dr in page.get_drawings():
                for it in dr.get("items", []):
                    if it[0] == "l":
                        drawings.append(fitz.Rect(it[1], it[2]).normalize() + (-0.5, -0.5, 0.5, 0.5))
                    elif it[0] == "re":
                        rr = fitz.Rect(it[1])                       # rettangolo: contano i suoi lati (bordi delle celle)
                        drawings += [fitz.Rect(rr.x0 - .5, rr.y0, rr.x0 + .5, rr.y1), fitz.Rect(rr.x1 - .5, rr.y0, rr.x1 + .5, rr.y1)]
            left = min(b.rect.x0 for b in bl)
            for b in bl:
                for lr in b.line_rects or [b.rect]:                # solo le righe di testo, non tutto il riquadro
                    rr = _avoid(fitz.Rect(lr) + (0.3, 0.3, -0.3, -0.3), keeps[pno])
                    if not rr.is_empty:
                        page.add_redact_annot(rr, fill=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
            for b in bl:
                t = _join_translated(segs[id(b)], tx)
                h, css = _html(b, t)
                # stesso riquadro, con il piccolo margine che serve all'interlinea dell'ultima riga; il bordo superiore
                # si sposta perché la prima riga tradotta stia sulla stessa linea di base dell'originale
                top = b.rect.y0
                if b.baseline:
                    top = b.baseline - _first_baseline(b.family, b.bold, b.italic) * b.size
                r = fitz.Rect(b.rect.x0, top, b.rect.x1 + 2, max(b.rect.y1 + 1.5, top + b.size * 1.2))
                if b.lines == 1 and b.align == "left":                 # etichetta: può usare lo spazio libero a destra
                    r.x1 = max(r.x1, _free_right(page.rect, b, [o.rect for o in bl if o is not b], drawings, left))
                spare, scale = page.insert_htmlbox(r, h, css=css, scale_low=opts.min_scale)
                if spare < 0 and b.lines == 1:
                    # una riga che non entra nemmeno rimpicciolita: si permette di andare a capo
                    b.lines = 2; h, css = _html(b, t)
                    spare, scale = page.insert_htmlbox(r, h, css=css, scale_low=opts.min_scale)
                if spare < 0:
                    # non entra alla dimensione minima: si scrive comunque, più piccolo, e lo si segnala (il testo non va perso)
                    page.insert_htmlbox(r, h, css=css, scale_low=0)
                rep.blocks += 1
                if _digits(b.text) != _digits(t):
                    rep.numbers_changed.append((pno + 1, b.text[:40]))
                if spare < 0:
                    rep.overflow.append((pno + 1, b.text[:40]))
                elif scale < 0.999:
                    rep.shrunk += 1
        for pno, xref, c in annots:
            pg = doc[pno]                                          # la pagina deve restare viva mentre si modifica il commento
            a = pg.load_annot(xref)
            if a is not None:
                a.set_info(content=tr_text(c))
                try:
                    a.update()
                except Exception:
                    pass
        if toc:
            doc.set_toc([[t[0], tr_text(t[1]), t[2], *t[3:]] for t in toc])
        if opts.metadata:
            m = dict(meta)
            for k in ("title", "subject"):
                if m.get(k):
                    m[k] = tr_text(m[k])
            doc.set_metadata(m)
        return doc.tobytes(garbage=3, deflate=True), rep
    finally:
        doc.close()


def output_name(path: str, lang: str, pattern: str = DEFAULT_PATTERN, folder: str = "") -> str:
    base = os.path.splitext(os.path.basename(path))[0] if path else tr("documento")
    name = (pattern or DEFAULT_PATTERN).replace("{name}", base).replace("{lang}", lang)
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip() or base
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return os.path.join(folder or (os.path.dirname(path) if path else os.getcwd()), name)
