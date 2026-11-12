# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Test della traduzione dei PDF: estrazione delle caselle, riscrittura nel riquadro (con rimpicciolimento), tabelle,
# numeri, commenti/segnalibri/metadati, nomi dei file, finestra «Traduci PDF», riga di comando.
import os, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))          # make_samples (anche con python -I)
TMP = tempfile.mkdtemp(prefix="pdfdesk-tr-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")

import pymupdf as fitz
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, TMP)
app = QApplication.instance() or QApplication([])
from make_samples import block_modal_dialogs; block_modal_dialogs()
from pdfdesk import shutdown as _shutdown; _shutdown.install_atexit(); _shutdown.watchdog()
from pdfdesk import translate as T


def wait(ms=80): QTest.qWait(ms)


class FakeEngine(T.Engine):
    """Traduzione finta: maiuscolo e testo più lungo (per provare il rimpicciolimento)."""
    name = "fake"

    def __init__(self, longer=True, numbers=False):
        self.longer, self.numbers, self.calls = longer, numbers, []

    def translate(self, texts, src, dst, progress=None):
        self.calls.append((list(texts), src, dst))
        out = []
        for t in texts:
            u = t.upper() + (" ALLUNGATO CON PAROLE IN PIÙ" if self.longer else "")
            if self.numbers:
                u = u.replace("4", "5")
            out.append(u)
        if progress:
            progress(len(texts), len(texts))
        return out


def make_doc(path):
    d = fitz.open(); p = d.new_page(width=595, height=842)
    p.insert_text((40, 60), "Relazione tecnica sul progetto di ricerca", fontsize=18, fontname="hebo")
    p.insert_textbox(fitz.Rect(40, 80, 555, 140),
                     "Il presente documento descrive l'infrastruttura utilizzata per l'analisi dei dati. "
                     "Il sistema è composto da quattordici nodi di calcolo collegati a un archivio condiviso.",
                     fontsize=11, fontname="tiro")
    y = 170
    for a, b in (("Voce", "Importo"), ("Server di calcolo", "48.000 EUR"), ("Archivio di rete", "35.500 EUR")):
        p.draw_rect(fitz.Rect(40, y, 300, y + 22), color=(0, 0, 0)); p.draw_rect(fitz.Rect(300, y, 555, y + 22), color=(0, 0, 0))
        p.insert_text((46, y + 15), a, fontsize=10); p.insert_text((306, y + 15), b, fontsize=10); y += 22
    p.insert_text((40, 300), "Pagina 4 di 12, rif. 2024", fontsize=9)
    p.insert_text((40, 330), "Firma", fontsize=10)
    p.insert_text((40, 360), "Testo ruotato in verticale", fontsize=10, rotate=90)
    p.add_text_annot((500, 60), "Controllare i costi con l'ufficio acquisti.")
    p2 = d.new_page(); p2.insert_text((40, 60), "Seconda pagina con un breve paragrafo di testo italiano.", fontsize=11)
    d.set_toc([[1, "Introduzione", 1], [1, "Seconda parte", 2]])
    d.set_metadata({"title": "Relazione tecnica", "subject": "Analisi dei costi"})
    d.save(path); d.close()


SRC = os.path.join(TMP, "relazione.pdf"); make_doc(SRC)


class BlockTests(unittest.TestCase):
    def test_blocks_split_table_cells_and_skip_numbers(self):
        bl, rot = T._blocks(fitz.open(SRC)[0])
        texts = [b.text for b in bl]
        for t in ("Voce", "Importo", "Server di calcolo", "Archivio di rete", "Firma"):
            self.assertIn(t, texts)                                       # ogni cella è una casella a sé
        self.assertFalse(any("EUR" in t for t in texts))                  # importi: non si traducono
        self.assertTrue(any(t.startswith("Il presente documento") for t in texts))
        self.assertEqual(rot, 1)                                          # testo ruotato: lasciato com'è

    def test_sentences_and_digits(self):
        self.assertEqual(len(T.split_sentences("Prima frase. Seconda frase! Terza? Sì.")), 4)
        self.assertEqual(len(T.split_sentences("Vedi es. il punto 3. Poi altro.")), 2)
        self.assertEqual(T._digits("35.500 EUR e 12"), T._digits("35,500 EUR and 12"))
        self.assertNotEqual(T._digits("pagina 4"), T._digits("page 5"))
        self.assertTrue(T._only_numbers("35.500 EUR")); self.assertFalse(T._only_numbers("Pagina 4 di 12"))

    def test_detect_language(self):
        self.assertEqual(T.detect_pdf_language(fitz.open(SRC)), "it")
        self.assertIsNone(T.detect_language("ciao"))
        self.assertEqual(T.detect_language("This document describes the infrastructure used for data analysis."), "en")

    def test_output_name(self):
        self.assertEqual(T.output_name("/a/b/doc.pdf", "en"), os.path.join("/a/b", "doc_translated_en.pdf"))
        self.assertEqual(T.output_name("/a/b/doc.pdf", "de", "{lang}-{name}", "/x"), os.path.join("/x", "de-doc.pdf"))
        self.assertEqual(os.path.basename(T.output_name("/a/doc.pdf", "en", "a/b:{name}")), "a_b_doc.pdf")

    def test_route(self):
        av = {("it", "en"), ("en", "de")}
        self.assertEqual(T.route("it", "en", av), [("it", "en")])
        self.assertEqual(T.route("it", "de", av), [("it", "en"), ("en", "de")])    # passando per l'inglese
        self.assertIsNone(T.route("de", "it", av))
        self.assertEqual(T.route("it", "it", av), [])


