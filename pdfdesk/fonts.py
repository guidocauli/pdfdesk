# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# fonts.py: libreria dei font TrueType/OpenType (.ttf/.otf): font dell'utente e font di sistema.
#
# Un font è identificato da un "codice": un nome base-14 ("helv", "tiro", "cour", ...) oppure "@Nome" per un
# font TTF/OTF, risolto in un file tramite la libreria.
from __future__ import annotations

import json
import os
import shutil
import sys
import threading

import pymupdf as fitz

from . import paths

BASE_FONTS = [("Helvetica", "helv"), ("Times", "tiro"), ("Courier", "cour")]
EXTS = (".ttf", ".otf")

_lock = threading.Lock()
_user: dict[str, str] = {}
_system: dict[str, str] = {}
_system_ready = False
_scan_started = False


def is_custom(code: str | None) -> bool:
    return bool(code) and code.startswith("@")


def user_dir() -> str:
    return paths.data_dir("fonti")


def system_dirs() -> list[str]:
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        win = os.environ.get("WINDIR", r"C:\Windows")
        return [os.path.join(win, "Fonts"), os.path.join(os.environ.get("LOCALAPPDATA", home), "Microsoft", "Windows", "Fonts")]
    if sys.platform == "darwin":
        return ["/System/Library/Fonts", "/Library/Fonts", os.path.join(home, "Library", "Fonts")]
    return ["/usr/share/fonts", "/usr/local/share/fonts", os.path.join(home, ".fonts"),
            os.path.join(home, ".local", "share", "fonts")]


def font_name(path: str) -> str | None:
    """Nome interno del font, oppure None se il file non è un TTF/OTF leggibile."""
    try:
        name = fitz.Font(fontfile=path).name
        return name.strip() if name and name.strip() else None
    except Exception:
        return None


def refresh_user() -> None:
    found: dict[str, str] = {}
    d = user_dir()
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(EXTS):
            p = os.path.join(d, f)
            n = font_name(p)
            if n:
                found.setdefault(n, p)
    with _lock:
        _user.clear()
        _user.update(found)


def add_user_font(src: str) -> str:
    """Copia un file TTF/OTF nella libreria dell'utente; restituisce il codice del font ("@Nome")."""
    if not src.lower().endswith(EXTS):
        raise ValueError("sono supportati solo file .ttf e .otf")
    n = font_name(src)
    if not n:
        raise ValueError("il file non è un font TrueType/OpenType valido")
    dest = os.path.join(user_dir(), os.path.basename(src))
    if os.path.abspath(src) != os.path.abspath(dest):
        shutil.copyfile(src, dest)
    refresh_user()
    with _lock:
        _user[n] = dest
    return "@" + n


def remove_user_font(name: str) -> None:
    with _lock:
        p = _user.pop(name, None)
    if p and os.path.exists(p):
        os.remove(p)


def _cache_file() -> str:
    return os.path.join(paths.data_dir(), "font-di-sistema.json")


def scan_system() -> None:
    """Scansiona i font di sistema (con cache per file/data di modifica)."""
    global _system_ready
    cache: dict = {}
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        pass
    new_cache: dict = {}
    found: dict[str, str] = {}
    for root in system_dirs():
        for dp, _dn, files in os.walk(root):
            for fn in files:
                if not fn.lower().endswith(EXTS):
                    continue
                p = os.path.join(dp, fn)
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    continue
                ent = cache.get(p)
                if ent and ent[0] == mt:
                    name = ent[1]
                else:
                    name = font_name(p)
                new_cache[p] = [mt, name]
                if name:
                    found.setdefault(name, p)
    try:
        with open(_cache_file(), "w", encoding="utf-8") as f:
            json.dump(new_cache, f)
    except OSError:
        pass
    with _lock:
        _system.clear()
        _system.update(found)
        _system_ready = True


def start_system_scan() -> None:
    """Avvia la scansione dei font di sistema in background (una sola volta)."""
    global _scan_started
    if _scan_started:
        return
    _scan_started = True
    threading.Thread(target=scan_system, daemon=True).start()


def system_ready() -> bool:
    return _system_ready


def resolve(code: str | None) -> str | None:
    """Percorso del file di un font personalizzato ("@Nome"), o None se non disponibile."""
    if not is_custom(code):
        return None
    name = code[1:]
    with _lock:
        return _user.get(name) or _system.get(name)


def choices() -> list[tuple[str, str]]:
    """Elenco (etichetta, codice): base-14, font dell'utente, font di sistema."""
    with _lock:
        user = sorted(_user, key=str.lower)
        system = sorted((n for n in _system if n not in _user), key=str.lower)
    out = list(BASE_FONTS)
    out += [(n, "@" + n) for n in user]
    out += [(n, "@" + n) for n in system]
    return out


def label_for(code: str) -> str:
    for label, c in BASE_FONTS:
        if c == code:
            return label
    return code[1:] if is_custom(code) else code


refresh_user()
