# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Test dell'interfaccia in modalità offscreen: mouse simulato, selezione, spostamento, annulla, firma.
import os, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-gui-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")
import pymupdf as fitz
from PySide6.QtCore import QPointF, Qt, QPoint, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidgetAction
from PySide6.QtWidgets import QApplication
from make_samples import make_text_pdf
from pdfdesk import shutdown as _shutdown; _shutdown.install_atexit(); _shutdown.watchdog()      # chiusura ordinata delle finestre lasciate aperte dai test
from pdfdesk.mainwindow import MainWindow
from pdfdesk import dialogs, signing, sigstore
from pdfdesk.dialogs import settings
from pdfdesk.core import T_INK, T_SQUARE, T_STAMP, T_FREETEXT

QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, TMP)
app = QApplication.instance() or QApplication([])
from make_samples import block_modal_dialogs; block_modal_dialogs()
SRC = os.path.join(TMP, "t.pdf"); make_text_pdf(SRC)
SHOT = os.environ.get("SHOTS", TMP)

def wait(ms=80): QTest.qWait(ms)

class GuiTests(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show()
        self.assertTrue(self.w.open_path(SRC)); wait(300)
        self.v = self.w.view

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30)

    def vp(self, pno, x, y):
        r = self.v.page_rects[pno]
        return self.v.mapFromScene(QPointF(r.x() + x, r.y() + y))

    def drag(self, pno, a, b, steps=6):
        vp = self.v.viewport()
        pa, pb = self.vp(pno, *a), self.vp(pno, *b)
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, pa)
        for i in range(1, steps + 1):
            QTest.mouseMove(vp, QPoint(pa.x() + (pb.x() - pa.x()) * i // steps, pa.y() + (pb.y() - pa.y()) * i // steps)); wait(5)
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, pb); wait(60)

    def annots(self, pno=0): return self.w.pdf.list_annots(pno)

    def test_render_and_zoom(self):
        self.v.set_zoom(1.0); wait(200)
        _, pix, rs, _ = self.v.page_items[0]
        self.assertFalse(pix.pixmap().isNull()); self.assertGreater(rs, 1.0)
        self.v.fit_width(); wait(150); self.assertGreater(self.v.zoom, 0.3)
        self.w.grab().save(os.path.join(SHOT, "gui_base.png"))

    def test_text_flow_selection(self):
        pg = self.w.pdf.page(0)
        ws = pg.get_text("words")
        w0 = ws[0]; w1 = next(w for w in ws if (w[5], w[6]) != (w0[5], w0[6]) and w[1] > w0[3] + 2)
        a = ((w0[0] + w0[2]) / 2, (w0[1] + w0[3]) / 2); b = ((w1[0] + w1[2]) / 2, (w1[1] + w1[3]) / 2)
        self.w.set_tool("textsel"); self.drag(0, a, b)
        txt = QApplication.clipboard().text()
        self.assertIn(w0[4], txt); self.assertIn(w1[4], txt); self.assertIn("\n", txt)
        self.w.set_tool("hl"); self.drag(0, a, b)
        an = self.annots(); self.assertEqual(len(an), 1)
        self.assertGreaterEqual(len(self.w.pdf.page(0).annots().__next__().vertices) // 4, 2)

    def test_pen_and_undo(self):
        self.w.set_tool("pen"); self.drag(0, (100, 400), (300, 450))
        a = self.annots(); self.assertEqual([x.type for x in a], [T_INK])
        self.w.undo(); wait(100); self.assertEqual(self.annots(), [])
        self.w.redo(); wait(100); self.assertEqual(len(self.annots()), 1)

    def test_rect_select_move_resize_delete(self):
        self.w.set_tool("rect"); self.drag(0, (200, 400), (300, 460))
        a = self.annots(); self.assertEqual([x.type for x in a], [T_SQUARE]); r0 = a[0].rect
        self.w.set_tool("select")
        self.drag(0, (250, 430), (290, 470)); wait(100)               # selezione + spostamento
        r1 = self.annots()[0].rect
        self.assertAlmostEqual(r1.x0 - r0.x0, 40, delta=6); self.assertAlmostEqual(r1.y0 - r0.y0, 40, delta=6)
        self.assertEqual(self.v.sel_page, 0)
        # ridimensiona dalla maniglia in basso a destra
        h = self.v._sel.handle_points()["se"]
        o = self.v.page_rects[0].topLeft()
        self.drag(0, (h.x() - o.x(), h.y() - o.y()), (h.x() - o.x() + 50, h.y() - o.y() + 30)); wait(100)
        r2 = self.annots()[0].rect
        self.assertAlmostEqual(r2.width - r1.width, 50, delta=6); self.assertAlmostEqual(r2.height - r1.height, 30, delta=6)
        self.w.delete_selection(); wait(60); self.assertEqual(self.annots(), [])

    def test_text_box_and_edit(self):
        from pdfdesk.dialogs import TextDialog
        orig = TextDialog.exec
        TextDialog.exec = lambda self_: (self_.edit.setPlainText("Ciao dal test àè"), TextDialog.Accepted)[1]
        try:
            self.w.set_tool("text"); self.drag(0, (100, 500), (320, 560))
        finally: TextDialog.exec = orig
        a = self.annots(); self.assertEqual(a[0].type, T_FREETEXT); self.assertEqual(a[0].text, "Ciao dal test àè")
        self.w.set_tool("select")
        self.v.select(0, a[0].xref)
        self.w.on_props_changed({"fontsize": 20.0}); wait(60)
        self.assertEqual(self.annots()[0].fontsize, 20.0)
        self.w.on_props_changed({"stroke": (1.0, 0.0, 0.0)}); wait(60)
        self.assertEqual(self.annots()[0].text_color, (1.0, 0.0, 0.0))
        self.w.grab().save(os.path.join(SHOT, "gui_text.png"))

    def test_edit_existing_text(self):
        from pdfdesk.dialogs import TextDialog
        orig = TextDialog.exec
        TextDialog.exec = lambda self_: (self_.edit.setPlainText("TITOLO NUOVO"), TextDialog.Accepted)[1]
        try:
            self.w.set_tool("edittext"); p = self.vp(0, 90, 95)
            QTest.mouseClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, p); wait(100)
        finally: TextDialog.exec = orig
        t = self.w.pdf.page(0).get_text(); self.assertIn("TITOLO NUOVO", t); self.assertNotIn("Ciao mondo", t)

    def test_markup_and_textsel(self):
        self.w.set_tool("hl"); self.drag(0, (70, 85), (260, 108))
        self.assertTrue(any(a.type == fitz.PDF_ANNOT_HIGHLIGHT for a in self.annots()))
        self.w.set_tool("textsel"); self.drag(0, (70, 85), (260, 108))
        self.assertIn("Pagina 1", QApplication.clipboard().text())

    def test_signature_image_insert(self):
        from PySide6.QtGui import QImage, QPainter, QColor
        im = QImage(300, 120, QImage.Format_ARGB32); im.fill(Qt.transparent)
        p = QPainter(im); p.setPen(QColor(0, 0, 150)); p.drawLine(10, 100, 290, 20); p.end()
        path = sigstore.add_signature(im); self.w.current_signature = path
        self.w.set_tool("sign"); self.drag(0, (300, 600), (480, 680))
        a = self.annots(); self.assertEqual(a[0].type, T_STAMP)
        self.assertLessEqual(a[0].rect.width, 181)

    def test_redaction_flow(self):
        self.w.set_tool("redact"); r = self.w.pdf.page(0).search_for("IBAN")[0]
        self.drag(0, (r.x0 - 3, r.y0 - 3), (r.x0 + 280, r.y1 + 3))
        self.assertEqual(self.w.pdf.pending_redactions(), 1)
        self.w._confirm_redactions = lambda n: (True, False)
        self.w.apply_redactions()
        self.assertNotIn("IBAN", self.w.pdf.page(0).get_text())

    def test_overwrite_warning_for_permanent_changes(self):
        import pdfdesk.mainwindow as mw, shutil
        w = self.w
        cp = os.path.join(TMP, "copia_redazione.pdf"); shutil.copyfile(SRC, cp)      # non toccare il file condiviso dai test
        w.open_path(cp); wait(100)
        self.assertEqual(w.pdf.path, os.path.abspath(cp))
        self.assertFalse(w.pdf.has_permanent_changes)
        calls = []
        w.confirm_permanent_overwrite = lambda: (calls.append(1), answer[0])[1]
        answer = ["cancel"]
        w.save()                                                                  # nessuna modifica permanente: nessun avviso
        self.assertEqual(calls, [])
        w.set_tool("redact"); r = w.pdf.page(0).search_for("IBAN")[0]
        self.drag(0, (r.x0 - 3, r.y0 - 3), (r.x0 + 280, r.y1 + 3))
        w._confirm_redactions = lambda n: (True, False)
        w.apply_redactions()
        self.assertTrue(w.pdf.has_permanent_changes)
        before = open(w.pdf.path, "rb").read()
        self.assertFalse(w.save()); self.assertEqual(len(calls), 1)               # annulla: file intatto
        self.assertEqual(open(w.pdf.path, "rb").read(), before)
        answer[0] = "overwrite"
        self.assertTrue(w.save()); self.assertEqual(len(calls), 2)
        self.assertNotIn(b"IBAN IT00X", fitz.open(w.pdf.path)[0].get_text().encode())
        self.assertFalse(w.pdf.has_permanent_changes)
        w.pdf.add_shape(0, "rect", fitz.Rect(10, 10, 50, 50)); w.save(); self.assertEqual(len(calls), 2)   # niente più avvisi
    def test_pages_and_thumbs(self):
        wait(400)
        self.assertEqual(self.w.thumbs.count(), 3)
        self.assertFalse(self.w.thumbs.item(0).icon().isNull())
        self.w.page_action("dup", [0]); self.assertEqual(self.w.pdf.page_count, 4); self.assertEqual(self.w.thumbs.count(), 4)
        self.w.page_action("rot_r", [1]); self.assertEqual(self.w.pdf.page(1).rotation, 90)
        self.w.undo(); self.w.undo(); wait(100); self.assertEqual(self.w.pdf.page_count, 3)

    def test_find(self):
        self.w.find_edit.setText("Ciao"); self.w.find_run(); wait(50)
        self.assertEqual(len(self.w.found), 3); self.w.find_step(1); self.assertEqual(self.w.found_idx, 1)

    def test_sign_digital_flow_and_signed_editing(self):
        p12 = os.path.join(TMP, "k.p12"); signing.create_self_signed_p12(p12, "pw", "Tester GUI")
        out = os.path.join(TMP, "firmato-gui.pdf")
        # firma visibile con immagine, comprimendo prima
        from PIL import Image  # pyhanko usa Pillow per le immagini
        from PySide6.QtGui import QImage, QPainter, QColor
        im = QImage(300, 120, QImage.Format_ARGB32); im.fill(Qt.transparent)
        p = QPainter(im); p.setPen(QColor(0, 0, 150)); p.drawLine(10, 100, 290, 20); p.end()
        sig = sigstore.add_signature(im)
        params = signing.SignParams(p12, "pw", "Test", "Bari", "Firma1", image_path=sig)
        self.w.pending_sign = (params, out, "medium", 0)
        self.w.finish_visible_signature(0, fitz.Rect(300, 600, 500, 700)); wait(300)
        self.assertTrue(os.path.exists(out)); self.assertTrue(self.w.pdf.is_signed)
        self.assertTrue(self.w.a_verify.isEnabled())            # documento firmato: la verifica è disponibile
        self.assertTrue(self.w.banner.isVisible() or not self.w.banner.isHidden())
        st = signing.verify_pdf_bytes(open(out, "rb").read()); self.assertTrue(st[0].valid)
        self.w.grab().save(os.path.join(SHOT, "gui_signed.png"))
        # modifica del documento firmato: la firma resta valida
        self.w.set_tool("rect"); self.drag(0, (100, 400), (200, 450))
        self.assertTrue(self.w.save())
        st2 = signing.verify_pdf_bytes(open(out, "rb").read())
        self.assertTrue(st2[0].intact and st2[0].valid, st2[0].summary)
        self.assertEqual(len(fitz.open(out)[0].get_text()) > 0, True)
        self.assertTrue(self.w.a_undo.isEnabled())            # anche i documenti firmati si possono annullare


class UiLayoutTests(unittest.TestCase):
    def setUp(self):
        QSettings().clear()
        self.w = MainWindow(); self.w.resize(1300, 800); self.w.show()
        self.assertTrue(self.w.open_path(SRC)); wait(300)

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30); QSettings().clear()

    def test_bars_icons_tooltips(self):
        self.assertEqual([b.windowTitle() for b in self.w.bars], ["Principale", "Pagine", "Strumenti", "Proprietà"])
        titles = [a.text().replace("&", "") for a in self.w.menuBar().actions()]
        self.assertIn("Inserisci", titles)
        self.assertLess(titles.index("Inserisci"), titles.index("Pagine"))
        ins = [a.text() for a in self.w.menu_insert.actions() if not a.isSeparator()]
        for needed in ("Casella di testo", "Immagine", "Rettangolo/cornice", "Ellisse", "Linea", "Freccia", "Penna", "Evidenziatore", "Redazione"):
            self.assertIn(needed, ins)
        for b in self.w.bars:
            self.assertTrue(b.toolTip())
            for a in b.actions():
                if a.isSeparator() or isinstance(a, QWidgetAction):
                    continue
                self.assertFalse(a.icon().isNull(), a.text())
                self.assertTrue(a.toolTip(), a.text())
        for w in (self.w.props.stroke, self.w.props.width, self.w.props.size, self.w.spin_page, self.w.zoom_btn):
            self.assertTrue(w.toolTip())

    def test_zoom_menu_and_pages_bar(self):
        self.assertTrue(self.w.zoom_btn.text().startswith("Ingrandimento"))
        acts = {a.text(): a for a in self.w.menu_zoom.actions()}
        acts["200%"].trigger(); self.assertAlmostEqual(self.w.view.zoom, 2.0, 2)
        acts["50%"].trigger(); self.assertAlmostEqual(self.w.view.zoom, 0.5, 2)
        if self.w.pdf.page_count > 1:
            self.w.spin_page.setValue(2); wait(100); self.assertEqual(self.w.view.current_page(), 1)
        self.assertFalse(self.w.menuBar().isNativeMenuBar())

    def test_rows_and_preferences(self):
        s = dialogs.settings()
        s.setValue("ui/rows", 2); s.setValue("ui/iconsize", 2); s.setValue("ui/btnstyle", 1); s.setValue("ui/locked", True)
        self.w.apply_prefs(relayout=True); wait(100)
        ys = {b.objectName(): b.y() for b in self.w.bars}
        self.assertGreater(ys["toolTools"], ys["toolMain"])
        self.assertEqual(ys["toolMain"], ys["toolPages"])
        self.assertEqual(self.w.bars[0].iconSize().width(), 32)
        self.assertFalse(self.w.bars[0].isMovable())
        s.setValue("ui/iconsize", 0); s.setValue("ui/btnstyle", 0)          ; self.w.resize(2600, 800); wait(50)   # solo icone e finestra larga: stanno su una riga
        s.setValue("ui/rows", 1); self.w.apply_prefs(relayout=True); wait(100)
        self.assertEqual({b.y() for b in self.w.bars}, {self.w.bars[0].y()})
        d = dialogs.PreferencesDialog(self.w); d.recent.setValue(3); d.zoom.setCurrentIndex(2); d.store()
        self.assertEqual(int(s.value("recent_max")), 3); self.assertEqual(int(s.value("view/initzoom")), 2)


