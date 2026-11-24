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
    p.add_argument("--fonts", default="keep", choices=[k for k, _ in compress.FONT_MODES],
                   help="con --compress: keep (come sono), subset (ridotti ai caratteri usati), embed (incorpora anche i "
                        "mancanti), unembed (toglie i font a codifica standard)")
    p.add_argument("--standard", choices=list(pdfstd.STANDARDS), metavar="STD",
                   help="con --compress: converte a uno standard (" + ", ".join(pdfstd.STANDARDS) + "); con --check: standard da verificare")
    p.add_argument("--icc", metavar="FILE", help="con --standard pdfx-*: profilo ICC di stampa (CMYK)")
    p.add_argument("--check", metavar="FILE", help="verifica la conformità di un PDF allo standard di --standard (o a quello dichiarato)")
    p.add_argument("--merge", nargs="+", metavar=("OUTPUT", "INPUT"), help="unisce i PDF/immagini INPUT (nell'ordine dato) in OUTPUT")
    p.add_argument("--meta-from", type=int, metavar="N",
                   help="con --merge: copia i metadati dall'N-esimo file (1 = il primo; 0 = nessuno). "
                        "Predefinito: il primo PDF dell'elenco che ha metadati")
    p.add_argument("--translate", nargs="+", metavar="FILE", help="traduce i PDF nella lingua di --to (crea NOME_translated_LINGUA.pdf)")
    p.add_argument("--to", metavar="LINGUA", help="con --translate: lingua di destinazione (codice ISO, es. en, it, de)")
    p.add_argument("--from", dest="src", metavar="LINGUA", help="con --translate: lingua di partenza (se assente viene rilevata)")
    p.add_argument("--name", metavar="SCHEMA", help="con --translate: nome dei file tradotti, con {name} e {lang} (predefinito {name}_translated_{lang})")
    p.add_argument("--outdir", metavar="CARTELLA", help="con --translate o --ocr: cartella dei file di uscita (predefinita: quella dell'originale)")
    p.add_argument("--engine", choices=["local", "deepl", "libretranslate"], default="local",
                   help="con --translate: motore (local senza internet; deepl usa DEEPL_KEY; libretranslate usa LIBRETRANSLATE_URL e LIBRETRANSLATE_KEY)")
    p.add_argument("--verify", metavar="FILE", help="verifica le firme digitali di un PDF")
    p.add_argument("--install-ocr", metavar="CARTELLA", help="scarica le lingue OCR predefinite (italiano, inglese) in CARTELLA/tessdata (usato dall'installatore Windows)")
    p.add_argument("--ocr", nargs="+", metavar="PDF", help="rende ricercabili (OCR) i PDF indicati, salvandoli come nome_ocr.pdf")
    p.add_argument("--ocr-lang", metavar="LINGUE", help="con --ocr: lingue Tesseract, es. ita+eng (predefinite)")
    p.add_argument("--ocr-suffix", default="_ocr", metavar="SUFFISSO", help="con --ocr: suffisso dei file di uscita (predefinito _ocr)")
    p.add_argument("--ocr-all", action="store_true", help="con --ocr: riconosce anche le pagine che hanno già testo")
    p.add_argument("--dpi", type=int, default=300, help="con --ocr: risoluzione del riconoscimento (predefinita 300)")
    p.add_argument("--overwrite", action="store_true", help="con --ocr: sovrascrive i file di uscita esistenti")
    p.add_argument("--ocr-download", metavar="LINGUE", help="scarica le lingue OCR indicate (es. ita+eng+deu) nella cartella dei dati")
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
    from . import crashlog
    crashlog.install(gui=False)                # registro degli errori (anche per la riga di comando)
    args = build_parser().parse_args(argv)
    # file di ingresso mancanti: messaggio chiaro invece di una traccia Python
    inputs = []
    if args.compress:
        inputs.append(args.compress[0])
    for a in ("check", "verify"):
        v = getattr(args, a, None)
        if isinstance(v, str):
            inputs.append(v)
    for a in ("merge",):
        v = getattr(args, a, None)
        if v:
            inputs += list(v[1:])
    if args.translate:
        inputs += list(args.translate)
    missing = [f for f in inputs if not os.path.isfile(f)]
    if missing:
        print(f"{VERSION_LINE}\nERRORE: file non trovato: " + ", ".join(missing), file=sys.stderr)
        return 2
    if args.selftest:
        from .selftest import run
        return run()
    if args.version:
        print(VERSION_LINE)
        return 0
    if args.install_ocr or args.ocr_download:
        # il motore OCR è nel programma: si scaricano solo le lingue (installatore Windows: accanto al programma)
        from . import ocr
        codes = [c.strip() for c in (args.ocr_download or "+".join(ocr.DEFAULT_LANGS)).replace(",", "+").split("+") if c.strip()]
        dest = os.path.join(args.install_ocr, "tessdata") if args.install_ocr else ""
        try:
            got = ocr.download(codes, dest=dest)
        except Exception as e:
            print(f"Errore: {e}", file=sys.stderr); return 1
        print(f"{VERSION_LINE}\n" + (f"lingue scaricate: {', '.join(got)}" if got else "lingue già presenti")
              + f"\ncartella: {dest or ocr.user_dir()}")
        return 0
    if args.ocr:
        from . import ocr
        bad = [f for f in args.ocr if not os.path.isfile(f)]
        if bad:
            print(f"{VERSION_LINE}\nERRORE: file non trovato: {', '.join(bad)}", file=sys.stderr)
            return 2
        langs = (args.ocr_lang or "+".join(ocr.DEFAULT_LANGS)).replace(",", "+")
        errors = 0
        print(VERSION_LINE)
        for f in args.ocr:
            out = ocr.output_name(f, args.ocr_suffix, args.outdir or "", args.overwrite)
            try:
                rep = ocr.ocr_file(f, out, langs, only_missing=not args.ocr_all, dpi=args.dpi)
                print(f"{f} → {out}: {rep.text()}")
            except Exception as e:  # noqa: BLE001
                errors += 1
                print(f"{f}: ERRORE: {e}", file=sys.stderr)
        return 1 if errors else 0
    if args.compress:
        src, dst = args.compress
        if os.path.abspath(src) == os.path.abspath(dst):
            print(f"{VERSION_LINE}\nERRORE: --compress crea un nuovo file: OUTPUT deve essere diverso da INPUT", file=sys.stderr)
            return 2
        data = open(src, "rb").read()
        rep: dict = {}
        try:
            o = compress.SaveOptions(args.preset, args.gray, args.strip_metadata and not args.standard, False, args.standard, args.icc)
            o.font_mode, o.report = args.fonts, rep
            out = compress.optimize_bytes(data, o)
        except pdfstd.StandardError as e:
            print(f"{VERSION_LINE}\nERRORE: {e}", file=sys.stderr)
            return 3
        compress.write_atomic(dst, out)
        print(f"{VERSION_LINE}\n{src} → {dst}: {compress.human_size(len(data))} → {compress.human_size(len(out))}")
        if "fonts_embedded" in rep:
            print(f"font incorporati: {rep['fonts_embedded']}" + (f"; ancora mancanti: {', '.join(rep['fonts_missing'])}"
                                                                  if rep["fonts_missing"] else ""))
        elif "fonts_removed" in rep:
            print(f"font tolti: {rep['fonts_removed']}; rimasti incorporati: {rep['fonts_kept']}")
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
        mf = None if args.meta_from is None else (-1 if args.meta_from == 0 else args.meta_from - 1)
        if mf is not None and not -1 <= mf < len(args.merge) - 1:
            print(f"{VERSION_LINE}\nERRORE: --meta-from deve essere tra 0 e {len(args.merge) - 1}", file=sys.stderr)
            return 3
        try:
            n = merge.merge_pdfs([{"path": f} for f in args.merge[1:]], args.merge[0], meta_from=mf)
        except merge.MergeError as e:
            print(f"{VERSION_LINE}\nERRORE: {e}", file=sys.stderr)
            return 3
        print(f"{VERSION_LINE}\n{args.merge[0]}: {n} pagine")
        return 0
    if args.translate:
        from . import translate as T
        if not args.to:
            print(f"{VERSION_LINE}\nERRORE: --translate richiede --to LINGUA", file=sys.stderr)
            return 3
        eng = T.make_engine(args.engine, os.environ.get("DEEPL_KEY", ""), os.environ.get("LIBRETRANSLATE_URL", ""),
                            os.environ.get("LIBRETRANSLATE_KEY", ""))
        print(VERSION_LINE)
        rc = 0
        index = None
        for f in args.translate:
            try:
                with open(f, "rb") as fh:
                    data = fh.read()
                src = args.src
                if not src:
                    import pymupdf as fitz
                    with fitz.open("pdf", data) as d:
                        src = T.detect_pdf_language(d)
                if not src:
                    raise T.TranslateError("lingua non rilevata: indicala con --from")
                if isinstance(eng, T.LocalEngine) and not eng.ready(src, args.to):
                    index = index or T.fetch_index()
                    for m in T.models_needed(src, args.to, index):
                        print(f"scaricamento del modello {m.src} → {m.dst}…", flush=True)
                        T.install_model(m)
                out_data, rep = T.translate_document(data, src, args.to, eng)
                out = T.output_name(f, args.to, args.name or T.DEFAULT_PATTERN, args.outdir or "")
                from .compress import write_atomic
                if os.path.dirname(out):
                    os.makedirs(os.path.dirname(out), exist_ok=True)     # --outdir non ancora esistente
                write_atomic(out, out_data)
                print(f"{f} → {out}\n  " + rep.text().replace("\n", "\n  "))
            except Exception as e:
                print(f"{f}: ERRORE: {e}", file=sys.stderr)
                rc = 3
        return rc
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
    from . import wayland
    wayland.configure_platform()               # Linux: Wayland nativo con ripiego su X11, o X11 se scelto
    from .icons import app_icon
    from .mainwindow import MainWindow
    app = QApplication(sys.argv[:1])
    _fitter = wayland.DialogFitter(app)
    app.installEventFilter(_fitter)            # i dialoghi restano entro lo schermo (schermi piccoli, niri, Hyprland…)
    app.setApplicationName("PDFDesk")
    app.setOrganizationName("GuidoCauli")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    app.setDesktopFileName("pdfdesk")          # collega la finestra al file .desktop (icona e raggruppamento su Wayland e X11)
    from . import crashlog
    crashlog.install(gui=True)
    crashlog.install_qt_handler()
    w = MainWindow(path)
    crashlog.set_gui_notify(w.notify_error)
    w.show()
    if crashlog.previous_crash():
        from PySide6.QtCore import QTimer
        QTimer.singleShot(400, w.report_previous_crash)
    rc = app.exec()
    crashlog.set_gui_notify(None)
    from . import shutdown
    shutdown.close_all_widgets()               # chiusura ordinata (vedi shutdown.py)
    crashlog.clean_exit()
    return rc
