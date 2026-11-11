# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Scansione da scanner: SANE (Linux, macOS con sane-backends) e WIA (Windows); creazione di PDF dalle immagini acquisite.
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional

import pymupdf as fitz

MODES = {"color": "Colore", "gray": "Scala di grigi", "bw": "Bianco e nero"}
SOURCES = {"flatbed": "Piano di scansione", "adf": "Alimentatore automatico (ADF)"}
# formati carta in mm (larghezza, altezza); None = area massima dello scanner
PAPER = {"max": ("Area massima", None), "a4": ("A4", (210, 297)), "a5": ("A5", (148, 210)),
         "letter": ("Letter", (216, 279)), "legal": ("Legal", (216, 356)), "a3": ("A3", (297, 420))}
SANE_MODE = {"color": "Color", "gray": "Gray", "bw": "Lineart"}


class ScanError(Exception):
    pass


@dataclass
class Scanner:
    backend: str        # "sane" | "wia"
    id: str
    name: str

    @property
    def label(self) -> str:
        return f"{self.name}  [{self.backend.upper()}]"


@dataclass
class ScanParams:
    mode: str = "color"
    dpi: int = 300
    source: str = "flatbed"
    paper: str = "a4"


def _hidden() -> dict:
    if os.name == "nt":
        si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": 0x08000000}
    return {}


def _run(cmd: list[str], timeout: int = 120, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout, **_hidden(), **kw)


def scanimage_path() -> Optional[str]:
    return shutil.which("scanimage")


def _powershell() -> Optional[str]:
    return shutil.which("powershell") or shutil.which("pwsh")


def available_backends() -> list[str]:
    out = []
    if scanimage_path():
        out.append("sane")
    if os.name == "nt" and _powershell():
        out.append("wia")
    return out


# ---------------------------------------------------------------------- SANE
def sane_list() -> list[Scanner]:
    exe = scanimage_path()
    if not exe:
        return []
    r = _run([exe, "-f", "%d|%v %m|%t%n"], timeout=60)
    res = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("|")
        if len(parts) >= 2 and parts[0].strip():
            res.append(Scanner("sane", parts[0].strip(), parts[1].strip()))
    return res


def _sane_cmd(dev: str, prm: ScanParams, fmt: str = "png") -> list[str]:
    cmd = [scanimage_path() or "scanimage", "-d", dev, f"--format={fmt}", f"--resolution={prm.dpi}",
           f"--mode={SANE_MODE.get(prm.mode, 'Color')}"]
    if prm.source == "adf":
        cmd += ["--source", "ADF"]
    elif prm.source == "flatbed":
        cmd += ["--source", "Flatbed"]
    size = PAPER.get(prm.paper, PAPER["max"])[1]
    if size:
        cmd += ["-l", "0", "-t", "0", "-x", str(size[0]), "-y", str(size[1])]
    return cmd


def _next_name(folder: str) -> str:
    n = len([f for f in os.listdir(folder) if f.startswith("scan") and f.endswith(".png")]) + 1
    return os.path.join(folder, f"scan{n:04d}.png")


def sane_scan(dev: str, prm: ScanParams, folder: str, progress: Optional[Callable[[int], bool]] = None) -> list[str]:
    """Acquisisce una pagina (piano) o tutte le pagine dell'alimentatore. Restituisce i file PNG."""
    base = _sane_cmd(dev, prm)
    if prm.source == "adf":
        sub = tempfile.mkdtemp(prefix="batch", dir=folder)
        r = _run(base + [f"--batch={os.path.join(sub, 'p%04d.png')}", "--batch-start=1"], timeout=1800)
        got = sorted(os.path.join(sub, x) for x in os.listdir(sub) if x.endswith(".png"))
        # un alimentatore che si svuota termina con errore «out of documents»: se ci sono pagine, è normale
        if not got and r.returncode != 0:
            shutil.rmtree(sub, ignore_errors=True)
            raise ScanError(r.stderr.decode("utf-8", "replace").strip() or "scansione non riuscita")
        files = []
        for g in got:              # nomi progressivi unici: più scansioni successive non si sovrascrivono
            dst = _next_name(folder)
            shutil.move(g, dst); files.append(dst)
        shutil.rmtree(sub, ignore_errors=True)
        return files
    r = _run(base, timeout=600)
    if r.returncode != 0 or not r.stdout:
        msg = r.stderr.decode("utf-8", "replace").strip()
        # alcuni scanner non hanno l'opzione --source: ritenta senza
        if "source" in msg.lower() and "--source" in base:
            i = base.index("--source")
            r = _run(base[:i] + base[i + 2:], timeout=600)
            msg = r.stderr.decode("utf-8", "replace").strip()
        if r.returncode != 0 or not r.stdout:
            raise ScanError(msg or "scansione non riuscita")
    path = _next_name(folder)
    with open(path, "wb") as f:
        f.write(r.stdout)
    return [path]