class ContentEditGuiTests(unittest.TestCase):
    """Strumento «Modifica oggetti»: selezione e spostamento con il mouse di testo, immagini e grafica già nel PDF."""

    def setUp(self):
        QSettings().clear()
        import pymupdf
        d = pymupdf.open(); p = d.new_page()
        p.draw_rect(pymupdf.Rect(100, 100, 220, 160), color=(0, 0, 1), fill=(1, 1, 0), width=2)
        pm = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40), False); pm.set_rect(pm.irect, (200, 50, 50))
        p.insert_image(pymupdf.Rect(100, 300, 220, 380), pixmap=pm)
        p.insert_text((100, 500), "Testo del PDF", fontsize=14)
        self.path = os.path.join(tempfile.mkdtemp(), "c.pdf"); d.save(self.path)
        self.w = MainWindow(); self.w.resize(1300, 900); self.w.show()
        self.assertTrue(self.w.open_path(self.path)); wait(300)
        self.w.set_tool_by_key("editobj") if hasattr(self.w, "set_tool_by_key") else self.w.tool_actions["editobj"].trigger()

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30); QSettings().clear()

    def _vp(self, x, y):
        v = self.w.view
        o = v.page_rects[0].topLeft()
        return v.mapFromScene(QPointF(o.x() + x, o.y() + y))

    def _drag(self, a, b):
        from PySide6.QtTest import QTest
        vp = self.w.view.viewport()
        QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, self._vp(*a)); wait(30)
        QTest.mouseMove(vp, self._vp(*b)); wait(30)
        QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, self._vp(*b)); wait(200)

    def test_move_shape_image_and_delete(self):
        doc = self.w.pdf
        self._drag((160, 130), (260, 230))
        d = doc.page(0).get_drawings()
        self.assertEqual(len(d), 1)
        self.assertAlmostEqual(d[0]["rect"].x0, 200, delta=3); self.assertAlmostEqual(d[0]["rect"].y0, 200, delta=3)
        self._drag((160, 340), (160, 440))
        im = doc.page(0).get_image_info()[0]["bbox"]
        self.assertAlmostEqual(im[1], 400, delta=3)
        self.assertTrue(doc.can_undo)
        self.w.view.select_content(0, doc.content_at(0, (130, 495)))
        self.w.delete_selection(); wait(100)
        self.assertNotIn("Testo", doc.page(0).get_text())

    def test_move_text_and_double_click_signal(self):
        self._drag((130, 495), (130, 595)); doc = self.w.pdf
        words = doc.page(0).get_text("words")
        self.assertTrue(any(w[4] == "Testo" and 580 < w[1] < 600 for w in words), words)


