# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# theme.py: tema chiaro/scuro. «Sistema» segue l'impostazione del sistema operativo (Windows, macOS, Linux/GNOME/KDE).
from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

SYSTEM, LIGHT, DARK = 0, 1, 2
_native_style: str | None = None


def _linux_dark() -> bool | None:
    """Rilevamento di riserva su Linux quando Qt non conosce lo schema colori (piattaforma senza portale/tema)."""
    gtk = os.environ.get("GTK_THEME", "")
    if gtk:
        return "dark" in gtk.lower()
    try:
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=1.5).stdout.lower()
        if "dark" in out:
            return True
        if "default" in out or "light" in out:
            return False
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                             capture_output=True, text=True, timeout=1.5).stdout.lower()
        if out.strip():
            return "dark" in out
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        with open(os.path.expanduser("~/.config/kdeglobals"), encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("ColorScheme="):
                    return "dark" in line.lower()
    except OSError:
        pass
    return None


def system_is_dark(app: QApplication) -> bool:
    cs = app.styleHints().colorScheme()
    if cs == Qt.ColorScheme.Dark:
        return True
    if cs == Qt.ColorScheme.Light:
        return False
    if sys.platform.startswith("linux"):
        d = _linux_dark()
        if d is not None:
            return d
    pal = app.palette()                      # ultima risorsa: com'è la tavolozza di sistema
    return pal.window().color().lightness() < 128


def dark_palette() -> QPalette:
    p = QPalette()
    win, base, alt, text = QColor(45, 45, 48), QColor(30, 30, 33), QColor(52, 52, 56), QColor(228, 228, 230)
    dis = QColor(130, 130, 134)
    for role, col in ((QPalette.Window, win), (QPalette.WindowText, text), (QPalette.Base, base), (QPalette.AlternateBase, alt),
                      (QPalette.ToolTipBase, QColor(60, 60, 64)), (QPalette.ToolTipText, text), (QPalette.Text, text),
                      (QPalette.Button, QColor(58, 58, 62)), (QPalette.ButtonText, text), (QPalette.BrightText, QColor(255, 90, 90)),
                      (QPalette.Link, QColor(95, 170, 255)), (QPalette.Highlight, QColor(46, 120, 210)),
                      (QPalette.HighlightedText, QColor(255, 255, 255)), (QPalette.PlaceholderText, dis),
                      (QPalette.Light, QColor(80, 80, 85)), (QPalette.Midlight, QColor(66, 66, 70)),
                      (QPalette.Mid, QColor(40, 40, 43)), (QPalette.Dark, QColor(25, 25, 27)), (QPalette.Shadow, QColor(0, 0, 0))):
        p.setColor(role, col)
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, dis)
    p.setColor(QPalette.Disabled, QPalette.Highlight, QColor(70, 70, 76))
    return p


def apply(app: QApplication, mode: int) -> bool:
    """Applica il tema. Restituisce True se il tema risultante è scuro."""
    global _native_style
    if _native_style is None:
        _native_style = app.style().objectName() or "Fusion"
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        try:
            hints.setColorScheme({LIGHT: Qt.ColorScheme.Light, DARK: Qt.ColorScheme.Dark}.get(mode, Qt.ColorScheme.Unknown))
        except Exception:
            pass
    dark = {LIGHT: False, DARK: True}.get(mode)
    if dark is None:
        dark = system_is_dark(app)
    if dark:
        # Fusion è l'unico stile Qt identico su Windows e Linux che si lascia colorare del tutto
        if app.style().objectName().lower() != "fusion":
            app.setStyle("Fusion")
        app.setPalette(dark_palette())
    else:
        if (app.style().objectName() or "").lower() != (_native_style or "").lower():
            app.setStyle(_native_style)
        app.setPalette(app.style().standardPalette())
    return dark
