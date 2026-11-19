"""Ottimizzazione: modalità dei font e creazione di un nuovo file (l'originale non si tocca)."""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf as fitz  # noqa: E402

from pdfdesk import compress, pdfstd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _sample() -> bytes:
    d = fitz.open()
    p = d.new_page()
    p.insert_text((50, 80), "Testo Helvetica àè", fontname="helv", fontsize=12)
    p.insert_text((50, 110), "Testo Times", fontname="tiro", fontsize=12)
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(50, 60, 200, 90), "uri": "https://example.org"})
    d.set_metadata({"title": "Prova font"})
    return d.tobytes()


class FontModeTests(unittest.TestCase):
    def test_inventario(self):
        inv = compress.font_inventory(fitz.open("pdf", _sample()))
        self.assertEqual(inv["embedded"], 0)
        self.assertEqual(inv["missing"], ["Helvetica", "Times-Roman"])
        self.assertIn("non incorporati", compress.format_analysis(compress.analyze(_sample())))

    def test_subset_flag_compatibile(self):
        self.assertEqual(compress.font_mode(compress.SaveOptions(subset_fonts=True)), "subset")
        self.assertEqual(compress.font_mode(compress.SaveOptions()), "keep")

    @unittest.skipUnless(pdfstd.gs_available(), "Ghostscript non disponibile")
    def test_incorpora_poi_togli(self):
        src = _sample()
        rep = {}
        emb = compress.optimize_bytes(src, compress.SaveOptions("original", font_mode="embed", report=rep))
        d = fitz.open("pdf", emb)
        self.assertEqual(compress.font_inventory(d)["missing"], [])
        self.assertEqual(rep["fonts_embedded"], 2)
        self.assertIn("Testo Helvetica àè", d[0].get_text())
        self.assertEqual(len(d[0].get_links()), 1)
        self.assertEqual(d.metadata.get("title"), "Prova font")
        rep2 = {}
        un = compress.optimize_bytes(emb, compress.SaveOptions("original", font_mode="unembed", report=rep2))
        u = fitz.open("pdf", un)
        self.assertEqual(rep2["fonts_removed"], 2)
        self.assertEqual(compress.font_inventory(u)["embedded"], 0)
        self.assertLess(len(un), len(emb))
        self.assertIn("Testo Helvetica àè", u[0].get_text())

    def test_font_composti_restano(self):
        ttf = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if not os.path.exists(ttf):
            self.skipTest("DejaVuSans non disponibile")
        d = fitz.open(); p = d.new_page()
        p.insert_font(fontname="dj", fontfile=ttf)
        p.insert_text((50, 80), "Ελληνικά", fontname="dj", fontsize=12)
        rep = {}
        out = compress.optimize_bytes(d.tobytes(), compress.SaveOptions("original", font_mode="unembed", report=rep))
        self.assertEqual(rep, {"fonts_removed": 0, "fonts_kept": 1})
        self.assertEqual(compress.font_inventory(fitz.open("pdf", out))["embedded"], 1)


class NewFileTests(unittest.TestCase):
    def test_cli_rifiuta_stesso_file(self):
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "a.pdf")
            open(f, "wb").write(_sample())
            before = open(f, "rb").read()
            r = subprocess.run([sys.executable, "-m", "pdfdesk", "--compress", f, f], cwd=ROOT, capture_output=True)
            self.assertEqual(r.returncode, 2)
            self.assertEqual(open(f, "rb").read(), before)

    def test_dialogo_propone_nuovo_nome(self):
        from PySide6.QtWidgets import QApplication
        from pdfdesk.dialogs import SaveDialog
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            f = os.path.join(t, "doc.pdf")
            open(f, "wb").write(_sample())
            dlg = SaveDialog(None, f, False, source=f)
            self.assertFalse(dlg.optimizing())
            self.assertEqual(dlg.path.text(), f)
            dlg.preset.setCurrentIndex(dlg.preset.findData("medium"))
            self.assertTrue(dlg.optimizing())
            self.assertEqual(dlg.path.text(), os.path.join(t, "doc_ottimizzato.pdf"))
            dlg.preset.setCurrentIndex(dlg.preset.findData("original"))
            self.assertEqual(dlg.path.text(), f)
            dlg.fonts.setCurrentIndex(dlg.fonts.findData("subset"))
            self.assertTrue(dlg.optimizing())
            self.assertEqual(dlg.options().font_mode, "subset")
            dlg.path.setText(f)                         # l'utente rimette il nome originale: rifiutato
            from unittest import mock
            with mock.patch("pdfdesk.dialogs.QMessageBox.warning") as w:
                dlg._ok()
            w.assert_called_once()
            self.assertNotEqual(dlg.result(), SaveDialog.Accepted)
            self.assertEqual(dlg.path.text(), os.path.join(t, "doc_ottimizzato.pdf"))
            dlg.deleteLater()


if __name__ == "__main__":
    unittest.main()
