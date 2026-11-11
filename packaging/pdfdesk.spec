# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Specifica PyInstaller: un solo file eseguibile, senza console (GUI), con i comandi da terminale ancora disponibili.
import re, sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = collect_submodules("pyhanko") + collect_submodules("pyhanko_certvalidator") + collect_submodules("pkcs11") + ["PIL.Image", "fontTools.subset", "aiohttp", "asn1crypto"]
datas = collect_data_files("pyhanko") + collect_data_files("pyhanko_certvalidator")
excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick",
            "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtNetwork",
            # componenti non usati (modelli di analisi layout, calcolo scientifico, ecc.): pesano decine di MB
            "numpy", "scipy", "lxml", "pydantic", "pydantic_core", "onnxruntime", "pymupdf4llm", "pymupdf_layout",
            "pymupdf.layout", "pandas", "matplotlib", "IPython", "pkg_resources", "setuptools", "pytest"]
DROP = ("onnx", "pymupdf/layout", "qgtk3", "libgtk", "libgdk", "libcairo", "libpango", "libatk", "libharfbuzz-icu")



def ghostscript_bundle():
    """Include Ghostscript (motore della conversione PDF/A e PDF/X) con le sue risorse: eseguibile, librerie, Resource, lib,
    profili ICC e font base. Si prende quello installato sul computer di compilazione (o indicato da PDFDESK_GS)."""
    import glob, os, shutil, subprocess
    win = sys.platform == "win32"
    gs = os.environ.get("PDFDESK_GS") or next((shutil.which(n) for n in (("gswin64c", "gswin32c") if win else ("gs",)) if shutil.which(n)), None)
    if not gs and win:
        g = sorted(glob.glob(r"C:\Program Files\gs\gs*\bin\gswin64c.exe"))
        gs = g[-1] if g else None
    if not gs:
        print("ATTENZIONE: Ghostscript non trovato: PDF/A e PDF/X non saranno disponibili nel pacchetto.")
        return [], []
    gs = os.path.realpath(gs)
    bindir = os.path.dirname(gs)
    root = os.path.dirname(bindir)
    ver = subprocess.run([gs, "--version"], capture_output=True, text=True).stdout.strip()
    bins = [(gs, "gs/bin")]
    for dll in glob.glob(os.path.join(bindir, "gsdll*.dll")):
        bins.append((dll, "gs/bin"))
    share_roots = [os.path.join(root, "share", "ghostscript", ver), os.path.join(root, "share", "ghostscript"), root,
                   os.path.join("/usr/share/ghostscript", ver), os.path.join("/opt/homebrew/share/ghostscript", ver),
                   os.path.join("/usr/local/share/ghostscript", ver)]
    # area di staging: copie reali (non link simbolici, che nel pacchetto resterebbero puntati al computer di compilazione)
    stage = os.path.abspath(os.path.join(SPECPATH, "..", "build", "gs-stage"))
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    data = []

    def stage_dir(src, dest, skip_links_in=None):
        dst = os.path.join(stage, dest)
        def ign(d, names):
            if skip_links_in and os.path.basename(d) == skip_links_in:      # Resource/Font: solo collegamenti ai font URW (copiati a parte)
                return [n for n in names if os.path.islink(os.path.join(d, n))]
            return []
        shutil.copytree(src, dst, symlinks=False, ignore=ign)
        data.append((dst, "gs/share/" + dest))

    def add(name, dest, extra=(), skip=None):
        for base in share_roots:
            for cand in (os.path.join(base, name),) + tuple(extra):
                if os.path.isdir(cand) and os.listdir(cand):
                    stage_dir(os.path.realpath(cand), dest, skip)
                    return
        print(f"ATTENZIONE: cartella Ghostscript «{name}» non trovata")
    add("Resource", "Resource", skip="Font")
    add("lib", "lib")
    add("iccprofiles", "iccprofiles", ("/usr/share/color/icc/ghostscript",))
    fonts = ["/usr/share/fonts/type1/urw-base35", "/usr/share/ghostscript/fonts", "/opt/homebrew/share/ghostscript/fonts",
             "/usr/local/share/ghostscript/fonts", os.path.join(root, "fonts"), os.path.join(root, "share", "ghostscript", "fonts")]
    for f in fonts:
        if os.path.isdir(f) and any(n.lower().endswith((".t1", ".pfb", ".otf", ".ttf")) for n in os.listdir(f)):
            stage_dir(os.path.realpath(f), "fonts")
            break
    else:
        print("ATTENZIONE: font URW di Ghostscript non trovati: i font base-14 non saranno incorporabili")
    print(f"Ghostscript {ver} incluso da {gs}")
    return bins, data


gs_bins, gs_data = ghostscript_bundle()


def qt_plugin_fallback():
    """Rete di sicurezza: se l'hook di PySide6 non riesce a interrogare Qt (accade con Wine e in qualche ambiente
    insolito) i plugin indispensabili — piattaforma, stili, formati immagine — verrebbero omessi e il programma
    non partirebbe. Li aggiungiamo esplicitamente; i doppioni vengono eliminati da PyInstaller."""
    import os, PySide6
    base = os.path.join(os.path.dirname(PySide6.__file__), "plugins")
    out = []
    for sub in ("platforms", "styles", "imageformats", "iconengines", "platforminputcontexts", "generic"):
        d = os.path.join(base, sub)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith((".dll", ".so", ".dylib")) and "debug" not in f.lower() and not f.lower().endswith("d.dll"):
                    out.append((os.path.join(d, f), "PySide6/plugins/" + sub))
    return out


gs_bins = gs_bins + (qt_plugin_fallback() if sys.platform == "win32" else [])
a = Analysis(["../run_pdfdesk.py"], pathex=[".."], binaries=gs_bins, datas=datas + gs_data, hiddenimports=hidden, excludes=excludes, noarchive=False)
a.binaries = [b for b in a.binaries if not any(d in b[0].lower() for d in DROP)]
a.datas = [d for d in a.datas if not any(x in d[0].lower() for x in DROP)]
pyz = PYZ(a.pure)
common = dict(name="pdfdesk", debug=False, strip=False, upx=False, console=False, disable_windowed_traceback=False)
if sys.platform == "darwin":
    # su macOS: cartella dentro il bundle .app (più affidabile del file singolo)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, argv_emulation=False, **common)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="pdfdesk")
    app = BUNDLE(coll, name="PDFDesk.app", bundle_identifier="it.guidocauli.pdfdesk",
                 info_plist={"CFBundleShortVersionString": re.search(r'__version__ = "(.*)"', open("../pdfdesk/__init__.py", encoding="utf-8").read()).group(1), "NSHighResolutionCapable": True,
                             "CFBundleDocumentTypes": [{"CFBundleTypeName": "PDF", "CFBundleTypeExtensions": ["pdf"],
                                                        "CFBundleTypeRole": "Editor"}]})
else:
    # Windows/Linux: un unico file eseguibile
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **common)