# ---------------------------------------------------------------------- WIA (Windows)
_WIA_LIST = r"""
$ErrorActionPreference='Stop'
$m = New-Object -ComObject WIA.DeviceManager
foreach ($d in $m.DeviceInfos) { if ($d.Type -eq 1) { "{0}|{1}" -f $d.DeviceID, $d.Properties.Item('Name').Value } }
"""

_WIA_SCAN = r"""
param([string]$Dev,[int]$Dpi,[int]$Intent,[int]$Adf,[int]$W,[int]$H,[string]$Out)
$ErrorActionPreference='Stop'
function SetP($o,$id,$v){ try { $o.Properties.Item($id).Value = $v } catch {} }
$m = New-Object -ComObject WIA.DeviceManager
$info = $null
foreach ($d in $m.DeviceInfos) { if ($d.DeviceID -eq $Dev) { $info = $d } }
if ($info -eq $null) { throw 'Scanner non trovato' }
$dev = $info.Connect()
$i = 0
do {
  if ($Adf -eq 1) { SetP $dev 3088 1 } else { SetP $dev 3088 2 }
  $item = $dev.Items.Item(1)
  SetP $item 6146 $Intent
  SetP $item 6147 $Dpi
  SetP $item 6148 $Dpi
  SetP $item 6149 0
  SetP $item 6150 0
  if ($W -gt 0) { SetP $item 6151 ([int]($W / 25.4 * $Dpi)); SetP $item 6152 ([int]($H / 25.4 * $Dpi)) }
  try { $img = $item.Transfer('{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}') } catch {
    if ($i -gt 0) { break } else { throw }
  }
  $i++
  $f = Join-Path $Out ('scan{0:D4}.png' -f $i)
  $img.SaveFile($f)
  if ($Adf -ne 1) { break }
  # altra pagina nell'alimentatore? (bit 1 di «Document Handling Status» = feeder pronto)
  $st = 0; try { $st = $dev.Properties.Item(3087).Value } catch {}
  if (($st -band 1) -eq 0) { break }
} while ($true)
"""


def wia_list() -> list[Scanner]:
    ps = _powershell()
    if os.name != "nt" or not ps:
        return []
    r = _run([ps, "-NoProfile", "-NonInteractive", "-Command", _WIA_LIST], timeout=60)
    res = []
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if "|" in line:
            a, b = line.split("|", 1)
            res.append(Scanner("wia", a.strip(), b.strip()))
    return res


def wia_scan(dev: str, prm: ScanParams, folder: str) -> list[str]:
    ps = _powershell()
    if not ps:
        raise ScanError("PowerShell non disponibile")
    script = os.path.join(folder, "wia_scan.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(_WIA_SCAN)
    size = PAPER.get(prm.paper, PAPER["max"])[1] or (0, 0)
    intent = {"color": 1, "gray": 2, "bw": 4}.get(prm.mode, 1)
    out = os.path.join(folder, "wia")
    os.makedirs(out, exist_ok=True)
    r = _run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script, "-Dev", dev,
              "-Dpi", str(prm.dpi), "-Intent", str(intent), "-Adf", "1" if prm.source == "adf" else "0",
              "-W", str(size[0]), "-H", str(size[1]), "-Out", out], timeout=1800)
    files = sorted(os.path.join(out, x) for x in os.listdir(out) if x.endswith(".png"))
    if not files:
        raise ScanError(r.stderr.decode("utf-8", "replace").strip() or "scansione non riuscita")
    final = []
    for f in files:                       # sposta nella cartella principale con numerazione progressiva
        dst = _next_name(folder)
        shutil.move(f, dst); final.append(dst)
    shutil.rmtree(out, ignore_errors=True)
    return final


