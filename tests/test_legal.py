# test_legal.py: esclusione di responsabilità nella finestra Informazioni, in --version e nel README.
import contextlib, io, os, unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LegalTests(unittest.TestCase):
    def test_version_prints_disclaimer(self):
        from pdfdesk import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["--version"]), 0)
        self.assertIn("SENZA ALCUNA GARANZIA", out.getvalue())

    def test_about_dialog_shows_disclaimer(self):
        from PySide6.QtWidgets import QApplication, QTextBrowser
        app = QApplication.instance() or QApplication([])
        from pdfdesk import dialogs
        d = dialogs.AboutDialog(None)
        txt = " ".join(b.toPlainText() for b in d.findChildren(QTextBrowser))
        self.assertIn("SENZA GARANZIE", txt)
        self.assertIn("redazioni", txt)
        d.deleteLater(); app.processEvents()

    def test_readme_has_disclaimer(self):
        s = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
        self.assertIn("## Esclusione di responsabilità", s)
        self.assertIn("(#esclusione-di-responsabilità)", s)


if __name__ == "__main__":
    unittest.main()