class FormGuiTests(unittest.TestCase):
    def setUp(self):
        import test_features as tf
        self.form = tf.FORM
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show()
        self.assertTrue(self.w.open_path(self.form)); wait(300)
        self.v = self.w.view

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30)

    def click(self, x, y):
        r = self.v.page_rects[0]
        QTest.mouseClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, self.v.mapFromScene(QPointF(r.x() + x, r.y() + y))); wait(80)

    def test_form_opens_in_form_tool_and_toggles_checkbox(self):
        self.assertEqual(self.w.tool, "form")
        self.assertEqual(len(self.v._field_items), 6)                      # campi evidenziati
        self.click(79, 257)                                                # casella ok
        self.assertTrue({f.name: f.value for f in self.w.pdf.list_fields(0)}["ok"])
        self.click(79, 257)
        self.assertFalse({f.name: f.value for f in self.w.pdf.list_fields(0)}["ok"])

    def test_text_field_dialog(self):
        from PySide6.QtCore import QTimer
        def fill():
            d = QApplication.activeModalWidget()
            d.edit.setText("Mario Rossi"); d.accept()
        QTimer.singleShot(150, fill); self.click(150, 110)
        self.assertEqual({f.name: f.value for f in self.w.pdf.list_fields(0)}["nome"], "Mario Rossi")
        self.assertTrue(self.w.pdf.modified)

    def test_font_combo_lists_base_and_user_fonts(self):
        from pdfdesk import fonts
        c = dialogs.FontCombo(); codes = [c.itemData(i) for i in range(c.count())]
        self.assertTrue({"helv", "tiro", "cour"} <= set(codes)); self.assertIn(c.ADD, codes)
        c.set_code("@Inesistente"); self.assertIn("non disponibile", c.currentText())


class StandardGuiTests(unittest.TestCase):
    def setUp(self):
        import test_standards as ts
        from pdfdesk import pdfstd
        self.pdfstd = pdfstd
        self.a2 = os.path.join(TMP, "a2.pdf")
        open(self.a2, "wb").write(pdfstd.convert(ts.hard_doc(), "pdfa-2b"))
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show()
        self.assertTrue(self.w.open_path(self.a2)); wait(300)

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30)

    def test_save_dialog_standard_picker(self):
        d = dialogs.SaveDialog(self.w, "/tmp/x.pdf", False, standard="PDF/A-2b")
        self.assertEqual(d.std.key(), "pdfa-2b")
        self.assertFalse(d.meta.isEnabled())                              # i metadati XMP servono allo standard
        d.std.combo.setCurrentIndex(0); self.assertTrue(d.meta.isEnabled())
        d.std.combo.setCurrentIndex(d.std.combo.findData("pdfx-4")); self.assertTrue(d.std.icc_box.isVisibleTo(d))
        self.assertEqual(d.options().standard, "pdfx-4")

    def test_run_bg_returns_and_raises(self):
        self.assertEqual(self.w.run_bg(lambda: 42), 42)
        with self.assertRaises(ValueError): self.w.run_bg(lambda: (_ for _ in ()).throw(ValueError("x")))

    def test_conformant_doc_warns_and_restores_on_save(self):
        from PySide6.QtWidgets import QMessageBox
        self.assertEqual(self.w.pdf.standard, "PDF/A-2b")
        self.w.pdf.add_text(0, fitz.Rect(100, 600, 300, 650), "Nota aggiunta", 14, "helv"); self.w.changed([0])
        self.assertIn("PDF/A-2b", self.w.statusBar().currentMessage())
        self.assertFalse(self.pdfstd.check(self.w.pdf.doc.tobytes(), "pdfa-2b").ok)      # modificato: non più conforme
        orig = QMessageBox.question; QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        try: self.assertTrue(self.w.save())
        finally: QMessageBox.question = orig
        data = open(self.a2, "rb").read()
        self.assertTrue(self.pdfstd.check(data, "pdfa-2b").ok)                            # ripristinata la conformità
        self.assertEqual(len(fitz.open("pdf", data)[0].get_text("words")) > 3, True)      # e il testo è ancora testo
        self.assertFalse(self.w.pdf.modified)

    def test_standard_dialog_checks_current_document(self):
        d = dialogs.StandardDialog(self.w, lambda: self.w.pdf.doc.tobytes(), self.w.pdf.standard, False)
        self.assertEqual(d.pick.key(), "pdfa-2b"); d._check()
        self.assertIn("CONFORME", d.out.toPlainText())



class ThemeTests(unittest.TestCase):
    def test_dark_and_light(self):
        from pdfdesk import theme
        app = QApplication.instance()
        self.assertTrue(theme.apply(app, theme.DARK))
        self.assertLess(app.palette().window().color().lightness(), 100)
        self.assertFalse(theme.apply(app, theme.LIGHT))
        self.assertGreater(app.palette().window().color().lightness(), 150)
        theme.apply(app, theme.SYSTEM)


