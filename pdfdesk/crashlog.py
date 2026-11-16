# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Registro degli errori. Su Windows il programma non ha una console: senza registro un errore resta invisibile.
#   - eccezioni Python non gestite (anche quelle nelle azioni dell'interfaccia e nei thread) → traccia completa;
#   - crash interni delle librerie (accesso a memoria non valida, abort…) → faulthandler scrive dove si trovava ogni thread;
#   - messaggi gravi di Qt.
# Un file «session.lock» rimasto dalla sessione precedente indica che il programma non si è chiuso normalmente:
# al riavvio l'interfaccia lo segnala e indica il registro.
from __future__ import annotations

import datetime
import faulthandler
import os
import platform
import sys
import threading
import traceback

from .paths import data_dir

LOG_NAME = "pdfdesk-errori.log"
MAX_SIZE = 1_000_000                     # oltre 1 MB il registro viene ruotato (una copia .1)

_file = None
_gui_notify = None                       # funzione dell'interfaccia per avvisare l'utente di un errore
_previous_crash = False
_installed = False


def log_path() -> str:
    return os.path.join(data_dir(), LOG_NAME)


def _lock_path() -> str:
    return os.path.join(data_dir(), "session.lock")


def _header() -> str:
    from . import __version__
    return (f"PDFDesk {__version__} · Python {platform.python_version()} · {platform.platform()} · "
            f"{'eseguibile' if getattr(sys, 'frozen', False) else 'sorgenti'}")


def write(text: str) -> None:
    """Aggiunge una voce al registro (con data e versione)."""
    f = _file
    if f is None:
        return
    try:
        f.write(f"\n===== {datetime.datetime.now().isoformat(timespec='seconds')} · {_header()}\n{text.rstrip()}\n")
        f.flush()
    except Exception:
        pass


def _excepthook(etype, value, tb) -> None:
    text = "".join(traceback.format_exception(etype, value, tb))
    write("Eccezione non gestita:\n" + text)
    try:
        sys.__stderr__ and sys.__stderr__.write(text)
    except Exception:
        pass
    if _gui_notify is not None and not issubclass(etype, (KeyboardInterrupt, SystemExit)):
        try:
            _gui_notify(f"{etype.__name__}: {value}")
        except Exception:
            pass


def _thread_hook(args) -> None:
    if args.exc_type is SystemExit:
        return
    write(f"Eccezione nel thread {getattr(args.thread, 'name', '?')}:\n"
          + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


def install(gui: bool = False) -> None:
    """Attiva il registro. Con `gui=True` crea anche il segnale di sessione aperta (per riconoscere un crash)."""
    global _file, _previous_crash, _installed
    if _installed:
        return
    _installed = True
    try:
        p = log_path()
        if os.path.exists(p) and os.path.getsize(p) > MAX_SIZE:
            os.replace(p, p + ".1")
        _file = open(p, "a", encoding="utf-8", errors="replace")
    except OSError:
        _file = None
    if _file is not None:
        try:
            faulthandler.enable(file=_file, all_threads=True)       # crash nativi: traccia di tutti i thread
        except Exception:
            pass
    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    if gui:
        lock = _lock_path()
        _previous_crash = os.path.exists(lock)
        try:
            with open(lock, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass
        if _previous_crash:
            write("La sessione precedente non si è chiusa normalmente.")


def install_qt_handler() -> None:
    """Messaggi gravi di Qt (critical/fatal) nel registro."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:
        return

    def handler(mode, ctx, msg):
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            write(f"Qt: {msg}")

    qInstallMessageHandler(handler)


def set_gui_notify(func) -> None:
    global _gui_notify
    _gui_notify = func


def previous_crash() -> bool:
    return _previous_crash


def clean_exit() -> None:
    """Chiusura normale: toglie il segnale di sessione aperta."""
    try:
        os.remove(_lock_path())
    except OSError:
        pass


def recent_entries(max_chars: int = 6000) -> str:
    try:
        with open(log_path(), encoding="utf-8", errors="replace") as f:
            return f.read()[-max_chars:]
    except OSError:
        return ""
