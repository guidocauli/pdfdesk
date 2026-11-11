# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# cli.py: avvio dell'applicazione e comandi da terminale (comprimi / verifica / informazioni).
from __future__ import annotations

import argparse
import os
import sys

from . import AUTHOR, VERSION_LINE, __version__, compress, pdfstd


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdfdesk",
        description=f"{VERSION_LINE}\nEditor PDF: visualizza, annota, redigi, firma e comprimi.",
        epilog=f"{AUTHOR}", formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="*", help="PDF da aprire (ognuno in una scheda)")
    p.add_argument("-V", "--version", action="store_true", help="mostra la versione ed esce")
    p.add_argument("--compress", nargs=2, metavar=("INPUT", "OUTPUT"), help="comprime un PDF senza aprire la grafica")
    p.add_argument("--preset", default="medium", choices=[x.key for x in compress.PRESETS],
                   help="qualità per --compress (default: medium)")
    p.add_argument("--gray", action="store_true", help="con --compress: immagini in scala di grigi")
    p.add_argument("--strip-metadata", action="store_true", help="con --compress: rimuove i metadati")
    p.add_argument("--standard", choices=list(pdfstd.STANDARDS), metavar="STD",
                   help="con --compress: converte a uno standard (" + ", ".join(pdfstd.STANDARDS) + "); con --check: standard da verificare")
    p.add_argument("--icc", metavar="FILE", help="con --standard pdfx-*: profilo ICC di stampa (CMYK)")
    p.add_argument("--check", metavar="FILE", help="verifica la conformità di un PDF allo standard di --standard (o a quello dichiarato)")
    p.add_argument("--merge", nargs="+", metavar=("OUTPUT", "INPUT"), help="unisce i PDF/immagini INPUT (nell'ordine dato) in OUTPUT")
    p.add_argument("--verify", metavar="FILE", help="verifica le firme digitali di un PDF")
    p.add_argument("--install-ocr", metavar="CARTELLA", help="Windows: scarica e installa Tesseract (OCR) nella CARTELLA (usato dall'installatore)")
    p.add_argument("--selftest", action="store_true", help="autodiagnosi: prova tutte le funzioni principali ed esce")
    return p


def _attach_console() -> None:
    """Su Windows l'eseguibile grafico non ha console: ci si aggancia a quella del chiamante per stampare l'output."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
            sys.stderr = open("CONOUT$", "w", encoding="utf-8")
    except Exception:
        pass


def main(argv=None) -> int:
    import multiprocessing
    multiprocessing.freeze_support()           # eseguibili congelati: i processi figli non devono riaprire il programma
    argv = sys.argv[1:] if argv is None else argv
    for st in (sys.stdout, sys.stderr):        # Windows: la console usa spesso cp1252 e non stampa «→», «—» ecc.
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
    if argv and (argv[0].startswith("-") or len(argv) > 1):
        _attach_console()
    args = build_parser().parse_args(argv)
    if args.selftest:
        from .selftest import run
        return run()
    if args.version:
        print(VERSION_LINE)
        return 0
    if args.install_ocr:
        from . import scan
        try:
            print(f"{VERSION_LINE}\n" + scan.install_tesseract(args.install_ocr))
        except Exception as e:
            print(f"Errore: {e}", file=sys.stderr); return 1
        return 0
    if args.compress:
        src, dst = args.compress
        data = open(src, "rb").read()
        try:
            out = compress.optimize_bytes(data, compress.SaveOptions(args.preset, args.gray, args.strip_metadata and not args.standard,
                                                                     False, args.standard, args.icc))
        except pdfstd.StandardError as e:
            print(f"{VERSION_LINE}\nERRORE: {e}", file=sys.stderr)
            return 3
        compress.write_atomic(dst, out)
        print(f"{VERSION_LINE}\n{src} → {dst}: {compress.human_size(len(data))} → {compress.human_size(len(out))}")
        return 0
    if args.check:
        data = open(args.check, "rb").read()
        declared = pdfstd.detect(data)
        key = args.standard
        if not key and declared:
            from .dialogs import StandardDialog
            key = StandardDialog._key_for(declared)
        print(VERSION_LINE)
        if not key:
            print(f"Standard dichiarato: {declared or 'nessuno'}. Indica quello da verificare con --standard.")
            return 2
        rep = pdfstd.check(data, key)
        print(rep.text())
        return 0 if rep.ok else 2
    if args.merge:
        from . import merge
        if len(args.merge) < 2:
            print(f"{VERSION_LINE}\nERRORE: --merge richiede OUTPUT e almeno un file da unire", file=sys.stderr)
            return 3
        try:
            n = merge.merge_pdfs([{"path": f} for f in args.merge[1:]], args.merge[0])
        except merge.MergeError as e:
            print(f"{VERSION_LINE}\nERRORE: {e}", file=sys.stderr)
            return 3
        print(f"{VERSION_LINE}\n{args.merge[0]}: {n} pagine")
        return 0
    if args.verify:
        from . import signing
        sts = signing.verify_pdf_bytes(open(args.verify, "rb").read())
        print(VERSION_LINE)
        if not sts:
            print("Nessuna firma digitale.")
        for s in sts:
            print(f"- {s.field}: {s.signer} | integra={'sì' if s.intact and s.valid else 'NO'} | attendibile={'sì' if s.trusted else 'no'} | {s.coverage}")
        return 0 if all(s.intact and s.valid for s in sts) else 2
    return run_gui(args.file or None)


def ui_scale_percent() -> int:
    """Scala dell'interfaccia scelta nelle Preferenze (0 = automatica: segue la densità dello schermo)."""
    try:
        from PySide6.QtCore import QSettings
        v = int(QSettings("GuidoCauli", "PDFDesk").value("ui/scale", 0))
    except Exception:
        return 0
    return v if v == 0 or 50 <= v <= 400 else 0


def configure_hidpi() -> None:
    """Da chiamare prima di creare QApplication: scale frazionarie esatte (125 %, 150 %…) invece che arrotondate, e
    l'eventuale scala forzata dall'utente. Una variabile QT_SCALE_FACTOR già impostata ha la precedenza."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    pct = ui_scale_percent()
    if pct and "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = f"{pct / 100:.3f}".rstrip("0").rstrip(".")


def run_gui(path=None) -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    configure_hidpi()
    from .icons import app_icon
    from .mainwindow import MainWindow
    app = QApplication(sys.argv[:1])
    app.setApplicationName("PDFDesk")
    app.setOrganizationName("GuidoCauli")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    app.setDesktopFileName("pdfdesk")          # collega la finestra al file .desktop (icona e raggruppamento su Wayland e X11)
    w = MainWindow(path)
    w.show()
    rc = app.exec()
    from . import shutdown
    shutdown.close_all_widgets()               # chiusura ordinata (vedi shutdown.py)
    return rc
