"""OCR su PDF esistenti (motore integrato in PyMuPDF), lingue, finestra e riga di comando."""
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-ocr-")
DATA = os.path.join(TMP, "data")

import pymupdf as fitz  # noqa: E402

from pdfdesk import ocr  # noqa: E402

# dati delle lingue per i test: quelli di un Tesseract di sistema (ita se c'è, altrimenti eng)
SYS_TD = next((d for d in [os.environ.get("OCR_TEST_TESSDATA", "")]
               + sorted(glob.glob("/usr/share/tesseract-ocr/*/tessdata"), reverse=True)
               + ["/usr/share/tessdata", "/opt/homebrew/share/tessdata", "/usr/local/share/tessdata"]
               if os.path.isfile(os.path.join(d, "eng.traineddata"))), None)
HAVE = bool(SYS_TD) and ocr.engine_ok()


def scanned_pdf(path, text="Fattura numero 2026/118 del 23 novembre", rotated=False, with_text_page=True):
    src = fitz.open(); p = src.new_page(); p.insert_text((72, 120), text, fontsize=16)
    img = p.get_pixmap(dpi=150).tobytes("png")
    d = fitz.open()
    q = d.new_page(); q.insert_image(q.rect, stream=img)
    if rotated:
        q2 = d.new_page(); q2.insert_image(q2.rect, stream=img); q2.set_rotation(90)
    if with_text_page:
        t = d.new_page(); t.insert_text((72, 100), "Testo già presente")
    d.save(path); d.close()
    return path


class _Env(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"PDFDESK_DATA": DATA})
        self.env.start()
        shutil.rmtree(DATA, ignore_errors=True)

    def tearDown(self):
        self.env.stop()


class CatalogTests(_Env):
    def test_catalogo(self):
        self.assertIn("ita", ocr.CATALOG); self.assertIn("eng", ocr.CATALOG)
        for c, (size, sha) in ocr.CATALOG.items():
            self.assertGreater(size, 100_000, c); self.assertEqual(len(sha), 64, c)
            self.assertIn(c, ocr.NAMES)
        self.assertEqual(ocr.lang_name("ita"), "Italiano")

    def test_nomi_di_uscita(self):
        src = os.path.join(TMP, "rel.pdf"); open(src, "wb").write(b"x")
        self.assertEqual(ocr.output_name(src), os.path.join(TMP, "rel_ocr.pdf"))
        open(os.path.join(TMP, "rel_ocr.pdf"), "wb").write(b"x")
        self.assertEqual(ocr.output_name(src), os.path.join(TMP, "rel_ocr-2.pdf"))
        self.assertEqual(ocr.output_name(src, overwrite=True), os.path.join(TMP, "rel_ocr.pdf"))
        self.assertEqual(ocr.output_name(src, ".testo", "/x"), "/x/rel.testo.pdf")

    def test_scaricamento_verificato(self):
        """Il download usa più indirizzi e controlla lo SHA-256: un file alterato non viene accettato."""
        good = b"dati-lingua" * 20000
        sha = hashlib.sha256(good).hexdigest()
        calls = []

        def fake_download(url, dest, progress=None, sha256=""):
            calls.append(url)
            if "raw.githubusercontent" in url:
                from pdfdesk.scan import ScanError
                raise ScanError("bloccato")
            data = good
            if hashlib.sha256(data).hexdigest() != sha256:
                from pdfdesk.scan import ScanError
                raise ScanError("sha")
            open(dest, "wb").write(data)
        with mock.patch.dict(ocr.CATALOG, {"zzz": (len(good), sha)}), mock.patch.dict(ocr.NAMES, {"zzz": "Prova"}), \
                mock.patch("pdfdesk.scan._download", fake_download):
            self.assertEqual(ocr.download(["zzz"]), ["zzz"])
            self.assertEqual(len(calls), 2)                       # primo indirizzo bloccato, secondo riuscito
            self.assertTrue(ocr.is_user_lang("zzz"))
            self.assertEqual(ocr.download(["zzz"]), [])           # già presente e integra: niente da fare
            self.assertTrue(ocr.remove("zzz"))
            self.assertFalse(ocr.is_user_lang("zzz"))
        with mock.patch.dict(ocr.CATALOG, {"zzz": (len(good), "0" * 64)}), mock.patch.dict(ocr.NAMES, {"zzz": "Prova"}), \
                mock.patch("pdfdesk.scan._download", fake_download):
            with self.assertRaises(ocr.OcrError):
                ocr.download(["zzz"])
            self.assertFalse(ocr.is_user_lang("zzz"))

    def test_lingua_mancante(self):
        with mock.patch.object(ocr, "installed", return_value={}):
            with self.assertRaises(ocr.OcrError) as cm:
                ocr.resolve("ita+eng")
            self.assertIn("Italiano", str(cm.exception))


