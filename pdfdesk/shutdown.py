# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Chiusura ordinata dell'interfaccia.
#
# Molte finestre collegano ai segnali dei propri widget delle funzioni che citano «self» (lambda, funzioni locali): la connessione
# vive nel lato C++ e tiene vivo l'oggetto Python, quindi il ciclo non lo vede il garbage collector e le finestre restano
# in vita fino alla fine del programma. PySide le distrugge allora, in un ordine qualsiasi e mentre l'interprete si sta
# smontando: può capitare un accesso a memoria già liberata («malloc(): unaligned tcache chunk», segmentation fault).
# Distruggere i widget noi, in ordine e con l'interprete ancora intero, evita il problema.
from __future__ import annotations

import atexit
import gc

_installed = False


def close_all_widgets() -> None:
    """Chiude ed elimina tutte le finestre di primo livello (e i loro figli) mentre Python è ancora completo."""
    try:
        import shiboken6
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        for w in list(QApplication.topLevelWidgets()):
            try:
                w.close()
            except Exception:
                pass
        app.processEvents()
        gc.collect()
        for w in list(QApplication.topLevelWidgets()):
            try:
                if shiboken6.isValid(w):
                    shiboken6.delete(w)
            except Exception:
                pass
        app.processEvents()
        gc.collect()
    except Exception:
        pass


def install_atexit() -> None:
    """Registra la pulizia alla fine dell'interprete (utile ai test, che lasciano finestre aperte). Viene eseguita prima di quella di PySide."""
    global _installed
    if not _installed:
        _installed = True
        atexit.register(close_all_widgets)


def watchdog(seconds: int = 900) -> None:
    """Per i test: se un processo resta bloccato (es. una finestra modale che nessuno chiude) dopo `seconds` secondi stampa dove
    si trova ogni thread e termina, invece di tenere occupata per ore una macchina di GitHub Actions."""
    import faulthandler
    faulthandler.dump_traceback_later(seconds, exit=True)
