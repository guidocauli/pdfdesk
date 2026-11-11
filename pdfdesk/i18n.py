# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# i18n.py: testi dell'interfaccia «tokenizzati». Ogni testo visibile passa da tr(): la lingua sorgente è l'italiano e il
# catalogo i18n_en.py fornisce la traduzione inglese. La lingua si sceglie in Preferenze (si applica al riavvio).
from __future__ import annotations

_lang: str | None = None
_en: dict | None = None
LANGUAGES = [("it", "Italiano"), ("en", "English")]


def language() -> str:
    global _lang
    if _lang is None:
        try:
            from PySide6.QtCore import QSettings
            v = str(QSettings("GuidoCauli", "PDFDesk").value("ui/lang", "it"))
        except Exception:
            v = "it"
        _lang = v if v in dict(LANGUAGES) else "it"
    return _lang


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in dict(LANGUAGES) else "it"


def catalog() -> dict:
    global _en
    if _en is None:
        from .i18n_en import EN
        _en = EN
    return _en


def tr(s: str) -> str:
    """Traduce un testo dell'interfaccia (italiano → lingua scelta). Se manca la traduzione resta l'italiano."""
    if language() == "it":
        return s
    return catalog().get(s, s)