@unittest.skipUnless(HAVE, "motore OCR o dati di sistema non disponibili")
class RecognitionTests(_Env):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(DATA, "tessdata"))
        shutil.copy(os.path.join(SYS_TD, "eng.traineddata"), os.path.join(DATA, "tessdata"))

    def test_lingue_dalla_cartella_del_programma(self):
        self.assertEqual(ocr.installed()["eng"], ocr.user_dir())
        self.assertTrue(ocr.is_user_lang("eng"))

    def test_documento(self):
        src = scanned_pdf(os.path.join(TMP, "s.pdf"), rotated=True)
        before = [p.get_pixmap(dpi=40).samples for p in fitz.open(src)]
        out = os.path.join(TMP, "s_ocr.pdf")
        rep = ocr.ocr_file(src, out, "eng")
        self.assertEqual((rep.pages, rep.recognized, rep.skipped_text, rep.errors), (3, 2, 1, []))
        d = fitz.open(out)
        for i, p in enumerate(d):
            self.assertEqual(p.get_pixmap(dpi=40).samples, before[i], f"pagina {i + 1} cambiata d'aspetto")
        self.assertEqual(len(d[0].search_for("2026/118")), 1)
        r0, r1 = d[0].search_for("2026/118")[0], d[1].search_for("2026/118")[0]
        self.assertLess(abs(r0.x0 - r1.x0) + abs(r0.y0 - r1.y0), 2)      # pagina ruotata: stessa posizione
        self.assertEqual(d[1].rotation, 90)
        self.assertEqual(d[2].get_text().strip(), "Testo già presente")   # pagina con testo: intatta

    def test_tutte_le_pagine_e_originale_intatto(self):
        src = scanned_pdf(os.path.join(TMP, "t.pdf"))
        orig = open(src, "rb").read()
        rep = ocr.ocr_file(src, os.path.join(TMP, "t2.pdf"), "eng", only_missing=False)
        self.assertEqual(rep.skipped_text, 0)
        self.assertEqual(open(src, "rb").read(), orig)
        with self.assertRaises(ocr.OcrError):
            ocr.ocr_file(src, src, "eng")

    def test_annulla(self):
        src = scanned_pdf(os.path.join(TMP, "u.pdf"))
        with self.assertRaises(ocr.OcrError):
            ocr.ocr_file(src, os.path.join(TMP, "u2.pdf"), "eng", progress=lambda i, n: False)
        self.assertFalse(os.path.exists(os.path.join(TMP, "u2.pdf")))

    def test_scansione_con_motore_integrato(self):
        from pdfdesk import scan
        src = fitz.open(); p = src.new_page(); p.insert_text((72, 120), "Verbale della riunione", fontsize=18)
        img = os.path.join(TMP, "pag.png"); p.get_pixmap(dpi=200).save(img)
        out = os.path.join(TMP, "scan.pdf")
        with mock.patch.object(scan, "tesseract_path", return_value=None):          # nessun Tesseract esterno
            self.assertIn("eng", scan.ocr_languages())
            scan.images_to_pdf([img], out, dpi=200, ocr_lang="eng")
        self.assertIn("Verbale", fitz.open(out)[0].get_text())

    def test_riga_di_comando(self):
        src = scanned_pdf(os.path.join(TMP, "c 1.pdf"))
        outdir = os.path.join(TMP, "uscita")
        env = {**os.environ, "PDFDESK_DATA": DATA}
        r = subprocess.run([sys.executable, "-m", "pdfdesk", "--ocr", src, "--ocr-lang", "eng", "--outdir", outdir,
                            "--ocr-suffix", ".ricercabile"], cwd=ROOT, capture_output=True, env=env, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))
        out = os.path.join(outdir, "c 1.ricercabile.pdf")
        self.assertIn("2026/118", fitz.open(out)[0].get_text())
        r = subprocess.run([sys.executable, "-m", "pdfdesk", "--ocr", os.path.join(TMP, "manca.pdf")], cwd=ROOT,
                           capture_output=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 2)