class InWindowMenuTests(unittest.TestCase):
    def setUp(self):
        QSettings().clear()
        dialogs.settings().setValue("ui/inmenus", 1)
        self.w = MainWindow(); self.w.resize(1300, 800); self.w.show()
        self.assertTrue(self.w.open_path(SRC)); wait(300)

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30); QSettings().clear()

    def test_panel_attached_under_title_and_click(self):
        mb = self.w.menuBar(); self.assertTrue(self.w.menus.enabled)
        act = next(a for a in mb.actions() if a.text().replace("&", "") == "Visualizza")
        r = mb.actionGeometry(act)
        QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, r.center()); wait(60)
        self.assertEqual(len(self.w.menus.panels), 1)
        pan = self.w.menus.panels[0]
        self.assertEqual(pan.parent(), self.w)                                   # non è una finestra separata
        self.assertEqual(pan.y(), mb.mapTo(self.w, r.bottomLeft()).y())          # attaccato sotto la voce
        self.assertEqual(pan.x(), mb.mapTo(self.w, r.bottomLeft()).x())
        # passando su un'altra voce si cambia tendina; un secondo clic sulla stessa la chiude
        act2 = next(a for a in mb.actions() if a.text().replace("&", "") == "Inserisci")
        QTest.mouseMove(mb, mb.actionGeometry(act2).center()); wait(60)
        self.assertIs(self.w.menus.key, act2)
        QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, mb.actionGeometry(act2).center()); wait(60)
        self.assertEqual(self.w.menus.panels, [])
        # voce di menu: clic su «Ellisse» seleziona lo strumento
        QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, mb.actionGeometry(act2).center()); wait(60)
        row = next(r_ for r_ in self.w.menus.panels[0].rows if r_.label.startswith("Ellisse"))
        QTest.mouseClick(row, Qt.LeftButton, Qt.NoModifier, row.rect().center()); wait(100)
        self.assertEqual(self.w.tool, "ellipse"); self.assertEqual(self.w.menus.panels, [])

    def test_press_only_and_drag_release(self):
        mb = self.w.menuBar()
        act = next(a for a in mb.actions() if a.text().replace("&", "") == "Inserisci")
        QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, mb.actionGeometry(act).center()); wait(60)
        row = next(r_ for r_ in self.w.menus.panels[0].rows if r_.label.startswith("Ellisse"))
        QTest.mousePress(row, Qt.LeftButton, Qt.NoModifier, row.rect().center()); wait(30)   # basta la pressione
        self.assertEqual(self.w.tool, "ellipse"); self.assertEqual(self.w.menus.panels, [])
        # premi sulla barra, trascina e rilascia sulla voce
        QTest.mousePress(mb, Qt.LeftButton, Qt.NoModifier, mb.actionGeometry(act).center()); wait(60)
        row = next(r_ for r_ in self.w.menus.panels[0].rows if r_.label.startswith("Rettangolo"))
        from PySide6.QtCore import QPoint
        g = row.mapToGlobal(row.rect().center())
        ev_pos = mb.mapFromGlobal(g)
        QTest.mouseRelease(mb, Qt.LeftButton, Qt.NoModifier, ev_pos); wait(100)
        self.assertEqual(self.w.tool, "rect"); self.assertEqual(self.w.menus.panels, [])

    def test_submenu_and_escape(self):
        mb = self.w.menuBar()
        act = next(a for a in mb.actions() if a.text().replace("&", "") == "Visualizza")
        QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, mb.actionGeometry(act).center()); wait(60)
        row = next(r_ for r_ in self.w.menus.panels[0].rows if r_.label.startswith("Ingrandimento"))
        QTest.mouseClick(row, Qt.LeftButton, Qt.NoModifier, row.rect().center()); wait(60)
        self.assertEqual(len(self.w.menus.panels), 2)
        QTest.keyClick(self.w, Qt.Key_Escape); wait(60)
        self.assertEqual(self.w.menus.panels, [])


class ModalPlacementTests(unittest.TestCase):
    def test_parentless_dialog_is_attached_and_centered_on_main(self):
        from PySide6.QtWidgets import QMessageBox
        QSettings().clear()
        w = MainWindow(); w.resize(900, 600); w.show(); wait(100)
        box = QMessageBox(); box.setText("prova"); box.show(); wait(100)
        try:
            self.assertIsNotNone(box.windowHandle().transientParent())
            self.assertIs(box.windowHandle().screen(), w.windowHandle().screen())
            self.assertLess(abs(box.frameGeometry().center().x() - w.frameGeometry().center().x()), 3)
        finally:
            box.close(); w.close(); wait(30)


class EditObjSelectsAnnotImageTests(unittest.TestCase):
    def test_editobj_click_selects_inserted_image(self):
        from pdfdesk import sigstore
        from PySide6.QtGui import QImage
        QSettings().clear()
        w = MainWindow(); w.resize(1200, 800); w.show(); self.assertTrue(w.open_path(SRC)); wait(200)
        img = QImage(120, 40, QImage.Format_ARGB32); img.fill(Qt.transparent)
        x = w.pdf.add_image(0, fitz.Rect(100, 300, 220, 340), sigstore.png_bytes(img)); w.changed([0]); wait(100)
        w.set_tool("editobj"); wait(30)
        v = w.view; r = v.page_rects[0]
        QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, v.mapFromScene(QPointF(r.x() + 160, r.y() + 320))); wait(80)
        self.assertEqual(v.sel_xref, x)
        self.assertIsNotNone(w.selected_image())
        w.pdf.modified = False; w.close(); wait(30)


class UndoRedrawTests(unittest.TestCase):
    def test_undo_reports_only_changed_pages(self):
        from pdfdesk.core import PdfDocument
        d = PdfDocument.open(SRC)
        while d.page_count < 3:
            d.duplicate_page(0)
        d.add_shape(1, "rect", fitz.Rect(50, 50, 150, 120), (1, 0, 0), None, 2)
        self.assertTrue(d.undo()); self.assertEqual(d.last_changed, [1])
        self.assertTrue(d.redo()); self.assertEqual(d.last_changed, [1])
        d.delete_pages([2]); self.assertTrue(d.undo()); self.assertIsNone(d.last_changed)     # cambia il numero di pagine
        d.rotate_pages([0], 90); self.assertTrue(d.undo()); self.assertIsNone(d.last_changed)  # cambia la rotazione


