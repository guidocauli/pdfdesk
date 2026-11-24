"""Barra di stato (statistiche, cursore dello zoom), schermo intero col doppio clic, pulsante di chiusura delle schede."""
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-sb-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")

import pymupdf as fitz  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QTabBar, QToolButton  # noqa: E402

from pdfdesk import shutdown as _shutdown; _shutdown.install_atexit(); _shutdown.watchdog()  # noqa: E402,E702
from pdfdesk import docstats  # noqa: E402
from pdfdesk.mainwindow import MainWindow  # noqa: E402

QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, TMP)
app = QApplication.instance() or QApplication([])
from make_samples import block_modal_dialogs; block_modal_dialogs()  # noqa: E402,E702


def mkpdf(name, pages):
    p = os.path.join(TMP, name); d = fitz.open()
    for t in pages:
        pg = d.new_page()
        if t:
            pg.insert_text((72, 100), t, fontsize=12)
    d.save(p); d.close(); return p


def dblclick(w, pos):
    p = QPointF(pos)
    app.sendEvent(w, QMouseEvent(QEvent.MouseButtonDblClick, p, w.mapToGlobal(p), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    app.processEvents()


class DocStatsTests(unittest.TestCase):
    def test_conteggi(self):
        d = fitz.open(mkpdf("s.pdf", ["uno due tre", "quattro cinque", ""]))
        st = docstats.text_stats(d)
        self.assertEqual((st.pages, st.words, st.text_pages), (3, 5, 2))
        self.assertEqual(st.chars, len("uno due tre") + len("quattro cinque"))
        self.assertEqual(st.chars_nospace, len("unoduetre") + len("quattrocinque"))
        self.assertEqual(docstats.page_format(d[0]), "A4 verticale")
        parts = list(docstats.iter_text_stats(d, chunk=1))
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[-1].done)

    def test_formato(self):
        d = fitz.open(); p = d.new_page(width=792, height=612)
        self.assertEqual(docstats.page_format(p), "Letter orizzontale")
        p2 = d.new_page(width=300, height=300)
        self.assertEqual(docstats.page_format(p2), "106 × 106 mm")


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show()
        self.w.open_path(mkpdf("a.pdf", ["alfa beta", "gamma"]))
        self.w.open_path(mkpdf("b.pdf", ["delta"]))
        for _ in range(50):
            app.processEvents()

    def tearDown(self):
        for d in self.w.docs:
            d.modified = False
        self.w.close(); self.w.deleteLater(); app.processEvents()

    def test_statistiche(self):
        t = self.w.lbl_stats.text()
        self.assertIn("1 parola", t)
        # l'etichetta deve davvero occupare spazio (con il criterio «Ignored» la barra di stato le dava 0 px)
        self.assertGreater(self.w.lbl_stats.width(), self.w.lbl_stats.fontMetrics().horizontalAdvance("1 parola"))
        self.w.resize(420, 700)
        for _ in range(20):
            app.processEvents()
        self.assertGreater(self.w.lbl_stats.width(), 30)                       # stretta: accorciata, non sparita
        self.w.resize(1200, 800)
        for _ in range(20):
            app.processEvents()
        self.assertIn("5 caratteri", t)
        self.assertIn("A4 verticale", t)
        self.assertIn(" B", t)
        self.w.tabbar.setCurrentIndex(0); app.processEvents()
        for _ in range(20):
            app.processEvents()
        self.assertIn("3 parole", self.w.lbl_stats.text())

    def test_cursore_zoom(self):
        w = self.w
        w.zoom_slider.setValue(w._zoom_to_slider(1.0)); app.processEvents()
        self.assertAlmostEqual(w.view.zoom, 1.0)
        self.assertEqual(w.lbl_zoom.text(), "100%")
        w.view.set_zoom(3.0); app.processEvents()
        self.assertEqual(w.zoom_slider.value(), w._zoom_to_slider(3.0))
        dblclick(w.zoom_slider, w.zoom_slider.rect().center())
        self.assertAlmostEqual(w.view.zoom, 1.0)

    def test_schermo_intero(self):
        w, tb = self.w, self.w.tabbar
        dblclick(tb, tb.tabRect(0).center())                    # su una scheda: niente
        self.assertFalse(w.isFullScreen())
        dblclick(tb, QPointF(tb.width() - 10, tb.height() / 2))  # zona libera
        self.assertTrue(w.isFullScreen())
        self.assertTrue(w.a_fullscreen.isChecked())
        w.escape_pressed(); app.processEvents()
        self.assertFalse(w.isFullScreen())
        w.view.backgroundDoubleClicked.emit(); app.processEvents()
        self.assertTrue(w.isFullScreen())
        w.a_fullscreen.trigger(); app.processEvents()
        self.assertFalse(w.isFullScreen())

    def test_chiusura_scheda(self):
        tb = self.w.tabbar
        box = tb.tabButton(1, QTabBar.RightSide)
        self.assertIsNotNone(box)
        btn = box.findChild(QToolButton)
        right = btn.mapTo(tb, btn.rect().topRight()).x()
        self.assertLess(right, tb.tabRect(1).right() - 4)                     # staccato dal bordo della linguetta
        btn.click(); app.processEvents()
        self.assertEqual(len(self.w.docs), 1)
        self.assertEqual(os.path.basename(self.w.docs[0].path), "a.pdf")


if __name__ == "__main__":
    unittest.main()
