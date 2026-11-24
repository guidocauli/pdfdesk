# PDFDesk — Guido Cauli
# wayland.py: Wayland nativo e dimensioni delle finestre su Linux (anche con compositor a tasselli: niri, Hyprland,
# sway, river, i3…).
#
# - Piattaforma: in una sessione Wayland il programma usa Wayland nativo, con ripiego automatico su X11 (XWayland) se il
#   supporto Wayland non si carica; Preferenze → Aspetto permette di forzare X11. QT_QPA_PLATFORM già impostata vince.
# - Identità della finestra: app_id «pdfdesk», uguale al file .desktop (icona, raggruppamento, regole del compositor).
# - Dimensioni: sui compositor a tasselli la dimensione la decide il compositor, quindi quella salvata non si impone;
#   altrove la dimensione salvata o iniziale si riduce se supera lo schermo. I dialoghi (che sui compositor a tasselli
#   galleggiano) non superano mai lo schermo disponibile.
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QObject, QSize

TILING = {"niri": "niri", "hyprland": "Hyprland", "sway": "sway", "river": "river", "i3": "i3", "dwl": "dwl",
          "qtile": "Qtile", "wayfire": "Wayfire", "labwc": "", "cosmic": ""}


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def wayland_session() -> bool:
    return is_linux() and (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY")))


def tiling_compositor() -> str:
    """Nome del compositor/gestore a tasselli in uso, o "" (GNOME, KDE, Windows, macOS…)."""
    if not is_linux():
        return ""
    if os.environ.get("NIRI_SOCKET"):
        return "niri"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "Hyprland"
    if os.environ.get("SWAYSOCK"):
        return "sway"
    if os.environ.get("I3SOCK"):
        return "i3"
    desk = (os.environ.get("XDG_CURRENT_DESKTOP", "") + ":" + os.environ.get("XDG_SESSION_DESKTOP", "")).lower()
    for key, name in TILING.items():
        if name and key in desk.split(":"):
            return name
    return ""


def platform_pref() -> str:
    """Preferenza salvata: "auto" (Wayland dove c'è), "x11" (XWayland)."""
    try:
        from PySide6.QtCore import QSettings
        v = str(QSettings("GuidoCauli", "PDFDesk").value("ui/platform", "auto"))
    except Exception:
        return "auto"
    return v if v in ("auto", "x11") else "auto"


def configure_platform() -> str:
    """Da chiamare prima di creare QApplication. Restituisce la lista di piattaforme scelta ("" = non toccata)."""
    if not is_linux() or "QT_QPA_PLATFORM" in os.environ:
        return ""
    if platform_pref() == "x11" and os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    elif wayland_session():
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"        # Wayland nativo; se non si carica, X11 (XWayland)
    else:
        return ""
    return os.environ["QT_QPA_PLATFORM"]


def available_size(widget) -> QSize:
    scr = widget.screen() if widget is not None else None
    if scr is None:
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
    return scr.availableGeometry().size() if scr is not None else QSize(1280, 800)


def fit_size(size: QSize, avail: QSize, ratio: float = 0.92) -> QSize:
    """`size` ridotta, se serve, a `ratio` dello spazio disponibile."""
    mw, mh = int(avail.width() * ratio), int(avail.height() * ratio)
    return QSize(min(size.width(), mw), min(size.height(), mh))


def restore_main_geometry(win, saved) -> None:
    """Dimensione della finestra principale all'avvio: sui compositor a tasselli decide il compositor (la geometria
    salvata non si impone); altrove si ripristina e la si riduce se è più grande dello schermo."""
    if tiling_compositor():
        return
    if saved:
        win.restoreGeometry(saved)
    if not win.isMaximized() and not win.isFullScreen():
        # lo schermo su cui la finestra si trova davvero (con più monitor non è per forza quello principale)
        from PySide6.QtGui import QGuiApplication
        scr = QGuiApplication.screenAt(win.geometry().center()) or win.screen()
        avail = scr.availableGeometry().size() if scr is not None else available_size(win)
        s = fit_size(win.size(), avail, 0.96)
        if s != win.size():
            win.resize(s)


class DialogFitter(QObject):
    """Filtro dell'applicazione: ogni dialogo, quando compare, sta entro lo schermo disponibile (anche la sua dimensione
    minima). Serve su schermi piccoli e sui compositor a tasselli, dove i dialoghi galleggiano sopra la finestra."""

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if ev.type() == QEvent.Show:
            from PySide6.QtWidgets import QDialog
            if isinstance(obj, QDialog) and obj.isWindow():
                avail = available_size(obj)
                lim = fit_size(QSize(10 ** 6, 10 ** 6), avail, 0.95)
                if obj.minimumWidth() > lim.width() or obj.minimumHeight() > lim.height():
                    obj.setMinimumSize(min(obj.minimumWidth(), lim.width()), min(obj.minimumHeight(), lim.height()))
                if obj.width() > lim.width() or obj.height() > lim.height():
                    obj.resize(fit_size(obj.size(), avail, 0.95))
        return False


def describe() -> str:
    """Per l'autodiagnosi e il registro: piattaforma e compositor."""
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    plat = app.platformName() if app else os.environ.get("QT_QPA_PLATFORM", "?")
    comp = tiling_compositor()
    return f"piattaforma {plat}" + (f", compositor a tasselli {comp}" if comp else "") + \
        (", sessione Wayland" if wayland_session() else "")