class TabsGatingExportTests(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show(); wait(100)
        self.b = os.path.join(TMP, "b.pdf"); make_text_pdf(self.b)

    def tearDown(self):
        for d in self.w.docs:
            d.modified = False
        self.w.close(); wait(30)
        dialogs.settings().remove("windowState2"); dialogs.settings().remove("geometry")

    def test_tools_disabled_without_pdf(self):
        w = self.w
        self.assertTrue(w.tool_actions and all(not a.isEnabled() for a in w.tool_actions.values()))
        for a in (w.a_sigimg, w.a_sigdig, w.a_insert, w.a_blank, w.a_standard, w.a_formtool, w.a_print, w.a_export, w.a_find, w.a_save):
            self.assertFalse(a.isEnabled(), a.text())
        self.assertFalse(w.props.isEnabled()); self.assertFalse(w.menu_insert.menuAction().isEnabled())
        self.assertTrue(w.a_open.isEnabled() and w.a_new.isEnabled() and w.a_prefs.isEnabled())
        self.assertTrue(w.open_path(SRC)); wait(150)
        self.assertTrue(all(a.isEnabled() for a in w.tool_actions.values()) and w.a_print.isEnabled() and w.props.isEnabled())
        self.assertTrue(w.menu_insert.menuAction().isEnabled())
        w.close_doc(); wait(50)
        self.assertFalse(w.a_print.isEnabled()); self.assertFalse(w.tool_actions["pen"].isEnabled())

    def test_vertical_dock(self):
        from PySide6.QtCore import Qt as Q
        w = self.w
        for tb in w.bars:
            self.assertTrue(tb.allowedAreas() & Q.LeftToolBarArea and tb.allowedAreas() & Q.RightToolBarArea)
        tools = next(t for t in w.bars if t.objectName() == "toolTools")
        w.removeToolBar(tools); w.addToolBar(Q.LeftToolBarArea, tools); tools.show(); wait(80)
        self.assertEqual(w.toolBarArea(tools), Q.LeftToolBarArea); self.assertEqual(tools.orientation(), Q.Vertical)
        props = next(t for t in w.bars if t.objectName() == "toolProps")
        w.removeToolBar(props); w.addToolBar(Q.RightToolBarArea, props); props.show(); wait(80)
        self.assertEqual(w.props._box.direction().name, "TopToBottom")
        w.removeToolBar(props); w.addToolBar(Q.TopToolBarArea, props); props.show(); wait(80)
        self.assertEqual(w.props._box.direction().name, "LeftToRight")
        w.apply_prefs(relayout=True)                                   # le barre ai lati restano dove sono
        self.assertEqual(w.toolBarArea(tools), Q.LeftToolBarArea)

    def test_tabs(self):
        w = self.w
        self.assertFalse(w.tabbar.isVisible())
        self.assertTrue(w.open_path(SRC)); wait(150)
        self.assertTrue(w.open_path(self.b)); wait(150)
        self.assertEqual(len(w.docs), 2); self.assertEqual(w.tabbar.count(), 2); self.assertTrue(w.tabbar.isVisible())
        self.assertIs(w.pdf, w.docs[1]); self.assertEqual(w.tabbar.currentIndex(), 1)
        self.assertTrue(w.open_path(SRC)); wait(50)                      # già aperto: passa alla scheda
        self.assertEqual(len(w.docs), 2); self.assertIs(w.pdf, w.docs[0])
        d0 = w.pdf
        d0.add_shape(0, "rect", fitz.Rect(50, 50, 150, 120), (1, 0, 0), None, 2)
        w.changed([0]); wait(50)
        self.assertTrue(w.tabbar.tabText(0).startswith("*")); self.assertFalse(w.tabbar.tabText(1).startswith("*"))
        w.view.set_zoom(1.7); w.tabbar.setCurrentIndex(1); wait(100)
        self.assertIs(w.pdf, w.docs[1]); self.assertIs(w.view.doc, w.docs[1])
        self.assertEqual(w.thumbs.count(), w.pdf.page_count)
        w.tabbar.setCurrentIndex(0); wait(150)
        self.assertAlmostEqual(w.view.zoom, 1.7, places=2)               # lo zoom della scheda è ricordato
        # l'annulla è per documento
        self.assertTrue(w.a_undo.isEnabled())
        w.tabbar.setCurrentIndex(1); wait(50)
        self.assertFalse(w.a_undo.isEnabled())
        # tabella spostabile: l'ordine dei documenti segue le schede
        w.tabbar.moveTab(0, 1); wait(30)
        self.assertEqual([d.path for d in w.docs][0], self.b)
        # chiusura della scheda inattiva senza modifiche
        w._on_tab_close(0); wait(50)
        self.assertEqual(len(w.docs), 1); self.assertIs(w.pdf, w.docs[0])
        w.pdf.modified = False
        w.close_doc(); wait(30)
        self.assertIsNone(w.pdf); self.assertFalse(w.tabbar.isVisible())

    def test_close_checks_every_tab(self):
        from PySide6.QtWidgets import QMessageBox
        w = self.w
        w.open_path(SRC); w.open_path(self.b); wait(100)
        w.docs[0].add_shape(0, "rect", fitz.Rect(50, 50, 150, 120), (1, 0, 0), None, 2)       # modificata, non attiva
        asked = []
        orig = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *a, **k: (asked.append(a[2]), QMessageBox.Cancel)[1])
        try:
            self.assertFalse(w.close())
        finally:
            QMessageBox.question = orig
        self.assertEqual(len(asked), 1); self.assertIn("t.pdf", asked[0]); self.assertIs(w.pdf, w.docs[0])

    def test_print_to_pdf(self):
        from PySide6.QtPrintSupport import QPrinter
        w = self.w
        w.open_path(SRC); wait(100)
        out = os.path.join(TMP, "printed.pdf")
        pr = QPrinter(QPrinter.HighResolution); pr.setOutputFormat(QPrinter.PdfFormat); pr.setOutputFileName(out)
        self.assertTrue(w.print_pages_to(pr, [0, 1]))
        d = fitz.open(out); self.assertEqual(d.page_count, 2); self.assertTrue(d[0].get_images() or d[0].get_drawings())

    def test_export_all_formats(self):
        w = self.w
        w.open_path(SRC); wait(100)
        n = w.pdf.page_count
        base = {"pages": list(range(n)), "dpi": 80, "quality": 70, "tiff_multipage": True, "tiff_compression": "tiff_lzw"}
        d = os.path.join(TMP, "exp"); os.makedirs(d, exist_ok=True)
        for fmt, ext in (("txt", ".txt"), ("docx", ".docx"), ("odt", ".odt"), ("tiff", ".tiff")):
            t = os.path.join(d, "o" + ext)
            self.assertTrue(w.export_to(dict(base, fmt=fmt), t)); self.assertGreater(os.path.getsize(t), 100)
        from PIL import Image
        self.assertEqual(Image.open(os.path.join(d, "o.tiff")).n_frames, n)
        for fmt in ("png", "jpg"):
            self.assertTrue(w.export_to(dict(base, fmt=fmt), os.path.join(d, fmt)))
            self.assertEqual(len(os.listdir(os.path.join(d, fmt))), n)
        import docx
        import zipfile
        docx.Document(os.path.join(d, "o.docx"))                                   # si apre: struttura valida
        self.assertIn("<w:t", zipfile.ZipFile(os.path.join(d, "o.docx")).read("word/document.xml").decode())
        txt = open(os.path.join(d, "o.txt"), encoding="utf-8").read()
        self.assertEqual(txt.strip().split()[:3], w.pdf.doc[0].get_text("text", sort=True).split()[:3])


class FontScaleTests(unittest.TestCase):
    def test_font_scale_and_about_size(self):
        QSettings().clear()
        w = MainWindow(); w.show(); wait(100)
        base = QApplication.font().pointSizeF()
        w._apply_font(150); wait(50)
        self.assertAlmostEqual(QApplication.font().pointSizeF(), base * 1.5, delta=0.6)
        self.assertAlmostEqual(w.menuBar().font().pointSizeF(), base * 1.5, delta=0.6)
        w._apply_font(100); wait(50)
        self.assertAlmostEqual(QApplication.font().pointSizeF(), base, delta=0.6)
        d = dialogs.AboutDialog(w); d.show(); wait(50)
        self.assertGreaterEqual(d.width(), 600); self.assertGreaterEqual(d.height(), 440)
        d.close(); w.pdf and setattr(w.pdf, "modified", False); w.close(); QSettings().clear()


class ImagePropsGuiTests(unittest.TestCase):
    def test_dialog_numeric_units_and_lock(self):
        dialogs.settings().clear()
        d = dialogs.ImageDialog(None, 144.0, 72.0, (200, 100))
        self.assertAlmostEqual(d.wsp.value(), 144.0 / (72 / 25.4), places=2)        # mm di default
        d.unit.setCurrentIndex(3)                                                    # pollici
        self.assertAlmostEqual(d.wsp.value(), 2.0, places=3); self.assertAlmostEqual(d.hsp.value(), 1.0, places=3)
        d.wsp.setValue(4.0); self.assertAlmostEqual(d.hsp.value(), 2.0, places=3)    # proporzioni bloccate
        d.lock.setChecked(False); d.hsp.setValue(1.0); self.assertAlmostEqual(d.wsp.value(), 4.0, places=3)
        w, h, a, r = d.values(); self.assertAlmostEqual(w, 288.0, places=1); self.assertAlmostEqual(h, 72.0, places=1)
        d.lock.setChecked(True); d.wsp.setValue(2.0); self.assertAlmostEqual(d.hsp.value(), 0.5, places=3)   # nuovo rapporto 4:1
        dialogs.settings().clear()

    def test_window_image_properties_flow(self):
        QSettings().clear()
        w = MainWindow(); w.resize(1200, 800); w.show()
        import io
        from PIL import Image
        im = Image.new("RGB", (80, 40), (255, 0, 0)); b = io.BytesIO(); im.save(b, "PNG")
        dd = fitz.open(); pg = dd.new_page(); pg.insert_image(fitz.Rect(100, 100, 260, 180), stream=b.getvalue())
        path = os.path.join(TMP, "ip.pdf"); dd.save(path)
        self.assertTrue(w.open_path(path)); wait(200)
        o = w.pdf.content_at(0, (150, 140)); w.view.select_content(0, o)
        self.assertIsNotNone(w.selected_image())
        m = w.build_context_menu(0, QPointF(150, 140))
        texts = [a.text() for a in m.actions()]
        for t in ("Proprietà immagine…", "Sostituisci immagine…", "Esporta immagine (PNG/JPG/TIFF)…"):
            self.assertIn(t, texts)
        w._rotate_image(0, w.selected_image()[1], 90); wait(100)
        bb = w.pdf.page(0).get_image_info()[0]["bbox"]
        self.assertAlmostEqual(bb[2] - bb[0], 80, delta=2)
        w.pdf.modified = False; w.close(); QSettings().clear()