class DocumentTests(unittest.TestCase):
    def test_translate_document(self):
        eng = FakeEngine()
        data, rep = T.translate_document(open(SRC, "rb").read(), None, "en", eng, T.Options(min_scale=0.3))
        self.assertEqual(rep.src, "it"); self.assertEqual(eng.calls[0][1:], ("it", "en"))
        d = fitz.open("pdf", data)
        txt = d[0].get_text()
        self.assertIn("RELAZIONE TECNICA", txt); self.assertIn("VOCE", txt); self.assertIn("IMPORTO", txt)
        self.assertNotIn("Il presente documento", txt)                  # il testo originale non resta sotto
        self.assertIn("48.000 EUR", txt)                                  # importi intatti
        self.assertIn("Testo ruotato in verticale", txt)                  # ruotato: invariato
        self.assertIn("SECONDA PAGINA", d[1].get_text())
        self.assertGreater(rep.shrunk, 0)                                 # il testo più lungo è stato rimpicciolito
        self.assertEqual(rep.skipped_rotated, 1)
        self.assertIn("CONTROLLARE I COSTI", [a.info["content"] for a in d[0].annots()][0])
        self.assertEqual([t[1][:12] for t in d.get_toc()], ["INTRODUZIONE", "SECONDA PART"])
        self.assertTrue(d.metadata["title"].startswith("RELAZIONE TECNICA"))
        # le caselle restano nello stesso posto: il titolo tradotto inizia dove iniziava l'originale
        r0 = fitz.open(SRC)[0].search_for("Relazione tecnica")[0]
        r1 = d[0].search_for("RELAZIONE")[0]
        self.assertLess(abs(r0.x0 - r1.x0), 2); self.assertLess(abs(r0.y0 - r1.y0), 4)
        # ogni riga tradotta resta dentro la pagina
        for b in d[0].get_text("dict")["blocks"]:
            self.assertTrue(fitz.Rect(b["bbox"]) in d[0].rect + (-1, -1, 1, 1))

    def test_shrink_and_overflow_report(self):
        d = fitz.open(); p = d.new_page()
        # paragrafo di più righe in una colonna stretta, con un'altra colonna accanto: non può allargarsi
        self.assertGreater(p.insert_textbox(fitz.Rect(50, 50, 170, 110), "Testo da tradurre in una colonna stretta, "
                                            "su più righe, per la prova del limite", fontsize=10), 0)
        self.assertGreater(p.insert_textbox(fitz.Rect(190, 50, 400, 110), "Colonna accanto", fontsize=10), 0)
        data = d.tobytes()
        _, rep = T.translate_document(data, "it", "en", FakeEngine(), T.Options(min_scale=0.9))
        self.assertTrue(rep.overflow)                                     # sotto il minimo non entra: segnalato
        _, rep2 = T.translate_document(data, "it", "en", FakeEngine(), T.Options(min_scale=0.3))
        self.assertFalse(rep2.overflow); self.assertGreater(rep2.shrunk, 0)

    def test_numbers_changed_reported(self):
        _, rep = T.translate_document(open(SRC, "rb").read(), "it", "en", FakeEngine(longer=False, numbers=True))
        self.assertTrue(rep.numbers_changed)
        self.assertIn("numeri", rep.text())

    def test_options_and_errors(self):
        data, _ = T.translate_document(open(SRC, "rb").read(), "it", "en", FakeEngine(),
                                       T.Options(annotations=False, bookmarks=False, metadata=False))
        d = fitz.open("pdf", data)
        self.assertEqual(d.get_toc()[0][1], "Introduzione"); self.assertEqual(d.metadata["title"], "Relazione tecnica")
        with self.assertRaises(T.TranslateError):
            T.translate_document(open(SRC, "rb").read(), "it", "it", FakeEngine())
        with self.assertRaises(T.TranslateError):
            T.translate_document(open(SRC, "rb").read(), "it", "ar", FakeEngine())          # destra-sinistra
        empty = fitz.open(); empty.new_page()
        with self.assertRaises(T.TranslateError):
            T.translate_document(empty.tobytes(), "it", "en", FakeEngine())                  # nessun testo (scansione)

    def test_engines_without_configuration(self):
        with self.assertRaises(T.TranslateError):
            T.DeepLEngine("").translate(["a"], "it", "en")
        with self.assertRaises(T.TranslateError):
            T.LibreTranslateEngine("").translate(["a"], "it", "en")
        self.assertFalse(T.LocalEngine().ready("it", "xx"))
        self.assertIsInstance(T.make_engine("boh"), T.LocalEngine)

    def test_install_model_rejects_bad_archives(self):
        import zipfile, unittest.mock as m
        bad = os.path.join(TMP, "bad.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("../evil.txt", "x")
        with m.patch("pdfdesk.scan._download", lambda url, dest, progress=None, sha256="": __import__("shutil").copy(bad, dest)):
            with self.assertRaises(T.TranslateError):
                T.install_model(T.ModelInfo("it", "xx", "1", "http://x"))
        good = os.path.join(TMP, "good.zip")
        with zipfile.ZipFile(good, "w") as z:
            z.writestr("it_xx/sentencepiece.model", "x"); z.writestr("it_xx/model/model.bin", "x"); z.writestr("it_xx/stanza/a", "x")
        with m.patch("pdfdesk.scan._download", lambda url, dest, progress=None, sha256="": __import__("shutil").copy(good, dest)):
            T.install_model(T.ModelInfo("it", "xx", "1", "http://x"))
        self.assertIn(("it", "xx"), T.installed_pairs())
        self.assertFalse(os.path.exists(os.path.join(T.models_dir(), "it_xx", "stanza")))
        T.remove_model("it", "xx"); self.assertNotIn(("it", "xx"), T.installed_pairs())


MODELS = os.environ.get("PDFDESK_TEST_MODELS", "")          # cartella con it_en/ (modello Argos estratto), facoltativa


@unittest.skipUnless(MODELS and os.path.isdir(os.path.join(MODELS, "it_en")), "modelli di traduzione non disponibili")
class LocalEngineTests(unittest.TestCase):
    def test_real_translation(self):
        import shutil
        shutil.copytree(os.path.join(MODELS, "it_en"), os.path.join(T.models_dir(), "it_en"), dirs_exist_ok=True)
        out = T.LocalEngine().translate(["Il contratto ha durata di quattro anni. Si rinnova automaticamente."], "it", "en")
        self.assertIn("four years", out[0].lower())
        data, rep = T.translate_document(open(SRC, "rb").read(), None, "en", T.LocalEngine())
        self.assertIn("Technical", fitz.open("pdf", data)[0].get_text())


class DialogTests(unittest.TestCase):
    def setUp(self):
        from pdfdesk.dialogs import settings
        settings().clear()

    def test_open_document_translated_opens_next_to_original(self):
        import shutil, unittest.mock as m
        from pdfdesk.mainwindow import MainWindow
        from pdfdesk import translate_ui
        a = os.path.join(TMP, "a.pdf"); b = os.path.join(TMP, "b.pdf"); shutil.copy(SRC, a); shutil.copy(SRC, b)
        w = MainWindow(); w.show(); wait(50)
        try:
            w.open_path(a); w.open_path(b); w.tabbar.setCurrentIndex(0); wait(100)
            self.assertEqual(os.path.basename(w.pdf.path), "a.pdf")
            orig = w.pdf

            def fake_exec(dlg):
                self.assertEqual(len(dlg.items), 1); self.assertTrue(dlg.items[0]["current"])
                self.assertEqual(dlg.table.item(0, 1).text(), T.lang_name("it"))   # lingua rilevata
                dlg.dst.setCurrentIndex(dlg.dst.findData("en")); dlg.run(); return 1
            with m.patch.object(translate_ui, "engine_from_settings", lambda: FakeEngine()), \
                    m.patch.object(translate_ui.TranslateDialog, "exec", fake_exec), \
                    m.patch("pdfdesk.translate_ui.QMessageBox.information", lambda *a, **k: None):
                w.translate_dialog()
            wait(200)
            names = [os.path.basename(d.path) for d in w.docs]
            self.assertEqual(names, ["a.pdf", "a_translated_en.pdf", "b.pdf"])  # subito dopo l'originale
            self.assertTrue(os.path.isfile(os.path.join(TMP, "a_translated_en.pdf")))
            self.assertIs(w.docs[0], orig); self.assertEqual(w.tabbar.currentIndex(), 1)
            self.assertIn("RELAZIONE", w.pdf.doc[0].get_text())
            # seconda traduzione dello stesso file: la scheda vecchia viene sostituita, non duplicata
            w.tabbar.setCurrentIndex(0); wait(50)
            with m.patch.object(translate_ui, "engine_from_settings", lambda: FakeEngine()), \
                    m.patch.object(translate_ui.TranslateDialog, "exec", fake_exec), \
                    m.patch("pdfdesk.translate_ui.QMessageBox.information", lambda *a, **k: None):
                w.translate_dialog()
            wait(200)
            self.assertEqual([os.path.basename(d.path) for d in w.docs], ["a.pdf", "a_translated_en.pdf", "b.pdf"])
        finally:
            for d in w.docs:
                d.modified = False
            w.close(); wait(30)

    def test_batch_files_and_unsaved_document(self):
        import shutil, unittest.mock as m
        from pdfdesk import translate_ui
        from pdfdesk.mainwindow import MainWindow
        files = []
        for i in range(3):
            p = os.path.join(TMP, f"lotto{i}.pdf"); shutil.copy(SRC, p); files.append(p)
        outdir = os.path.join(TMP, "out"); os.makedirs(outdir, exist_ok=True)
        w = MainWindow(); w.show(); wait(50)
        try:
            w.new_doc(); w.pdf.doc[0].insert_text((50, 80), "Documento nuovo mai salvato con del testo italiano da tradurre.")
            new = w.pdf

            def fake_exec(dlg):
                for f in files:
                    dlg.add_file(f)
                dlg.add_file(files[0])                                     # duplicato ignorato
                self.assertEqual(len(dlg.items), 4)
                dlg.src.setCurrentIndex(dlg.src.findData("it")); dlg.dst.setCurrentIndex(dlg.dst.findData("de"))
                dlg.pattern.setText("{name}.{lang}"); dlg.folder.setText(outdir)
                dlg.run(); return 1
            with m.patch.object(translate_ui, "engine_from_settings", lambda: FakeEngine()), \
                    m.patch.object(translate_ui.TranslateDialog, "exec", fake_exec), \
                    m.patch("pdfdesk.translate_ui.QMessageBox.information", lambda *a, **k: None):
                w.translate_dialog()
            wait(200)
            self.assertEqual(sorted(os.listdir(outdir)), ["lotto0.de.pdf", "lotto1.de.pdf", "lotto2.de.pdf"])
            self.assertEqual(len(w.docs), 2); self.assertIs(w.docs[0], new)
            self.assertIsNone(w.docs[1].path); self.assertTrue(w.docs[1].modified)   # traduzione di un file mai salvato
            from pdfdesk.dialogs import settings
            self.assertEqual(settings().value("translate/target"), "de")
        finally:
            for d in w.docs:
                d.modified = False
            w.close(); wait(30)

    def test_home_card_and_preferences(self):
        import unittest.mock as m
        from pdfdesk.mainwindow import MainWindow
        from pdfdesk import dialogs
        w = MainWindow(); w.show(); wait(50)
        try:
            self.assertIn("translate", w.home.cards)
            with m.patch.object(w, "translate_dialog") as td:
                w.home.cards["translate"].click()
            td.assert_called_once()
        finally:
            w.close(); wait(30)
        d = dialogs.PreferencesDialog(None)
        d.tr_engine.setCurrentIndex(d.tr_engine.findData("deepl")); d.tr_deepl.setText("abc:fx"); d.store()
        from pdfdesk import translate_ui
        e = translate_ui.engine_from_settings()
        self.assertIsInstance(e, T.DeepLEngine); self.assertEqual(e.key, "abc:fx")
        d.close()


class CliTests(unittest.TestCase):
    def test_cli_translate(self):
        import unittest.mock as m, shutil, io, contextlib
        from pdfdesk import cli
        p = os.path.join(TMP, "cli.pdf"); shutil.copy(SRC, p)
        with m.patch.object(T, "make_engine", lambda *a, **k: FakeEngine()), contextlib.redirect_stdout(io.StringIO()) as out:
            rc = cli.main(["--translate", p, "--to", "en"])
        self.assertEqual(rc, 0); self.assertTrue(os.path.isfile(os.path.join(TMP, "cli_translated_en.pdf")))
        self.assertIn("cli_translated_en.pdf", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["--translate", p]), 3)                         # manca --to


if __name__ == "__main__":
    unittest.main()
