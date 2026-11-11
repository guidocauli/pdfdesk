# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# selftest.py: autodiagnosi dell'installazione/eseguibile (usata anche dalla CI su ogni piattaforma).
from __future__ import annotations

import os
import sys
import tempfile

from . import VERSION_LINE


def run() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    results: list[tuple[str, bool, str]] = []

    def step(name, fn):
        try:
            detail = fn() or ""
            results.append((name, True, str(detail)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {e}"))

    import pymupdf as fitz
    tmp = tempfile.mkdtemp(prefix="pdfdesk-selftest-")
    src = os.path.join(tmp, "prova.pdf")
    ctx: dict = {}

    def make():
        d = fitz.open()
        for i in range(2):
            p = d.new_page()
            p.insert_text((72, 100), f"Pagina {i + 1} àèìòù — SEGRETO 12345", fontsize=14)
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 900, 900), False)
        pm.set_rect(pm.irect, (30, 120, 200))
        d[0].insert_image(fitz.Rect(72, 200, 400, 528), stream=pm.tobytes("jpeg"))
        d.save(src)
        return f"PyMuPDF {fitz.__version__}"

    def core():
        from .core import PdfDocument
        d = PdfDocument.open(src)
        d.add_ink(0, [[(10, 10), (80, 60), (140, 20)]], (1, 0, 0), 3)
        d.add_shape(0, "rect", fitz.Rect(200, 600, 300, 660), (0, 0, 1), (1, 1, 0.5))
        d.add_text(0, fitz.Rect(72, 650, 300, 720), "Nota", 12)
        d.add_markup(0, "hl", fitz.Rect(70, 80, 300, 110))
        d.add_redact(0, fitz.Rect(d.page(0).search_for("SEGRETO")[0]) + (-2, -2, 60, 2))
        d.apply_redactions()
        assert "SEGRETO" not in d.page(0).get_text(), "la redazione non ha rimosso il testo"
        assert d.undo() and d.redo()
        ctx["bytes"] = d.current_bytes()
        d.close()
        return "annotazioni, redazione, annulla/ripeti"

    def fontsf():
        from . import fonts
        from .core import PdfDocument
        cand = [p for d in fonts.system_dirs() for p in
                (os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs if f.lower().endswith((".ttf", ".otf")))][:200]
        if not cand:
            return "nessun font di sistema da provare (saltato)"
        code = None
        for p in cand:
            try:
                code = fonts.add_user_font(p)
                break
            except Exception:
                continue
        assert code, "nessun font utilizzabile"
        d = PdfDocument.new()
        x = d.add_text(0, fitz.Rect(60, 100, 360, 160), "Font personale àèì €", 16, code)
        assert d.annot_info(0, x).fontname == code
        d.set_rect(0, x, fitz.Rect(60, 120, 400, 220))
        fonts.remove_user_font(code[1:])
        d.close()
        return "casella con font TTF/OTF: " + code[1:]

    def forms():
        from .core import PdfDocument
        doc = fitz.open()
        p = doc.new_page()
        for t, r, n in ((fitz.PDF_WIDGET_TYPE_TEXT, (72, 100, 300, 120), "nome"), (fitz.PDF_WIDGET_TYPE_CHECKBOX, (72, 140, 86, 154), "ok")):
            w = fitz.Widget(); w.field_type = t; w.rect = fitz.Rect(*r); w.field_name = n; p.add_widget(w)
        f = os.path.join(tmp, "modulo.pdf"); doc.save(f)
        d = PdfDocument.open(f)
        fl = {x.name: x for x in d.list_fields(0)}
        d.set_field(0, fl["nome"].xref, "Guido"); d.set_field(0, fl["ok"].xref, True)
        assert "Guido" in d.page(0).get_text() and d.flatten_forms() == 2
        return "campi di testo e casella, appiattimento"

    def card():
        from . import signing
        import pkcs11  # noqa: F401
        return "modulo PKCS#11 incluso; moduli trovati: %d" % len(signing.pkcs11_candidates())

    def standards():
        from . import pdfstd
        gs = pdfstd.find_gs()
        if not gs:
            if getattr(sys, "frozen", False):
                raise RuntimeError("Ghostscript non incluso nel pacchetto")
            return "Ghostscript non installato (saltato)"
        out = pdfstd.convert(ctx["bytes"], "pdfa-2b", title="Selftest")
        rep = pdfstd.check(out, "pdfa-2b")
        assert rep.ok, rep.text()
        x = pdfstd.convert(ctx["bytes"], "pdfx-4", title="Selftest")
        rx = pdfstd.check(x, "pdfx-4")
        assert rx.ok, rx.text()
        assert "Pagina 1" in fitz.open("pdf", out)[0].get_text(), "testo perso nella conversione"
        return f"PDF/A-2b e PDF/X-4 ({os.path.basename(gs)}, {rep.validator})"

    def comp():
        from . import compress
        out = compress.optimize_bytes(ctx["bytes"], compress.SaveOptions("low"))
        assert fitz.open("pdf", out)[0].get_text().strip(), "testo perso"
        ctx["small"] = out
        return f"{len(ctx['bytes'])} → {len(out)} byte"

    def sign():
        from . import signing
        p12 = os.path.join(tmp, "t.p12")
        signing.create_self_signed_p12(p12, "pw", "PDFDesk Selftest")
        img = os.path.join(tmp, "s.png")
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), False)
        pm.set_rect(pm.irect, (0, 0, 120))
        pm.save(img)
        signed = signing.sign_pdf_bytes(ctx["small"], signing.SignParams(p12, "pw", "test", "qui", page=0, box=(300, 100, 520, 190),
                                                                          image_path=img))
        st = signing.verify_pdf_bytes(signed)
        assert st and st[0].intact and st[0].valid, "firma non valida"
        ctx["signed"] = signed
        return "firma visibile con immagine + verifica"

    def gui():
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QEventLoop, QTimer
        from .mainwindow import MainWindow
        app = QApplication.instance() or QApplication(sys.argv[:1])
        path = os.path.join(tmp, "firmato.pdf")
        open(path, "wb").write(ctx["signed"])
        w = MainWindow(path)
        w.resize(1100, 760)
        w.show()
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()
        assert w.pdf and w.pdf.is_signed
        _, pix, rs, _ = w.view.page_items[0]
        assert not pix.pixmap().isNull(), "pagina non disegnata"
        w.pdf.modified = False
        w.close()
        return "finestra, rendering, documento firmato"

    step("creazione PDF di prova", make)
    step("core", core)
    step("font TTF/OTF", fontsf)
    step("moduli", forms)
    step("smart card", card)
    step("standard PDF/A e PDF/X", standards)
    step("compressione", comp)
    step("firma digitale", sign)
    def par():
        from . import export, parallel
        d = fitz.open()
        for i in range(12):
            d.new_page().insert_text((72, 100), f"pagina {i}", fontsize=14)
        out = os.path.join(tmp, "par")
        old = os.environ.get("PDFDESK_CORES")
        os.environ["PDFDESK_CORES"] = str(max(2, parallel.cpu_total()))
        try:
            files = export.export_images(d, list(range(12)), "png", out, dpi=50)
        finally:
            os.environ.pop("PDFDESK_CORES", None)
            if old is not None:
                os.environ["PDFDESK_CORES"] = old
        assert len(files) == 12 and all(os.path.getsize(f) > 100 for f in files), "esportazione parallela incompleta"
        return f"{parallel.cpu_total()} processori, fino a {parallel.max_workers()} in uso"

    def exports():
        from . import export
        d = fitz.open(src)
        done = []
        for fmt, ext in (("txt", "txt"), ("docx", "docx"), ("odt", "odt")):
            out = os.path.join(tmp, "esporta." + ext)
            export.export(d, fmt, [0, 1], out)
            assert os.path.getsize(out) > 20, f"esportazione {fmt} vuota"
            done.append(fmt.upper())
        d.close()
        return ", ".join(done)

    def modules():
        import importlib.util
        names = ("compress", "core", "export", "export_fixed", "extract", "fonts", "imgutil", "merge", "parallel", "paths", "pdfstd",
                 "scan", "signing", "sigstore", "textbox", "updater", "selftest", "cli", "view", "dialogs", "mainwindow", "icons", "theme", "printing", "inmenu", "i18n", "i18n_en")
        missing = [n for n in names if importlib.util.find_spec("pdfdesk." + n) is None]   # senza importarli (alcuni richiedono Qt)
        assert not missing, "moduli assenti dal pacchetto: " + ", ".join(missing)       # es. scartati dalla compilazione per sintassi non valida
        return f"{len(names)} moduli presenti"

    step("moduli del programma", modules)
    step("esportazione TXT/DOCX/ODT", exports)
    step("calcolo parallelo", par)
    step("interfaccia", gui)
    lines = [VERSION_LINE]
    ok = True
    for name, good, detail in results:
        lines.append(f"[{'OK' if good else 'ERRORE'}] {name}" + (f" — {detail}" if detail else ""))
        ok &= good
    report = "\n".join(lines)
    try:   # su Windows l'eseguibile grafico può non avere console: il rapporto resta anche su file (scritto prima della stampa)
        with open(os.path.join(tempfile.gettempdir(), "pdfdesk-selftest.log"), "w", encoding="utf-8") as f:
            f.write(report + "\n")
    except OSError:
        pass
    try:
        print(report)
    except (UnicodeError, OSError, ValueError):
        pass
    return 0 if ok else 1