class MultiSelectGuiTests(unittest.TestCase):
    def setUp(self):
        QSettings().clear()
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show()
        d = fitz.open(); pg = d.new_page()
        pg.insert_text((72, 100), "Testo A", fontsize=14)
        pg.draw_rect(fitz.Rect(300, 300, 360, 340), color=(1, 0, 0), fill=(0, 1, 0))
        self.path = os.path.join(TMP, "ms.pdf"); d.save(self.path)
        self.assertTrue(self.w.open_path(self.path)); wait(200)
        self.v = self.w.view
        self.a = self.w.pdf.add_shape(0, "rect", fitz.Rect(100, 200, 160, 240), (1, 0, 0), None, 2, 1.0)
        self.b = self.w.pdf.add_shape(0, "ellipse", fitz.Rect(200, 200, 260, 240), (0, 0, 1), None, 2, 1.0)
        self.w.changed([0]); wait(100)

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30); QSettings().clear()

    def vp(self, x, y):
        r = self.v.page_rects[0]; return self.v.mapFromScene(QPointF(r.x() + x, r.y() + y))

    def press_move_release(self, a, b, mod=Qt.NoModifier, steps=5):
        vp = self.v.viewport(); pa, pb = self.vp(*a), self.vp(*b)
        QTest.mousePress(vp, Qt.LeftButton, mod, pa)
        for i in range(1, steps + 1):
            QTest.mouseMove(vp, QPoint(pa.x() + (pb.x() - pa.x()) * i // steps, pa.y() + (pb.y() - pa.y()) * i // steps)); wait(5)
        QTest.mouseRelease(vp, Qt.LeftButton, mod, pb); wait(80)

    def test_ctrl_click_band_move_group_delete(self):
        self.w.set_tool("select"); wait(30)
        QTest.mouseClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(130, 220)); wait(60)
        QTest.mouseClick(self.v.viewport(), Qt.LeftButton, Qt.ControlModifier, self.vp(230, 220)); wait(60)
        self.assertEqual(len(self.v.multi), 2)
        QTest.mouseClick(self.v.viewport(), Qt.LeftButton, Qt.ControlModifier, self.vp(230, 220)); wait(60)   # toglie
        self.assertEqual(self.v.sel_xref, self.a)
        # area: seleziona entrambe, le sposta insieme con un solo annulla
        self.v.clear_selection()
        self.press_move_release((80, 180), (290, 260)); self.assertEqual(len(self.v.multi), 2)
        n0 = len(self.w.pdf._undo)
        self.press_move_release((130, 220), (180, 280))
        self.assertEqual(len(self.w.pdf._undo), n0 + 1)
        ra = self.w.pdf.annot_info(0, self.a).rect; self.assertAlmostEqual(ra.x0, 150, delta=5); self.assertAlmostEqual(ra.y0, 260, delta=5)
        self.w.undo(); wait(80)
        self.assertAlmostEqual(self.w.pdf.annot_info(0, self.a).rect.x0, 100, delta=2)
        # raggruppa: un clic seleziona tutto il gruppo; separa lo scioglie
        self.v.clear_selection(); self.press_move_release((80, 180), (290, 260))
        self.assertEqual(len(self.v.multi), 2, "prima di raggruppare")
        self.w.group_selection(); wait(80)
        self.assertEqual(len(self.v.multi), 2, self.w.statusBar().currentMessage())
        self.v.clear_selection(); QTest.mouseClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(130, 220)); wait(60)
        self.assertEqual(len(self.v.multi), 2)
        m = self.w.build_context_menu(0, QPointF(130, 220)); texts = [x.text() for x in m.actions()]
        self.assertIn("Separa il gruppo", texts)
        self.w.ungroup_selection(); wait(60)
        self.assertEqual(self.w.pdf.annot_group(0, self.a), [self.a])
        # elimina multipla = un solo annulla
        self.v.clear_selection(); self.press_move_release((80, 180), (290, 260)); n0 = len(self.w.pdf._undo)
        self.w.delete_selection(); wait(60)
        self.assertEqual(len(self.w.pdf.list_annots(0)), 0); self.assertEqual(len(self.w.pdf._undo), n0 + 1)
        self.w.undo(); wait(60); self.assertEqual(len(self.w.pdf.list_annots(0)), 2)

    def test_editobj_band_with_content_and_redact_toggle(self):
        self.w.set_tool("editobj"); wait(30)
        self.press_move_release((50, 70), (400, 360))
        kinds = sorted((i["kind"], i["obj"]["kind"] if i["kind"] == "content" else "") for i in self.v.multi)
        self.assertIn(("content", "text"), kinds); self.assertIn(("content", "vector"), kinds)
        m = self.w.build_context_menu(0, QPointF(130, 220)); texts = [x.text() for x in m.actions()]
        self.assertIn("Segna per la redazione", texts)
        items = list(self.v.multi)
        self.w.selected_rects_toggle_redact(0, items); wait(60)
        self.assertEqual(self.w.pdf.pending_redactions(), len(items))
        self.v.clear_selection(); self.w.set_tool("select"); wait(30)
        obj = self.w.pdf.content_at(0, (330, 320))
        self.w.set_tool("editobj"); self.v.select_content(0, obj)
        c = self.w.pdf.redact_at(0, (330, 320)); self.assertIsNotNone(c)
        m = self.w.build_context_menu(0, QPointF(330, 320)); texts = [x.text() for x in m.actions()]
        self.assertIn("Annulla redazione", texts)
        self.w._toggle_redact(0, fitz.Rect(obj["rect"])); wait(60)
        self.assertIsNone(self.w.pdf.redact_at(0, (330, 320)))


class UpdateCheckGuiTests(unittest.TestCase):
    def setUp(self):
        self.w = MainWindow(); self.w.resize(1000, 700); self.w.show()
        from PySide6.QtWidgets import QMessageBox
        self.seen = []
        self._orig = (QMessageBox.information, QMessageBox.warning)
        QMessageBox.information = staticmethod(lambda p, t, m, *a, **k: self.seen.append(("info", m)))
        QMessageBox.warning = staticmethod(lambda p, t, m, *a, **k: self.seen.append(("warn", m)))
        self.QMB = QMessageBox

    def tearDown(self):
        self.QMB.information, self.QMB.warning = self._orig
        self.w.close()

    def _run(self, fetch):
        import time
        self.w.check_updates(fetch)
        end = time.time() + 5
        while not self.seen and time.time() < end:
            QApplication.processEvents(); time.sleep(0.01)

    def test_menu_has_item(self):
        self.assertIn(self.w.a_update, self.w.menuBar().actions()[-1].menu().actions())

    def test_up_to_date(self):
        from pdfdesk import __version__
        self._run(lambda: {"version": __version__, "url": "", "notes": ""})
        self.assertEqual(self.seen[0][0], "info")

    def test_network_error(self):
        def boom(): raise OSError("offline")
        self._run(boom)
        self.assertEqual(self.seen[0][0], "warn")


class ThumbAlignmentTests(unittest.TestCase):
    def test_mixed_page_sizes_stay_in_one_column(self):
        import time, tempfile
        d = fitz.open()
        for sz in [(595, 842)] * 4 + [(842, 595), (595, 842), (300, 400)] + [(595, 842)] * 4:
            d.new_page(width=sz[0], height=sz[1]).insert_text((50, 80), "x")
        path = os.path.join(tempfile.mkdtemp(), "mix.pdf"); d.save(path)
        w = MainWindow(path); w.resize(1100, 700); w.show()
        end = time.time() + 6
        while time.time() < end:
            QApplication.processEvents(); time.sleep(0.01)
        t = w.thumbs
        xs = {t.visualItemRect(t.item(i)).x() for i in range(t.count())}
        self.assertEqual(len(xs), 1, xs)
        w.close()