# ---------------------------------------------------------------------- interfaccia comune
def list_scanners() -> list[Scanner]:
    res = []
    for fn in (wia_list, sane_list):
        try:
            res += fn()
        except Exception:
            pass
    return res


def scan_pages(sc: Scanner, prm: ScanParams, folder: str) -> list[str]:
    os.makedirs(folder, exist_ok=True)
    try:
        return wia_scan(sc.id, prm, folder) if sc.backend == "wia" else sane_scan(sc.id, prm, folder)
    except subprocess.TimeoutExpired as e:
        raise ScanError("lo scanner non ha risposto in tempo") from e
    except FileNotFoundError as e:
        raise ScanError(str(e)) from e


# ---------------------------------------------------------------------- immagini → PDF
def tesseract_path() -> Optional[str]:
    return shutil.which("tesseract")


def images_to_pdf(files: list[str], out_path: str, dpi: int = 300, jpeg_quality: int = 0, ocr_lang: str = "",
                  progress: Optional[Callable[[int, int], bool]] = None, title: str = "") -> int:
    """Crea un PDF con una pagina per immagine, alla dimensione fisica data da `dpi`.

    `jpeg_quality` > 0: ricodifica le pagine a colori/grigio come JPEG (file molto più piccolo).
    `ocr_lang`: lingua Tesseract (es. «ita+eng»): il testo riconosciuto rende il PDF ricercabile.
    """
    from PIL import Image
    if not files:
        raise ScanError("Nessuna pagina")
    out = fitz.open()
    tess = tesseract_path() if ocr_lang else None
    n = len(files)
    try:
        for i, f in enumerate(files):
            if progress and progress(i, n) is False:
                raise ScanError("Operazione annullata")
            im = Image.open(f)
            xres = im.info.get("dpi", (dpi, dpi))[0] or dpi
            try:
                res = int(round(float(xres))) if float(xres) > 1 else dpi
            except Exception:
                res = dpi
            if not im.info.get("dpi"):
                res = dpi
            w, h = im.size
            data = None
            if jpeg_quality and im.mode not in ("1",):
                buf = io.BytesIO(); im.convert("L" if im.mode == "L" else "RGB").save(buf, "JPEG", quality=jpeg_quality, dpi=(res, res))
                data = buf.getvalue()
            else:
                buf = io.BytesIO(); (im if im.mode in ("1", "L", "RGB") else im.convert("RGB")).save(buf, "PNG")
                data = buf.getvalue()
            im.close()
            page = out.new_page(width=w * 72.0 / res, height=h * 72.0 / res)
            page.insert_image(page.rect, stream=data)
            if tess:
                _ocr_page(out, page, f, tess, ocr_lang)
        if title:
            out.set_metadata({"title": title})
        out.save(out_path, garbage=3, deflate=True)
        if progress:
            progress(n, n)
        return n
    finally:
        out.close()


def _ocr_page(doc: fitz.Document, page: fitz.Page, img_path: str, tess: str, lang: str) -> None:
    """Sovrappone alla pagina il livello di testo invisibile prodotto da Tesseract (PDF «sandwich»)."""
    tmp = tempfile.mkdtemp(prefix="pdfdesk-ocr-")
    try:
        base = os.path.join(tmp, "o")
        r = _run([tess, img_path, base, "-l", lang, "pdf"], timeout=300)
        if r.returncode != 0 or not os.path.exists(base + ".pdf"):
            return
        o = fitz.open(base + ".pdf")
        idx = page.number
        doc.insert_pdf(o, from_page=0, to_page=0, start_at=idx)
        doc.delete_page(idx + 1)
        o.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ocr_languages() -> list[str]:
    t = tesseract_path()
    if not t:
        return []
    try:
        r = _run([t, "--list-langs"], timeout=20)
        return [x.strip() for x in r.stdout.decode().splitlines()[1:] if x.strip() and x.strip() != "osd"]
    except Exception:
        return []