@unittest.skipUnless(HAVE, "motore OCR o dati di sistema non disponibili")
class DialogTests(_Env):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(DATA, "tessdata"))
        shutil.copy(os.path.join(SYS_TD, "eng.traineddata"), os.path.join(DATA, "tessdata"))
        from PySide6.QtCore import QSettings
        ini = os.path.join(TMP, "impostazioni.ini")                  # impostazioni proprie: non si toccano quelle vere
        self.sp = mock.patch("pdfdesk.ocr_ui.settings", lambda: QSettings(ini, QSettings.IniFormat))
        self.sp.start()

    def tearDown(self):
        self.sp.stop()
        super().tearDown()

    def test_documento_aperto_e_batch(self):
        from pdfdesk.core import PdfDocument
        from pdfdesk.ocr_ui import OcrDialog
        a = scanned_pdf(os.path.join(TMP, "aperto.pdf"))
        b = scanned_pdf(os.path.join(TMP, "altro.pdf"))
        pdf = PdfDocument.open(a)
        opened = []
        dlg = OcrDialog(None, (a, pdf, "aperto.pdf"), [b], lambda out, data: opened.append(out))
        self.assertEqual(dlg.table.rowCount(), 2)
        self.assertIn("1 senza testo", dlg.table.item(0, 1).text())
        for i in range(dlg.langs.list.count()):                       # solo inglese
            it = dlg.langs.list.item(i)
            from PySide6.QtCore import Qt
            it.setCheckState(Qt.Checked if it.data(Qt.UserRole) == "eng" else Qt.Unchecked)
        dlg.folder.setText("")
        dlg.suffix.setText("_ocr")
        dlg.run()
        self.assertEqual(opened, [os.path.join(TMP, "aperto_ocr.pdf")])
        self.assertTrue(os.path.isfile(os.path.join(TMP, "altro_ocr.pdf")))
        self.assertFalse(pdf.modified)                                # il documento aperto non cambia
        self.assertIn("2026/118", fitz.open(os.path.join(TMP, "altro_ocr.pdf"))[0].get_text())
        self.assertIn("Fatto", dlg.table.item(1, 2).text())
        dlg.deleteLater()

    def test_finestra_lingue(self):
        from pdfdesk.ocr_ui import LanguagesDialog
        from PySide6.QtCore import Qt
        dlg = LanguagesDialog(None)
        codes = {dlg.list.item(i).data(Qt.UserRole): dlg.list.item(i) for i in range(dlg.list.count())}
        self.assertEqual(codes["eng"].checkState(), Qt.Checked)
        self.assertEqual(codes["ita"].checkState(), Qt.Unchecked) if not os.path.isfile(os.path.join(SYS_TD, "ita.traineddata")) else None
        codes["eng"].setCheckState(Qt.Unchecked)                    # scaricata dal programma: si può togliere
        self.assertIn("da togliere", dlg.status.text())
        dlg.apply()
        self.assertFalse(ocr.is_user_lang("eng"))
        dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