class SignCursorEscRotateTests(unittest.TestCase):
    def setUp(self):
        QSettings().clear()
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show(); self.assertTrue(self.w.open_path(SRC)); wait(200)

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30)

    def test_sign_tool_cursor_is_custom_bitmap(self):
        self.w.current_signature = "x"          # evita la finestra di scelta firma
        self.w.view.set_tool("sign")
        cur = self.w.view.viewport().cursor()
        self.assertEqual(cur.shape(), Qt.BitmapCursor)
        self.assertFalse(cur.pixmap().isNull())
        self.w.view.set_tool("select")
        self.assertEqual(self.w.view.viewport().cursor().shape(), Qt.ArrowCursor)

    def test_escape_returns_to_select(self):
        for t in ("pen", "rect", "textsel", "editobj"):
            self.w.set_tool(t); wait(20)
            QTest.keyClick(self.w.view, Qt.Key_Escape); wait(30)
            self.assertEqual(self.w.tool, "select", t)
            self.assertTrue(self.w.tool_actions["select"].isChecked())

    def test_draw_signature_canvas_draws(self):
        from pdfdesk.dialogs import DrawSignatureDialog
        d = DrawSignatureDialog(self.w); d.show(); wait(50)
        c = d.canvas
        QTest.mousePress(c, Qt.LeftButton, Qt.NoModifier, QPoint(40, 100))
        for x in range(50, 300, 10):
            QTest.mouseMove(c, QPoint(x, 100 + (x % 30)))
        QTest.mouseRelease(c, Qt.LeftButton, Qt.NoModifier, QPoint(300, 100))
        self.assertTrue(c.strokes and len(c.strokes[0]) > 5)
        self.assertIsNotNone(d.result_image())
        c.grab()                                   # il paintEvent non deve sollevare eccezioni
        d.close(); d.deleteLater()

    def test_mouse_rotation_of_selected_image(self):
        from pdfdesk import sigstore
        from PySide6.QtGui import QImage, QColor
        w = self.w
        img = QImage(200, 100, QImage.Format_ARGB32); img.fill(QColor(200, 30, 30))
        x = w.pdf.add_image(0, fitz.Rect(100, 300, 300, 400), sigstore.png_bytes(img)); w.changed([0]); wait(100)
        w.set_tool("select"); wait(30)
        v = w.view; o = v.page_rects[0]
        def vp(px, py): return v.mapFromScene(QPointF(o.x() + px, o.y() + py))
        QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, vp(200, 350)); wait(60)
        self.assertEqual(v.sel_xref, x)
        self.assertFalse(v._sel.rotate_mode)
        QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, vp(200, 350)); wait(60)     # secondo clic: rotazione
        self.assertTrue(v._sel.rotate_mode)
        # trascinamento: da destra del centro a sotto il centro = 90° in senso orario
        QTest.mousePress(v.viewport(), Qt.LeftButton, Qt.NoModifier, vp(290, 350))
        for k in range(1, 10):
            QTest.mouseMove(v.viewport(), vp(200 + 90 * (1 - k / 9), 350 + 90 * (k / 9)))
        QTest.mouseRelease(v.viewport(), Qt.LeftButton, Qt.NoModifier, vp(200, 440)); wait(150)
        r = w.pdf.annot_info(0, v.sel_xref).rect if v.sel_info else None
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.width, 100, delta=3)       # 200×100 ruotata di 90° → 100×200
        self.assertAlmostEqual(r.height, 200, delta=3)
        self.assertFalse(v._sel.rotate_mode)


class CommentsStylesDoubleClickTests(unittest.TestCase):
    def setUp(self):
        QSettings().clear()
        self.w = MainWindow(); self.w.resize(1200, 800); self.w.show(); self.assertTrue(self.w.open_path(SRC)); wait(200)
        self.v = self.w.view; self.o = self.v.page_rects[0]

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close(); wait(30)

    def vp(self, px, py):
        return self.v.mapFromScene(QPointF(self.o.x() + px, self.o.y() + py))

    def test_verify_disabled_without_signatures(self):
        self.assertFalse(self.w.pdf.is_signed)
        self.assertFalse(self.w.a_verify.isEnabled())

    def test_comment_tool_adds_note_and_edit(self):
        self.w._comment_text = lambda title, text="": "Primo commento"
        self.w.set_tool("comment"); wait(30)
        QTest.mouseClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(400, 500)); wait(100)
        notes = [a for a in self.w.pdf.list_annots(0) if a.type == 0]
        self.assertEqual(len(notes), 1); self.assertEqual(notes[0].text, "Primo commento")
        self.assertTrue(notes[0].movable)
        # doppio clic con Seleziona: strumento Commento + modifica
        self.w._comment_text = lambda title, text="": "Modificato"
        self.w.set_tool("select"); wait(30)
        r = notes[0].rect
        QTest.mouseDClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)); wait(100)
        self.assertEqual(self.w.tool, "comment")
        self.assertEqual([a.text for a in self.w.pdf.list_annots(0) if a.type == 0], ["Modificato"])
        # salvato come annotazione Text standard
        out = os.path.join(TMP, "comm.pdf"); self.assertTrue(self.w.pdf.save_as(out) if hasattr(self.w.pdf, "save_as") else True)

    def test_double_click_switches_tool(self):
        from pdfdesk import dialogs as dlg
        orig = dlg.TextDialog.exec
        dlg.TextDialog.exec = lambda self: dlg.TextDialog.Rejected
        try:
            x = self.w.pdf.add_text(0, fitz.Rect(100, 600, 300, 640), "Casella", 12, "helv", (0, 0, 0), None, 0, "")
            r2 = self.w.pdf.add_shape(0, "rect", fitz.Rect(100, 650, 200, 700), (1, 0, 0), None, 2.0)
            self.w.changed([0]); wait(100)
            for xref, expected in ((x, "text"), (r2, "rect")):
                self.w.set_tool("select"); wait(30)
                inf = self.w.pdf.annot_info(0, xref)
                cx, cy = (inf.rect.x0 + inf.rect.x1) / 2, (inf.rect.y0 + inf.rect.y1) / 2
                if expected == "rect":
                    cx, cy = inf.rect.x0 + 1, (inf.rect.y0 + inf.rect.y1) / 2           # sul bordo
                QTest.mouseDClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(cx, cy)); wait(100)
                self.assertEqual(self.w.tool, expected)
                self.assertEqual(self.v.sel_xref, xref)
            # testo già presente nel PDF: strumento «Modifica testo»
            self.w.set_tool("select"); wait(30)
            called = []
            self.w.edit_text_block = lambda pno, blk: called.append(blk["text"])
            QTest.mouseDClick(self.v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(150, 160)); wait(100)
            self.assertEqual(self.w.tool, "edittext"); self.assertTrue(called)
        finally:
            dlg.TextDialog.exec = orig

    def test_double_click_on_image_selects_toggles_rotation_and_switches_tool(self):
        from pdfdesk import sigstore
        from PySide6.QtGui import QImage, QColor
        shown = []
        self.w.image_properties = lambda *a, **k: shown.append(a)        # il doppio clic non deve più aprire finestre
        img = QImage(200, 100, QImage.Format_ARGB32); img.fill(QColor(30, 120, 200))
        x = self.w.pdf.add_image(0, fitz.Rect(100, 300, 300, 400), sigstore.png_bytes(img)); self.w.changed([0]); wait(100)
        self.w.set_tool("select"); wait(30)
        v = self.v
        QTest.mouseDClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(200, 350)); wait(100)
        self.assertEqual(self.w.tool, "editobj")                           # strumento adatto
        self.assertEqual(v.sel_xref, x)                                    # immagine selezionata
        self.assertTrue(v._sel.rotate_mode)                                # e subito in rotazione (secondo clic)
        self.assertFalse(shown)
        QTest.mouseDClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(200, 350)); wait(100)
        self.assertEqual(self.w.tool, "editobj")
        self.assertFalse(v._sel.rotate_mode)                               # ogni clic alterna selezione e rotazione
        QTest.mouseDClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, self.vp(200, 350)); wait(100)
        self.assertTrue(v._sel.rotate_mode)

    def test_text_dialog_style_buttons_and_properties_panel(self):
        d = dialogs.TextDialog(self.w, "t", "x", 12, "tibo", (0, 0, 0), None, style="u")
        self.assertEqual(d.font.code(), "tiro")
        self.assertEqual(d.values()["style"], "bu")                       # tibo = Times + grassetto
        d.styles_.btn["s"].setChecked(True); d.styles_.btn["i"].setChecked(True)
        self.assertEqual(d.values()["style"], "biu" + "s")
        d.font.set_code("helv"); d.close()
        got = []
        self.w.props.changed.connect(lambda kw: got.append(kw))
        self.w.props.styles_.btn["u"].setChecked(True)
        self.assertIn({"style": "u"}, got)


class UiScaleTests(unittest.TestCase):
    def setUp(self):
        dialogs.settings().clear()
        self._env = os.environ.pop("QT_SCALE_FACTOR", None)

    def tearDown(self):
        dialogs.settings().clear()
        os.environ.pop("QT_SCALE_FACTOR", None)
        if self._env is not None:
            os.environ["QT_SCALE_FACTOR"] = self._env

    def test_scale_setting_and_env(self):
        from pdfdesk import cli
        self.assertEqual(cli.ui_scale_percent(), 0)
        cli.configure_hidpi()
        self.assertNotIn("QT_SCALE_FACTOR", os.environ)           # automatica: nessuna forzatura
        dialogs.settings().setValue("ui/scale", 150)
        self.assertEqual(cli.ui_scale_percent(), 150)
        cli.configure_hidpi()
        self.assertEqual(os.environ.get("QT_SCALE_FACTOR"), "1.5")
        os.environ["QT_SCALE_FACTOR"] = "2"                        # la variabile dell'utente ha la precedenza
        cli.configure_hidpi()
        self.assertEqual(os.environ["QT_SCALE_FACTOR"], "2")
        dialogs.settings().setValue("ui/scale", 9999)                     # valore assurdo: ignorato
        self.assertEqual(cli.ui_scale_percent(), 0)

    def test_prefs_dialog_roundtrip(self):
        d = dialogs.PreferencesDialog()
        self.assertEqual(d.scale.currentData(), 0)
        d.scale.setCurrentIndex(d.scale.findData(200)); d.store()
        self.assertEqual(int(dialogs.settings().value("ui/scale")), 200)
        d2 = dialogs.PreferencesDialog()
        self.assertEqual(d2.scale.currentData(), 200)
        d.deleteLater(); d2.deleteLater()

    def test_cursors_hidpi(self):
        from pdfdesk.view import sign_cursor, rotate_cursor
        for c in (sign_cursor(), rotate_cursor()):
            pm = c.pixmap()
            self.assertFalse(pm.isNull())
            self.assertGreaterEqual(pm.devicePixelRatio(), 1.0)
            self.assertGreaterEqual(pm.width(), 32)


class GpuModeTests(unittest.TestCase):
    def setUp(self):
        dialogs.settings().remove("ui/gpu"); self._e = os.environ.pop("PDFDESK_GL", None)

    def tearDown(self):
        dialogs.settings().remove("ui/gpu"); os.environ.pop("PDFDESK_GL", None)
        if self._e is not None:
            os.environ["PDFDESK_GL"] = self._e

    def test_mode_and_fallback(self):
        from pdfdesk import view
        self.assertEqual(view.gpu_mode(), "software")
        dialogs.settings().setValue("ui/gpu", "opengl")
        self.assertEqual(view.gpu_mode(), "opengl")
        os.environ["PDFDESK_GL"] = "0"
        self.assertEqual(view.gpu_mode(), "software")
        os.environ["PDFDESK_GL"] = "1"
        v = view.DocView()                      # con la piattaforma offscreen OpenGL non c'è: ritorno silenzioso al software
        self.assertEqual(v.gl_active, view.gl_available())
        v.deleteLater()

    def test_prefs_roundtrip(self):
        d = dialogs.PreferencesDialog()
        d.gpu.setCurrentIndex(d.gpu.findData("opengl")); d.store()
        self.assertEqual(str(dialogs.settings().value("ui/gpu")), "opengl")
        d.deleteLater()


class HomePageTests(unittest.TestCase):
    """Pagina «Attività»: all'avvio, pulsante della barra, recenti, attività, chiusura dell'ultimo documento."""

    def setUp(self):
        settings().clear()
        import tempfile, shutil
        self.tmp = tempfile.mkdtemp()
        self.recents = []
        for i in range(12):
            p = os.path.join(self.tmp, f"doc{i}.pdf"); shutil.copy(SRC, p); self.recents.append(p)
        settings().setValue("recent", self.recents + [os.path.join(self.tmp, "sparito.pdf")])
        settings().setValue("recent_max", 30)

    def tearDown(self):
        settings().clear()

    def test_shown_at_startup_with_recent_and_activities(self):
        w = MainWindow(); w.resize(1200, 860); w.show(); wait(100)
        try:
            self.assertTrue(w.home_visible()); self.assertFalse(w.view.isVisible()); self.assertTrue(w.a_home.isChecked())
            self.assertFalse(w.dock_pages.isVisible())
            self.assertEqual(len(w.home.rows), 10)                                  # massimo 10, i file mancanti esclusi
            self.assertEqual([r.path for r in w.home.rows], self.recents[:10])
            self.assertEqual(set(w.home.cards), {"open", "new", "merge", "scan", "form", "sign", "compress", "standard", "export",
                                                  "translate", "verify", "redact"})
            self.assertIs(w.bars[0].actions()[0], w.a_home)                         # primo pulsante della barra principale
        finally:
            w.close(); wait(30)

    def test_not_shown_when_opening_a_file_or_disabled(self):
        w = MainWindow(SRC); w.show(); wait(300)
        try:
            self.assertFalse(w.home_visible()); self.assertTrue(w.view.isVisible())
        finally:
            w.pdf.modified = False; w.close(); wait(30)
        settings().setValue("ui/home_start", False)
        w = MainWindow(); w.show(); wait(50)
        try:
            self.assertFalse(w.home_visible())
        finally:
            w.close(); wait(30)

    def test_open_recent_toggle_and_close_last(self):
        w = MainWindow(); w.resize(1200, 860); w.show(); wait(100)
        try:
            dock = w.dock_pages.isVisible()
            w.home.rows[2].click(); wait(300)
            self.assertIsNotNone(w.pdf); self.assertEqual(w.pdf.path, self.recents[2])
            self.assertFalse(w.home_visible()); self.assertTrue(w.view.isVisible())
            w.a_home.trigger(); wait(50)
            self.assertTrue(w.home_visible()); self.assertEqual(w.home.rows[0].path, self.recents[2])   # appena aperto: primo
            w.a_home.trigger(); wait(50)
            self.assertFalse(w.home_visible())                                      # di nuovo: torna al documento
            w.a_home.trigger(); wait(50)
            w._on_tab_clicked(0); wait(50); self.assertFalse(w.home_visible())        # clic sulla scheda attiva
            w.close_doc(); wait(100)
            self.assertIsNone(w.pdf); self.assertTrue(w.home_visible())             # chiuso l'ultimo: pagina Attività
            w.a_home.trigger(); wait(50); self.assertTrue(w.home_visible())         # senza documenti resta aperta
        finally:
            if w.pdf: w.pdf.modified = False
            w.close(); wait(30)

    def test_remove_recent_and_activities_ask_for_file(self):
        import unittest.mock as m
        from PySide6.QtWidgets import QFileDialog
        w = MainWindow(); w.show(); wait(50)
        try:
            w.home.remove_recent.emit(self.recents[0]); wait(20)
            self.assertNotIn(self.recents[0], [r.path for r in w.home.rows])
            self.assertNotIn(self.recents[0], settings().value("recent"))
            calls = []
            with m.patch.object(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", ""))):
                for k in ("form", "sign", "compress", "standard", "export", "verify", "redact"):
                    w.home.cards[k].click()                                     # annullando la scelta non succede nulla
            self.assertIsNone(w.pdf); self.assertTrue(w.home_visible())
            with m.patch.object(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (__import__("test_features").FORM, ""))):
                w.home.cards["form"].click(); wait(300)
            self.assertEqual(w.tool, "form"); self.assertFalse(w.home_visible())
            with m.patch.object(w, "new_doc", lambda: calls.append("new")), m.patch.object(w, "merge_dialog", lambda: calls.append("merge")):
                w.run_activity("new"); w.run_activity("merge")
            self.assertEqual(calls, ["new", "merge"])
        finally:
            if w.pdf: w.pdf.modified = False
            w.close(); wait(30)

    def test_dock_state_is_not_saved_hidden(self):
        w = MainWindow(); w.show(); wait(50)
        self.assertTrue(w.home_visible()); was = w._dock_was
        w.close(); wait(30)
        w2 = MainWindow(); w2.show(); wait(50)
        try:
            w2.show_home(False); self.assertEqual(w2.dock_pages.isVisible(), was)
        finally:
            w2.close(); wait(30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
