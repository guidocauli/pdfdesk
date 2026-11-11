# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Test: metadati, compressione avanzata, estrazione di immagini/aree, dati delle firme digitali.
import os, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-new-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")
import pymupdf as fitz
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from make_samples import make_text_pdf
from pdfdesk import compress, dialogs, extract, signing
from pdfdesk.core import PdfDocument
from pdfdesk.mainwindow import MainWindow

QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, TMP)
app = QApplication.instance() or QApplication([])
SRC = os.path.join(TMP, "t.pdf"); make_text_pdf(SRC)


def pdf_with_images(path):
    d = fitz.open()
    for i in range(2):
        pg = d.new_page()
        pg.insert_text((72, 80), f"Pagina {i + 1}", fontsize=14)
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), False); pm.set_rect(pm.irect, (200, 30 * (i + 1), 60))
        pg.insert_image(fitz.Rect(72, 120, 272, 270), pixmap=pm)
    d.save(path); d.close()


class MetadataTests(unittest.TestCase):
    def test_roundtrip_and_undo(self):
        p = PdfDocument.open(SRC)
        p.set_metadata({"title": "Titolo X", "author": "Guido"}, {"Progetto": "Alfa"})
        m = p.get_metadata()
        self.assertEqual(m["standard"]["title"], "Titolo X")
        self.assertEqual(m["custom"], {"Progetto": "Alfa"})
        d = fitz.open("pdf", p.current_bytes())
        self.assertEqual(d.metadata["author"], "Guido")
        p.undo()
        self.assertNotEqual(p.get_metadata()["standard"]["title"], "Titolo X")

    def test_xmp_regen_and_remove(self):
        p = PdfDocument.open(SRC)
        std = {"title": "Con XMP"}
        p.set_metadata(std, {}, xmp=p.make_xmp(std))
        self.assertIn("Con XMP", p.get_metadata()["xmp"])
        p.set_metadata(std, {}, remove_xmp=True)
        self.assertEqual(p.get_metadata()["xmp"], "")

    def test_redaction_strips_metadata(self):
        p = PdfDocument.open(SRC)
        p.set_metadata({"title": "RISERVATO", "author": "Mario"}, {"Segreto": "x"})
        p.add_redact(0, fitz.Rect(50, 50, 300, 120))
        p.apply_redactions(strip_metadata=True)
        d = fitz.open("pdf", p.current_bytes())
        self.assertFalse(d.metadata.get("title"))
        self.assertNotIn(b"RISERVATO", p.current_bytes())
        self.assertNotIn(b"Segreto", p.current_bytes())

    def test_dialog_values(self):
        p = PdfDocument.open(SRC)
        dlg = dialogs.MetadataDialog(None, p.get_metadata(), p.document_info(), p.standard)
        from pdfdesk.core import display_to_pdf_date
        v = dlg._collect(display_to_pdf_date)
        self.assertIn("standard", v)
        self.assertIn("custom", v)


class CompressionTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "img.pdf"); pdf_with_images(self.path)
        self.data = open(self.path, "rb").read()

    def test_custom_resample_shrinks(self):
        o = compress.SaveOptions(preset="custom", dpi_threshold=50, dpi_target=40, quality=30)
        out = compress.optimize_bytes(self.data, o)
        fitz.open("pdf", out)  # valido
        self.assertLessEqual(len(out), len(self.data))

    def test_cleanup_options(self):
        d = fitz.open(self.path); d.embfile_add("a.txt", b"allegato"); b = d.tobytes()
        out = compress.optimize_bytes(b, compress.SaveOptions(drop_attachments=True))
        self.assertEqual(fitz.open("pdf", out).embfile_count(), 0)

    def test_analysis(self):
        a = compress.analyze(self.data)
        self.assertTrue(compress.format_analysis(a))

    def test_standard_disables_controls(self):
        dlg = dialogs.SaveDialog(None, os.path.join(TMP, "o.pdf"), False, len(self.data), raw=lambda: self.data)
        self.assertTrue(dlg.preset.isEnabled())
        dlg.std.combo.setCurrentIndex(dlg.std.combo.findData("pdfa-2b"))
        self.assertFalse(dlg.preset.isEnabled())
        self.assertFalse(dlg.meta.isEnabled())


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "img.pdf"); pdf_with_images(self.path)
        self.doc = fitz.open(self.path)

    def test_list_and_extract_all_formats(self):
        items = extract.list_images(self.doc)
        self.assertEqual(len(items), 2)
        for fmt, ext in (("png", ".png"), ("jpg", ".jpg"), ("tiff", ".tif")):
            folder = os.path.join(TMP, "ex_" + fmt)
            out = extract.extract_images(self.doc, items, fmt, folder)
            self.assertEqual(len(out), 2)
            for f in out:
                self.assertTrue(os.path.getsize(f) > 0)
            self.assertTrue(out[0].endswith(extract.FORMATS[fmt][1]))

    def test_render_area(self):
        pix = extract.render_area(self.doc, 0, fitz.Rect(72, 120, 272, 270), 144)
        self.assertEqual((pix.width, pix.height), (400, 300))
        with self.assertRaises(ValueError):
            extract.render_area(self.doc, 0, fitz.Rect(2000, 2000, 2100, 2100), 72)

    def test_gui_wiring(self):
        w = MainWindow(); w.show()
        self.assertFalse(w.a_extract_imgs.isEnabled() or w.a_meta.isEnabled())
        self.assertTrue(w.open_path(self.path))
        self.assertTrue(w.a_extract_imgs.isEnabled() and w.a_meta.isEnabled())
        out = w.grab_area(0, fitz.Rect(72, 120, 272, 270), os.path.join(TMP, "area.png"),
                          {"fmt": "png", "dpi": 100, "quality": 90, "annots": True, "copy": False})
        self.assertTrue(os.path.getsize(out) > 0)
        res = w.extract_images(os.path.join(TMP, "gui_ex"), extract.list_images(w.pdf.doc), "tiff")
        self.assertEqual(len(res), 2)
        w.pdf.modified = False; w.close()


class SignatureDataTests(unittest.TestCase):
    def test_full_details(self):
        p12 = os.path.join(TMP, "s.p12")
        signing.create_self_signed_p12(p12, "pw", "Guido Prova", "CNR", "guido@example.org")
        signed = signing.sign_pdf_bytes(open(SRC, "rb").read(), signing.SignParams(p12, "pw", reason="Prova", location="Bari"))
        st = signing.verify_pdf_bytes(signed)
        self.assertEqual(len(st), 1)
        s = st[0]
        self.assertTrue(s.intact and s.valid and not s.trusted)
        self.assertEqual((s.reason, s.location), ("Prova", "Bari"))
        self.assertEqual(dict(s.cert.subject)["Nome comune (CN)"], "Guido Prova")
        self.assertEqual(len(s.cert.sha256.split(":")), 32)
        self.assertTrue(s.cert.self_signed)
        self.assertEqual(s.digest_algo, "sha256")
        txt = signing.describe_status(s)
        for needle in ("Guido Prova", "Bari", "SHA-256", "Numero di serie", "Valido fino al", "Byte range"):
            self.assertIn(needle, txt)
        dlg = dialogs.VerifyDialog(None, st)
        self.assertIn("Impronta SHA-256", dlg.detail.toPlainText())
        # modifica dopo la firma → segnalata
        tampered = signed + b"\n%extra"
        dialogs.VerifyDialog(None, signing.verify_pdf_bytes(tampered))
        dialogs.VerifyDialog(None, [])




class FixesTests(unittest.TestCase):
    def test_dialogs_are_application_modal(self):
        import inspect
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDialog as QD
        for name, cls in inspect.getmembers(dialogs, inspect.isclass):
            if issubclass(cls, QD) and cls.__module__ == dialogs.__name__ and name != "QDialog":
                self.assertTrue(issubclass(cls, dialogs.QDialog), name)
        d = dialogs.TextDialog(None, "t", "x", 12, "helv", (0, 0, 0))
        self.assertTrue(d.isModal())
        self.assertEqual(d.windowModality(), Qt.ApplicationModal)

    def test_redact_object_click_toggle_and_undo(self):
        path = os.path.join(TMP, "red.pdf"); pdf_with_images(path)
        w = MainWindow(); w.show(); self.assertTrue(w.open_path(path))
        pdf = w.pdf
        from PySide6.QtCore import QPointF
        self.assertTrue(w.redact_object_at(0, QPointF(150, 190)))          # immagine
        self.assertEqual(pdf.pending_redactions(), 1)
        self.assertTrue(w.redact_object_at(0, QPointF(80, 75)))            # testo
        self.assertEqual(pdf.pending_redactions(), 2)
        self.assertTrue(w.redact_object_at(0, QPointF(150, 190)))          # secondo clic: toglie
        self.assertEqual(pdf.pending_redactions(), 1)
        pdf.undo(); self.assertEqual(pdf.pending_redactions(), 2)          # annullabile
        pdf.undo(); pdf.undo(); self.assertEqual(pdf.pending_redactions(), 0)
        pdf.redo(); self.assertEqual(pdf.pending_redactions(), 1)
        pdf.modified = False; w.close()

    def test_move_images_with_masks_and_alpha(self):
        import io
        from PIL import Image
        d = fitz.open(); pg = d.new_page()
        def png(mode):
            b = io.BytesIO(); Image.new(mode, (60, 40), (200, 50, 50, 128) if mode == "RGBA" else (200, 50, 50)).save(b, "PNG"); return b.getvalue()
        pg.insert_image(fitz.Rect(50, 50, 150, 120), stream=png("RGBA"))
        base = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 60), False); base.set_rect(base.irect, (0, 200, 0))
        x = pg.insert_image(fitz.Rect(200, 200, 300, 260), pixmap=base)
        sm = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 20, 15), False); sm.set_rect(sm.irect, (100,))   # maschera di altra dimensione
        smx = d.get_new_xref(); d.update_object(smx, "<</Type/XObject/Subtype/Image/Width 20/Height 15/ColorSpace/DeviceGray/BitsPerComponent 8>>")
        d.update_stream(smx, sm.samples, new=True); d.xref_set_key(x, "SMask", f"{smx} 0 R")
        path = os.path.join(TMP, "masks.pdf"); d.save(path)
        p = PdfDocument.open(path)
        for pt in ((100, 85), (250, 230)):
            o = p.content_at(0, pt); self.assertEqual(o["kind"], "image")
            p.move_content(0, o, fitz.Rect(o["rect"]) + (15, 15, 15, 15))
        self.assertEqual(len(fitz.open("pdf", p.current_bytes())[0].get_images()), 2)


class AlphaTests(unittest.TestCase):
    def test_pixmap_alpha_all_kinds(self):
        import io
        from PIL import Image
        from pdfdesk import imgutil
        # to_png_bytes conserva la trasparenza di modi diversi
        for mode, col in (("RGBA", (10, 20, 30, 40)), ("LA", (100, 50)), ("P", 5), ("CMYK", (10, 20, 30, 0)), ("I;16", 3000)):
            im = Image.new(mode, (8, 6), col)
            if mode == "P":
                im.info["transparency"] = 5
            b = io.BytesIO(); im.save(b, "PNG" if mode != "CMYK" else "TIFF"); out = imgutil.to_png_bytes(b.getvalue())
            r = Image.open(io.BytesIO(out)); self.assertEqual(r.size, (8, 6))
            if mode in ("RGBA", "LA", "P"):
                self.assertIn("A", r.mode if r.mode != "P" else "RGBA", mode)
        # immagine PDF con alfa proprio (PNG RGBA via stream) → pixmap con alfa, spostabile e ri-estraibile
        d = fitz.open(); pg = d.new_page()
        b = io.BytesIO(); Image.new("RGBA", (30, 20), (255, 0, 0, 100)).save(b, "PNG")
        pg.insert_image(fitz.Rect(50, 50, 150, 120), stream=b.getvalue())
        path = os.path.join(TMP, "alpha.pdf"); d.save(path)
        dd = fitz.open(path); xr = dd[0].get_images(full=True)[0][0]
        pm = imgutil.image_pixmap(dd, xr)
        self.assertTrue(pm.alpha)
        col, mask = imgutil.split_alpha(pm)                       # base senza alfa + maschera: nessun errore «must not have an alpha channel»
        self.assertFalse(col.alpha); self.assertEqual((mask.width, mask.height), (30, 20))
        again = imgutil.with_mask(pm, mask)                       # anche partendo da un pixmap che ha già l'alfa
        self.assertTrue(again.alpha)
        out = extract.image_pixmap(dd, xr)
        f = extract.write_pixmap(out, os.path.join(TMP, "alpha_out.png"), "png")
        self.assertEqual(Image.open(f).mode, "RGBA")
        p = PdfDocument.open(path); o = p.content_at(0, (100, 85))
        p.move_content(0, o, fitz.Rect(o["rect"]) + (10, 10, 10, 10))
        from pdfdesk.view import pix_to_qimage
        self.assertFalse(pix_to_qimage(pm).isNull())
        self.assertFalse(pix_to_qimage(fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 5, 5), False)).isNull())


class ContextMenuTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "ctx.pdf"); pdf_with_images(self.path)
        self.w = MainWindow(); self.w.resize(1000, 800); self.w.show()
        self.assertTrue(self.w.open_path(self.path))

    def tearDown(self):
        self.w.pdf.modified = False; self.w.close()

    @staticmethod
    def texts(m):
        return [a.text() for a in m.actions() if a.text()]

    def test_menus_by_object_kind(self):
        from PySide6.QtCore import QPointF
        w, v = self.w, self.w.view
        v.select_content(0, w.pdf.content_at(0, (150, 190)))                 # immagine
        t = self.texts(w.build_context_menu(0, QPointF(150, 190)))
        for x in ("Esporta immagine (PNG/JPG/TIFF)…", "Segna per la redazione", "Elimina", "Salva l'area come immagine…"):
            self.assertIn(x, t)
        v.select_content(0, w.pdf.content_at(0, (80, 75)))                   # testo
        t = self.texts(w.build_context_menu(0, QPointF(80, 75)))
        for x in ("Modifica testo…", "Copia testo", "Marca il testo"):
            self.assertIn(x, t)
        v.clear_selection()                                                  # pagina vuota
        t = self.texts(w.build_context_menu(0, QPointF(400, 600)))
        self.assertIn("Aggiungi casella di testo qui", t)
        self.assertNotIn("Elimina", t)

    def test_annotation_menu_and_actions(self):
        from PySide6.QtCore import QPointF
        w, v = self.w, self.w.view
        xr = w.pdf.add_shape(0, "rect", fitz.Rect(300, 300, 400, 380), (1, 0, 0), None, 1, 1.0)
        w.changed([0]); v.select(0, xr)
        m = w.build_context_menu(0, QPointF(350, 340))
        acts = {a.text(): a for a in m.actions()}
        acts["Segna per la redazione"].trigger()
        self.assertEqual(w.pdf.pending_redactions(), 1)
        v.select(0, xr)
        w.build_context_menu(0, QPointF(350, 340)).actions()
        acts = {a.text(): a for a in w.build_context_menu(0, QPointF(350, 340)).actions()}
        acts["Elimina"].trigger()
        self.assertIsNone(w.pdf.annot_info(0, xr))
        acts2 = {a.text(): a for a in w.build_context_menu(0, QPointF(350, 340)).actions()}
        w.pdf.undo(); w.pdf.undo()

    def test_right_click_selects_object(self):
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtGui import QContextMenuEvent
        v = self.w.view; got = []
        v.contextRequested.connect(lambda pno, p, g: got.append(pno))
        r = v.page_rects[0]
        pt = v.mapFromScene(QPointF(r.x() + 150, r.y() + 190))
        v.contextRequested.disconnect(self.w.on_context)          # il menu reale (exec) bloccherebbe il test
        v.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Mouse, pt, v.viewport().mapToGlobal(pt)))
        self.assertEqual(got, [0])
        self.assertIsNotNone(v.sel_content)
        self.assertEqual(v.sel_content["kind"], "image")


class SignedUndoTests(unittest.TestCase):
    def setUp(self):
        d = fitz.open(); pg = d.new_page(); pg.insert_text((72, 100), "Documento firmato", fontsize=14)
        pg.draw_rect(fitz.Rect(72, 200, 172, 260), color=(1, 0, 0), fill=(0, 1, 0))
        b = d.tobytes(); d.close()
        p12 = os.path.join(TMP, "su.p12"); signing.create_self_signed_p12(p12, "pw", "Prova", "CNR", "a@b.it")
        self.orig = signing.sign_pdf_bytes(b, signing.SignParams(p12, "pw"))
        self.path = os.path.join(TMP, "signed_undo.pdf"); open(self.path, "wb").write(self.orig)

    def sig(self, p):
        import hashlib
        return hashlib.md5(p.doc[0].get_pixmap(dpi=40).samples).hexdigest()

    def test_undo_redo_and_incremental_save(self):
        p = PdfDocument.open(self.path); self.assertTrue(p.is_signed)
        s0 = self.sig(p)
        o = p.content_at(0, (120, 230)); p.move_content(0, o, fitz.Rect(o["rect"]) + (40, 40, 40, 40)); s1 = self.sig(p)
        p.add_shape(0, "rect", fitz.Rect(300, 300, 400, 360), (1, 0, 0), None, 2, 1.0); s2 = self.sig(p)
        p.set_metadata({"title": "T"}, {})
        self.assertTrue(p.can_undo)
        p.undo(); p.undo(); self.assertEqual(self.sig(p), s1)
        p.undo(); self.assertEqual(self.sig(p), s0); self.assertFalse(p.can_undo)
        self.assertEqual(p.current_bytes(), self.orig)                      # tutto annullato: file identico
        p.redo(); p.redo(); p.redo(); self.assertEqual(self.sig(p), s2)
        out = p.current_bytes()
        self.assertTrue(out.startswith(self.orig))                          # byte firmati intatti
        r = fitz.open("pdf", out); self.assertEqual(r.page_count, 1); self.assertEqual(r.metadata["title"], "T")
        st = signing.verify_pdf_bytes(out)[0]; self.assertTrue(st.intact and st.valid)

    def test_permanent_op_defers_signature_drop(self):
        p = PdfDocument.open(self.path)
        o = p.content_at(0, (120, 230)); p.delete_content(0, o)
        out = p.current_bytes()                                             # non altera il documento aperto
        self.assertTrue(p.is_signed); self.assertTrue(p.can_undo)
        self.assertFalse(out.startswith(self.orig))
        self.assertEqual(signing.verify_pdf_bytes(out), [])
        p.current_bytes(); self.assertTrue(p.is_signed)
        p.mark_saved(self.path)                                             # salvataggio riuscito: firme scartate
        self.assertFalse(p.is_signed)

    def test_permanent_op_keep_signatures(self):
        p = PdfDocument.open(self.path)
        o = p.content_at(0, (120, 230)); p.delete_content(0, o)
        p.keep_signatures = True
        out = p.current_bytes()
        self.assertTrue(out.startswith(self.orig))
        st = signing.verify_pdf_bytes(out)[0]; self.assertTrue(st.intact)
        p.mark_saved(self.path); self.assertTrue(p.is_signed); self.assertFalse(p.keep_signatures)

    def test_object_streams_document(self):
        make_text_pdf(os.path.join(TMP, "t3.pdf"))
        data = compress.optimize_bytes(open(os.path.join(TMP, "t3.pdf"), "rb").read(), compress.SaveOptions("medium"))
        p12 = os.path.join(TMP, "su2.p12"); signing.create_self_signed_p12(p12, "pw", "T")
        signed = signing.sign_pdf_bytes(data, signing.SignParams(p12, "pw", "R", "L", "F"))
        path = os.path.join(TMP, "s_objstm.pdf"); open(path, "wb").write(signed)
        p = PdfDocument.open(path); n = p.doc.page_count
        p.add_shape(0, "rect", fitz.Rect(100, 400, 200, 450), (1, 0, 0), None, 2, 1.0)
        out = p.current_bytes(); self.assertEqual(fitz.open("pdf", out).page_count, n)
        self.assertTrue(signing.verify_pdf_bytes(out)[0].valid)


class GridAndThumbsTests(unittest.TestCase):
    def test_grid_settings_and_snap(self):
        from PySide6.QtCore import QRectF
        s = QSettings(); s.setValue("grid/unit", "mm"); s.setValue("grid/x", 10); s.setValue("grid/y", 5)
        s.setValue("grid/snap", True)
        from pdfdesk.view import grid_from_settings
        snap, show, gx, gy = grid_from_settings(s)
        self.assertTrue(snap); self.assertFalse(show)
        self.assertAlmostEqual(gx, 10 * 72 / 25.4, places=3); self.assertAlmostEqual(gy, 5 * 72 / 25.4, places=3)
        s.remove("grid/snap"); s.remove("grid/unit"); s.remove("grid/x"); s.remove("grid/y")
        path = os.path.join(TMP, "gr.pdf"); pdf_with_images(path)
        w = MainWindow(); w.show(); self.assertTrue(w.open_path(path)); v = w.view
        v.set_grid(True, True, 20.0, 10.0)
        o = v.page_rects[0].topLeft()
        r = v._snap_move(QRectF(o.x() + 38, o.y() + 48, 50, 30), 0)           # sinistra 38 → 40; alto 48 → 50
        self.assertAlmostEqual(r.left() - o.x(), 40, places=3); self.assertAlmostEqual(r.top() - o.y(), 50, places=3)
        r2 = v._snap_resize(QRectF(o.x() + 33, o.y() + 47, 50, 30), "se", 0)  # spigolo basso-destro: 83→80, 77→80
        self.assertAlmostEqual(r2.right() - o.x(), 80, places=3); self.assertAlmostEqual(r2.bottom() - o.y(), 80, places=3)
        v.set_grid(False, False, 20.0, 10.0)
        r3 = QRectF(o.x() + 33, o.y() + 47, 50, 30)
        self.assertEqual(v._snap_move(r3, 0), r3)                              # senza aggancio nulla cambia
        from pdfdesk.dialogs import PreferencesDialog
        d = PreferencesDialog(None); d.grid_snap.setChecked(True); d.grid_x.setValue(12.5); d.grid_unit.setCurrentIndex(d.grid_unit.findData("pt")); d.store()
        self.assertTrue(w.a_gridsnap is not None)
        w.apply_prefs(); self.assertTrue(v.grid_snap); self.assertAlmostEqual(v.grid[0], 12.5, places=3)
        QSettings().clear()
        w.pdf.modified = False; w.close()

    def test_thumbs_follow_column_width(self):
        from PySide6.QtGui import QPixmap
        from pdfdesk.dialogs import ThumbPanel
        t = ThumbPanel(); t.resize(200, 400); t.show(); app.processEvents()
        t.set_count(3)
        for i in range(3):
            pm = QPixmap(300, 424); pm.fill(); t.set_thumb(i, pm)
        t.relayout(); w1 = t.iconSize().width()
        t.resize(360, 400); app.processEvents(); t.relayout(); w2 = t.iconSize().width()
        self.assertGreater(w2, w1)
        self.assertLessEqual(w2, t.viewport().width())
        self.assertLessEqual(abs(t.item(0).icon().actualSize(t.iconSize()).width() - t.iconSize().width()), 2)
        t.resize(2000, 400); t.relayout(); self.assertLessEqual(t.iconSize().width(), ThumbPanel.MAX_W)


class TextMoveKeepsStyleTests(unittest.TestCase):
    def test_move_keeps_font_size_color(self):
        d = fitz.open(); pg = d.new_page()
        pg.insert_text((72, 100), "Titolo grande", fontsize=22, fontname="hebo", color=(1, 0, 0))
        pg.insert_text((72, 300), "Corpo piccolo serif", fontsize=9.5, fontname="tiro")
        path = os.path.join(TMP, "tm.pdf"); d.save(path)
        p = PdfDocument.open(path)

        def spans():
            return sorted([(round(s["size"], 1), s["font"], s["text"], s["color"], round(s["origin"][0]), round(s["origin"][1]))
                           for b in p.doc[0].get_text("dict")["blocks"] if b["type"] == 0
                           for l in b["lines"] for s in l["spans"]], key=lambda x: x[5])
        before = spans()
        for pt in [(80, 95), (80, 297)]:
            o = p.content_at(0, pt)
            r = fitz.Rect(o["rect"])
            p.move_content(0, o, fitz.Rect(r.x0 + 100, r.y0 + 60, r.x1 + 150, r.y1 + 90))   # sposta e "ridimensiona"
        after = spans()
        self.assertEqual([a[:4] for a in after], [b[:4] for b in before])
        self.assertEqual([(a[4], a[5]) for a in after], [(172, 160), (172, 360)])
        p.undo(); p.undo()
        self.assertEqual(spans(), before)


class TextFlowSelectionTests(unittest.TestCase):
    def setUp(self):
        d = fitz.open(); pg = d.new_page()
        pg.insert_text((72, 100), "alfa beta gamma delta", fontsize=12)
        pg.insert_text((72, 120), "epsilon zeta eta theta", fontsize=12)
        pg.insert_text((72, 140), "iota kappa lambda mu", fontsize=12)
        self.path = os.path.join(TMP, "flow.pdf"); d.save(self.path)
        self.p = PdfDocument.open(self.path)

    def test_text_between_multiline(self):
        t = self.p.text_between(0, (130, 98), (110, 138))          # da "gamma" a "kappa"
        self.assertEqual(t, "gamma delta\nepsilon zeta eta theta\niota kappa")
        self.assertEqual(self.p.text_between(0, (110, 138), (130, 98)), t)   # direzione indifferente
        self.assertEqual(self.p.text_between(0, (80, 98), (90, 98)), "alfa")

    def test_markup_flow(self):
        n = len(list(self.p.doc[0].annots() or []))
        x = self.p.add_markup_flow(0, "hl", (130, 98), (110, 138))
        pg = self.p.doc[0]
        a = [a for a in pg.annots() if a.xref == x][0]
        self.assertEqual(len(a.vertices) // 4, 3)                              # una fascia per riga
        self.assertEqual(len(list(self.p.doc[0].annots())), n + 1)
        self.p.add_markup_flow(0, "ul", (80, 98), (90, 98)); self.p.add_markup_flow(0, "st", (80, 118), (90, 118))
        self.assertEqual(len(self.p.flow_rects(0, (130, 98), (110, 138))), 3)
        with self.assertRaises(Exception):
            e = PdfDocument(); e.doc.new_page(); e.add_markup_flow(0, "hl", (1, 1), (2, 2))


class ImagePropertiesTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        import io
        im = Image.new("RGBA", (80, 40), (255, 0, 0, 255)); im.paste((0, 0, 255, 255), (0, 0, 40, 40))
        b = io.BytesIO(); im.save(b, "PNG"); self.png = b.getvalue()
        d = fitz.open(); pg = d.new_page(); pg.insert_image(fitz.Rect(100, 100, 260, 180), stream=self.png)
        self.path = os.path.join(TMP, "imgp.pdf"); d.save(self.path)
        self.p = PdfDocument.open(self.path)

    def test_content_image_resize_rotate_replace_export(self):
        o = self.p.content_at(0, (150, 140)); self.assertEqual(o["kind"], "image")
        t = {"kind": "content", "obj": o}
        pix = self.p.image_pixmap_of(0, t); self.assertEqual((pix.width, pix.height), (80, 40))
        t2 = self.p.modify_image(0, t, fitz.Rect(100, 100, 200, 150))
        info = self.p.doc[0].get_image_info()[0]["bbox"]
        self.assertAlmostEqual(info[2] - info[0], 100, delta=1.5); self.assertAlmostEqual(info[3] - info[1], 50, delta=1.5)
        t3 = self.p.modify_image(0, t2, self.p.image_rect_of(0, t2), angle=90)
        b = self.p.doc[0].get_image_info()[0]["bbox"]
        self.assertAlmostEqual(b[2] - b[0], 50, delta=1.5); self.assertAlmostEqual(b[3] - b[1], 100, delta=1.5)
        from PIL import Image
        import io
        new = Image.new("RGB", (20, 20), (0, 255, 0)); bb = io.BytesIO(); new.save(bb, "PNG")
        self.p.modify_image(0, t3, self.p.image_rect_of(0, t3), replacement=bb.getvalue())
        t4 = {"kind": "content", "obj": self.p.content_at(0, (150, 150))}
        pix = self.p.image_pixmap_of(0, t4); self.assertEqual(pix.width, 20)
        for fmt in ("png", "jpg", "tiff"):
            out = os.path.join(TMP, "exp." + fmt); self.p.export_image_of(0, t4, out, fmt); self.assertTrue(os.path.getsize(out) > 100)
            self.assertEqual(Image.open(out).size, (20, 20))
        for _ in range(4): self.p.undo()
        self.assertEqual(self.p.image_pixmap_of(0, {"kind": "content", "obj": self.p.content_at(0, (150, 140))}).width, 80)

    def test_stamp_image(self):
        x = self.p.add_image(0, fitz.Rect(300, 300, 380, 340), self.png)
        t = {"kind": "annot", "xref": x}
        self.assertEqual(self.p.image_pixmap_of(0, t).width, 80)
        t2 = self.p.modify_image(0, t, fitz.Rect(300, 300, 400, 350), angle=45)
        r = self.p.image_rect_of(0, t2); self.assertGreater(r.width, 100)
        self.assertEqual(self.p.image_pixmap_of(0, t2).alpha, 1)
        self.p.undo(); self.assertAlmostEqual(self.p.image_rect_of(0, {"kind": "annot", "xref": x}).width, 80, delta=1)


class GroupingMultiTests(unittest.TestCase):
    def setUp(self):
        d = fitz.open(); pg = d.new_page()
        pg.insert_text((72, 100), "Blocco uno", fontsize=12)
        pg.draw_rect(fitz.Rect(300, 300, 360, 340), color=(1, 0, 0), fill=(0, 1, 0))
        self.path = os.path.join(TMP, "grp.pdf"); d.save(self.path)
        self.p = PdfDocument.open(self.path)

    def test_group_move_ungroup_undo(self):
        a = self.p.add_shape(0, "rect", fitz.Rect(100, 200, 160, 240), (1, 0, 0), None, 2, 1.0)
        b = self.p.add_shape(0, "ellipse", fitz.Rect(200, 200, 260, 240), (0, 0, 1), None, 2, 1.0)
        self.p.group_annots(0, [a, b])
        self.assertEqual(sorted(self.p.annot_group(0, a)), sorted([a, b]))
        n0 = len(self.p._undo)
        with self.p.batch("sposta"):
            for x in self.p.annot_group(0, a):
                r = self.p.annot_info(0, x).rect
                self.p.set_rect(0, x, fitz.Rect(r) + (50, 0, 50, 0))
        self.assertEqual(len(self.p._undo), n0 + 1)                     # un solo passo di annulla
        self.assertEqual(len(self.p.annot_group(0, a)), 2)
        self.p.undo()
        self.assertAlmostEqual(self.p.annot_info(0, a).rect.x0, 100, delta=1)
        self.assertEqual(self.p.ungroup_annots(0, [a]), 2)
        self.assertEqual(self.p.annot_group(0, a), [a])
        with self.assertRaises(Exception):
            self.p.group_annots(0, [a])

    def test_objects_in_rect_and_image_to_stamp(self):
        objs = self.p.objects_in_rect(0, fitz.Rect(0, 0, 400, 400))
        kinds = sorted(o["obj"]["kind"] for o in objs if o["kind"] == "content")
        self.assertEqual(kinds, ["text", "vector"])
        self.assertEqual(self.p.objects_in_rect(0, fitz.Rect(500, 500, 590, 590)), [])
        from PIL import Image
        import io
        b = io.BytesIO(); Image.new("RGB", (30, 30), (0, 0, 255)).save(b, "PNG")
        d = fitz.open(); pg = d.new_page(); pg.insert_image(fitz.Rect(100, 100, 160, 160), stream=b.getvalue()); pp = os.path.join(TMP, "i2.pdf"); d.save(pp)
        q = PdfDocument.open(pp); o = q.content_at(0, (120, 120))
        x = q.content_image_to_stamp(0, o)
        self.assertIsNone(q.content_at(0, (120, 120)))
        self.assertAlmostEqual(q.annot_info(0, x).rect.width, 60, delta=1)


class HighlightToggleTests(unittest.TestCase):
    def _doc(self):
        from pdfdesk.core import PdfDocument
        d = fitz.open(); pg = d.new_page(); pg.insert_text((72, 100), "alfa beta gamma delta", fontsize=14)
        path = os.path.join(TMP, "hlt.pdf"); d.save(path)
        return PdfDocument.open(path)

    def _hl(self, doc):
        return [(a.colors["stroke"], len(a.vertices) // 4) for a in doc.doc[0].annots() if a.type[0] == fitz.PDF_ANNOT_HIGHLIGHT]

    def test_same_colour_toggles_off_and_other_colour_replaces(self):
        d = self._doc(); full = fitz.Rect(60, 80, 300, 110)
        d.add_markup(0, "hl", full, (1, 1, 0))
        self.assertEqual(self._hl(d), [([1.0, 1.0, 0.0], 4)])
        d.add_markup(0, "hl", full, (1, 1, 0))                         # stesso colore: toggle
        self.assertEqual(self._hl(d), [])
        d.undo(); self.assertEqual(len(self._hl(d)), 1)                  # annullabile
        d.add_markup(0, "hl", full, (0, 1, 0))                         # altro colore: sostituisce
        self.assertEqual(self._hl(d), [([0.0, 1.0, 0.0], 4)])

    def test_partial_overlap_keeps_rest(self):
        d = self._doc()
        d.add_markup(0, "hl", fitz.Rect(60, 80, 300, 110), (1, 1, 0))
        words = d.doc[0].get_text("words"); b = fitz.Rect(words[1][:4])
        d.add_markup(0, "hl", b + (-1, -1, 1, 1), (1, 1, 0))             # togli solo la seconda parola
        self.assertEqual(self._hl(d), [([1.0, 1.0, 0.0], 3)])
        d.add_markup(0, "hl", b + (-1, -1, 1, 1), (1, 0, 0))             # la riprende con un altro colore
        cols = sorted(c[0] for c in self._hl(d))
        self.assertEqual(cols, [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0]])


class SignatureTransparencyTests(unittest.TestCase):
    def test_import_keeps_existing_transparency(self):
        from PySide6.QtGui import QImage, QPainter, QPen, QColor
        from PySide6.QtCore import Qt
        from pdfdesk import sigstore
        img = QImage(300, 100, QImage.Format_ARGB32); img.fill(Qt.transparent)
        p = QPainter(img); p.setPen(QPen(QColor(10, 20, 120), 4)); p.drawLine(10, 80, 150, 20); p.end()
        self.assertTrue(sigstore.has_transparency(img))
        out = sigstore.remove_background(img)
        self.assertEqual(out.pixel(1, 1) >> 24, 0)                    # lo sfondo resta trasparente (non nero opaco)
        opaque = QImage(50, 50, QImage.Format_RGB32); opaque.fill(Qt.white)
        self.assertFalse(sigstore.has_transparency(opaque))


class ExportLayoutTests(unittest.TestCase):
    def _pdf(self):
        d = fitz.open(); p = d.new_page()
        p.insert_text((72, 80), "Titolo", fontsize=22)
        p.insert_text((300, 400), "Colonna destra", fontsize=11)
        p.draw_rect(fitz.Rect(72, 300, 540, 360), color=(0, 0, 0.6), fill=(0.9, 0.9, 1))
        d.new_page().insert_text((72, 100), "Seconda", fontsize=14)
        path = os.path.join(TMP, "lay.pdf"); d.save(path)
        return fitz.open(path)

    def test_docx_odt_keep_positions_and_text(self):
        import zipfile
        from pdfdesk import export
        d = self._pdf()
        for fmt, part in (("docx", "word/document.xml"), ("odt", "content.xml")):
            out = os.path.join(TMP, "lay." + fmt)
            export.export(d, fmt, [0, 1], out)
            xml = zipfile.ZipFile(out).read(part).decode()
            self.assertIn("Titolo", xml); self.assertIn("Colonna destra", xml); self.assertIn("Seconda", xml)
        import docx, odf.opendocument as od
        docx.Document(os.path.join(TMP, "lay.docx")); od.load(os.path.join(TMP, "lay.odt"))     # file validi
        # posizione del riquadro "Colonna destra": x=300pt → 3810000 EMU nel DOCX, 300pt nell'ODT
        self.assertIn("<wp:posOffset>3810000</wp:posOffset>", zipfile.ZipFile(os.path.join(TMP, "lay.docx")).read("word/document.xml").decode())
        self.assertIn('svg:x="300.00pt"', zipfile.ZipFile(os.path.join(TMP, "lay.odt")).read("content.xml").decode())

    def test_text_keeps_columns_and_flow_mode_still_available(self):
        from pdfdesk import export
        d = self._pdf()
        out = os.path.join(TMP, "lay.txt")
        export.export(d, "txt", [0], out)
        lines = open(out, encoding="utf-8").read().split("\n")
        col = [l for l in lines if "Colonna destra" in l][0]
        self.assertGreater(col.index("Colonna destra"), 10)             # rientro mantenuto
        export.export(d, "txt", [0], out, keep_layout=False)
        self.assertIn("Colonna destra", open(out, encoding="utf-8").read())
        export.export(d, "docx", [0], os.path.join(TMP, "flow.docx"), keep_layout=False)


class UpdaterTests(unittest.TestCase):
    def test_version_compare(self):
        from pdfdesk import updater
        self.assertTrue(updater.is_newer("0.7.4", "0.7.3"))
        self.assertTrue(updater.is_newer("v0.10.0", "0.9.9"))
        self.assertTrue(updater.is_newer("1.0", "0.9.9"))
        self.assertFalse(updater.is_newer("0.7.3", "0.7.3"))
        self.assertFalse(updater.is_newer("0.7", "0.7.0"))
        self.assertFalse(updater.is_newer("0.6.9", "0.7.0"))
        self.assertFalse(updater.is_newer("", "0.7.0"))
        self.assertFalse(updater.is_newer("abc", "0.7.0"))

    def test_fetch_latest_parses_github_json(self):
        import json, threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from pdfdesk import updater

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"tag_name": "v9.9.9", "html_url": "https://example.org/r", "body": "note"}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def log_message(self, *a): pass
        srv = HTTPServer(("127.0.0.1", 0), H)
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            r = updater.fetch_latest(url=f"http://127.0.0.1:{srv.server_port}/x")
        finally:
            srv.shutdown()
        self.assertEqual(r, {"version": "9.9.9", "url": "https://example.org/r", "notes": "note"})


class CommentAndTextStyleCoreTests(unittest.TestCase):
    def setUp(self):
        self.d = PdfDocument.open(SRC)

    def test_comment_roundtrip(self):
        x = self.d.add_comment(0, (100, 200), "Ciao")
        inf = self.d.annot_info(0, x)
        self.assertEqual((inf.type, inf.text, inf.movable, inf.resizable), (0, "Ciao", True, False))
        nx = self.d.set_rect(0, x, fitz.Rect(150, 250, 400, 400))
        r = self.d.annot_info(0, nx).rect
        self.assertAlmostEqual(r.width, inf.rect.width, places=1)           # l'icona non si ridimensiona
        self.d.set_props(0, nx, text="Nuovo")
        out = os.path.join(tempfile.mkdtemp(), "c.pdf"); self.d.doc.save(out)
        doc = fitz.open(out); pg = doc[0]
        a = list(pg.annots())[0]
        self.assertEqual((a.type[1], a.info["content"]), ("Text", "Nuovo"))

    def test_text_styles_persist_and_render(self):
        base = self.d.add_text(0, fitz.Rect(50, 400, 350, 440), "Testo di prova", 14, "helv", (0, 0, 0), None, 0, "")
        sty = self.d.add_text(0, fitz.Rect(50, 450, 350, 490), "Testo di prova", 14, "tiro", (0, 0, 0), None, 0, "bus")
        self.assertEqual(self.d.annot_info(0, sty).style, "bus")
        self.assertEqual(self.d.annot_info(0, base).style, "")
        nx = self.d.set_props(0, base, style="u")
        self.assertEqual(self.d.annot_info(0, nx).style, "u")
        nx = self.d.set_rect(0, nx, fitz.Rect(60, 400, 400, 460))           # ridimensionato: l'aspetto si rigenera con lo stile
        self.assertEqual(self.d.annot_info(0, nx).style, "u")
        out = os.path.join(tempfile.mkdtemp(), "s.pdf"); self.d.doc.save(out)
        r = fitz.open(out); rp = r[0]
        self.assertEqual(len(list(rp.annots())), 2)
        # sottolineato/barrato disegnano davvero una riga nell'aspetto
        plain = self.d.add_text(0, fitz.Rect(50, 500, 350, 540), "Riga", 14, "helv", (0, 0, 0), None, 0, "")
        under = self.d.add_text(0, fitz.Rect(50, 550, 350, 590), "Riga", 14, "helv", (0, 0, 0), None, 0, "u")
        pm1 = self.d.doc[0].get_pixmap(clip=fitz.Rect(50, 500, 350, 540), dpi=100)
        pm2 = self.d.doc[0].get_pixmap(clip=fitz.Rect(50, 550, 350, 590), dpi=100)
        dark = lambda pm: sum(1 for i in range(0, len(pm.samples), pm.n) if pm.samples[i] < 100)
        self.assertGreater(dark(pm2), dark(pm1))

    def test_replace_text_block_with_styles(self):
        blk = self.d.text_block_at(0, (100, 100))
        self.d.replace_text_block(0, blk["rect"], "Nuovo titolo", 16, "helv", (0, 0, 0), None, "b")
        names = [f[3] for f in self.d.doc[0].get_fonts()]
        self.assertTrue(any("Bold" in n or "bo" in n.lower() for n in names), names)
        blk = self.d.text_block_at(0, (100, 100))
        n0 = len(self.d.doc[0].get_drawings())
        self.d.replace_text_block(0, blk["rect"], "Nuovo titolo", 16, "helv", (0, 0, 0), None, "us")
        self.assertGreater(len(self.d.doc[0].get_drawings()), n0)             # righe di sottolineato e barrato


class SigningPackagingTests(unittest.TestCase):
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_certificate_is_code_signing(self):
        from cryptography import x509
        from cryptography.x509.oid import ExtendedKeyUsageOID
        with open(os.path.join(self.ROOT, "packaging", "windows", "pdfdesk-sign.cer"), "rb") as f:
            c = x509.load_der_x509_certificate(f.read())
        self.assertIn("PDFDesk", c.subject.rfc4514_string())
        self.assertIn(ExtendedKeyUsageOID.CODE_SIGNING, c.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
        self.assertFalse(c.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)

    def test_mac_unlock_script(self):
        p = os.path.join(self.ROOT, "packaging", "macos", "sblocca.sh")
        txt = open(p, encoding="utf-8").read()
        self.assertIn("xattr -cr", txt)
        self.assertTrue(os.access(p, os.X_OK))

    def test_installer_has_certificate_section_and_no_private_key_in_sources(self):
        nsi = open(os.path.join(self.ROOT, "packaging", "windows", "pdfdesk.nsi"), encoding="utf-8").read()
        for k in ("SecCert", "pdfdesk-sign.cer", "TrustedPublisher", "/CERT"):
            self.assertIn(k, nsi)
        self.assertIn("pdfdesk-sign.key", open(os.path.join(self.ROOT, ".gitignore")).read())
        self.assertIn("pdfdesk-sign.key", open(os.path.join(self.ROOT, "make_sources.sh")).read())


class ParallelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        d = fitz.open()
        for i in range(40):
            p = d.new_page()
            for k in range(12):
                p.insert_text((50, 60 + k * 16), f"Pagina {i + 1} riga {k} àèì parola{i}", fontsize=11)
        cls.doc = d

    def setUp(self):
        self._e = os.environ.pop("PDFDESK_CORES", None)

    def tearDown(self):
        os.environ.pop("PDFDESK_CORES", None)
        if self._e is not None:
            os.environ["PDFDESK_CORES"] = self._e

    def test_plan(self):
        from pdfdesk import parallel
        n = parallel.cpu_total()
        os.environ["PDFDESK_CORES"] = "1"
        self.assertEqual(parallel.plan(500), 1)
        os.environ["PDFDESK_CORES"] = str(n)
        self.assertEqual(parallel.plan(3), 1)                      # poche pagine: seriale
        self.assertEqual(parallel.plan(500, 10 ** 12), 1)          # file enorme: un solo processo
        self.assertLessEqual(parallel.plan(500), n)
        os.environ.pop("PDFDESK_CORES")
        self.assertEqual(parallel.max_workers(), max(1, n - 1))   # automatico: n-1
        parallel.set_cores(2)
        self.assertEqual(parallel.max_workers(), min(2, n))
        parallel.set_cores(0)

    def test_parallel_equals_serial(self):
        from pdfdesk import export, parallel
        if parallel.cpu_total() < 2:
            self.skipTest("serve almeno 2 processori")
        import hashlib
        out = {}
        for c in ("1", "2"):
            os.environ["PDFDESK_CORES"] = c
            files = export.export_images(self.doc, list(range(40)), "png", os.path.join(self.tmp, "o" + c), dpi=72)
            out[c] = [hashlib.md5(open(f, "rb").read()).hexdigest() for f in files]
        self.assertEqual(len(out["1"]), 40)
        self.assertEqual(out["1"], out["2"])
        t = {}
        for c in ("1", "2"):
            os.environ["PDFDESK_CORES"] = c
            f = os.path.join(self.tmp, f"t{c}.txt"); export.export_text(self.doc, list(range(40)), f)
            t[c] = open(f, encoding="utf-8").read()
        self.assertEqual(t["1"], t["2"])
        self.assertIn("parola39", t["2"])

    def test_cancel_cleans_up(self):
        from pdfdesk import export, parallel
        if parallel.cpu_total() < 2:
            self.skipTest("serve almeno 2 processori")
        os.environ["PDFDESK_CORES"] = "2"
        before = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("pdfdesk-par-")}
        with self.assertRaises(export.Cancelled):
            export.export_images(self.doc, list(range(40)), "png", os.path.join(self.tmp, "c"), dpi=72, progress=lambda i, n: i < 1)
        after = {d for d in os.listdir(tempfile.gettempdir()) if d.startswith("pdfdesk-par-")}
        self.assertEqual(after - before, set())

    def test_search_many_pages(self):
        from pdfdesk import parallel
        from pdfdesk.core import PdfDocument
        if parallel.cpu_total() < 2:
            self.skipTest("serve almeno 2 processori")
        d = fitz.open()
        for i in range(210):
            d.new_page().insert_text((50, 80), f"foglio {i} trovami{i % 7}", fontsize=12)
        p = os.path.join(self.tmp, "long.pdf"); d.save(p)
        pdf = PdfDocument.open(p)
        os.environ["PDFDESK_CORES"] = "2"
        par = pdf.search("trovami3")
        os.environ["PDFDESK_CORES"] = "1"
        ser = pdf.search("trovami3")
        self.assertEqual(len(par), 30)
        self.assertEqual([(a, tuple(r)) for a, r in par], [(a, tuple(r)) for a, r in ser])
        pdf.close()


class OcrDownloadTests(unittest.TestCase):
    """Tesseract: percorsi di ricerca, percorso scelto dall'utente, download con controllo SHA-256, installatore."""

    def setUp(self):
        from pdfdesk import scan
        self.scan = scan; self.tmp = tempfile.mkdtemp(prefix="ocr-")
        self.addCleanup(scan.set_tesseract_path, "")
        self._which = scan.shutil.which; scan.shutil.which = lambda n: None
        self.addCleanup(setattr, scan.shutil, "which", self._which)

    def _fake(self, d):
        os.makedirs(d, exist_ok=True); p = os.path.join(d, self.scan._tess_exe()); open(p, "w").write("x"); return p

    def test_pins(self):
        import re
        self.assertRegex(self.scan.TESSERACT_SHA256, r"^[0-9a-f]{64}$")
        self.assertTrue(self.scan.TESSERACT_URL.startswith("https://"))
        self.assertIn(self.scan.TESSERACT_VERSION, self.scan.TESSERACT_URL)

    def test_user_path_file_or_folder(self):
        p = self._fake(os.path.join(self.tmp, "t"))
        self.scan.set_tesseract_path(p); self.assertEqual(self.scan.tesseract_path(), p)
        self.scan.set_tesseract_path(os.path.dirname(p)); self.assertEqual(self.scan.tesseract_path(), p)
        self.scan.set_tesseract_path(os.path.join(self.tmp, "nonesiste")); self.assertIsNone(self.scan.tesseract_path())

    def test_auto_search_dirs(self):
        p = self._fake(os.path.join(self.tmp, "auto"))
        self.addCleanup(setattr, self.scan, "ocr_search_dirs", self.scan.ocr_search_dirs)
        self.scan.ocr_search_dirs = lambda: [os.path.join(self.tmp, "vuota"), os.path.dirname(p)]
        self.assertEqual(self.scan.find_tesseract(), p); self.assertEqual(self.scan.tesseract_path(), p)

    def test_download_sha256(self):
        import hashlib
        src = os.path.join(self.tmp, "a.bin"); open(src, "wb").write(b"dati" * 5000)
        url = "file://" + src; ok = hashlib.sha256(b"dati" * 5000).hexdigest()
        dst = os.path.join(self.tmp, "b.bin"); seen = []
        self.scan._download(url, dst, lambda a, b: seen.append((a, b)) or True, ok)
        self.assertEqual(os.path.getsize(dst), 20000); self.assertTrue(seen)
        bad = os.path.join(self.tmp, "c.bin")
        with self.assertRaises(self.scan.ScanError):
            self.scan._download(url, bad, None, "0" * 64)
        self.assertFalse(os.path.exists(bad))                      # file con hash errato: cancellato
        with self.assertRaises(self.scan.ScanError):
            self.scan._download(url, bad, lambda a, b: False)      # annullato dall'utente
        self.assertFalse(os.path.exists(bad))
        with self.assertRaises(self.scan.ScanError):
            self.scan._download("file://" + os.path.join(self.tmp, "assente"), bad)

    def test_install_only_windows_and_hint(self):
        if sys.platform != "win32":
            with self.assertRaises(self.scan.ScanError):
                self.scan.install_tesseract(os.path.join(self.tmp, "x"))
        self.assertTrue(self.scan.ocr_hint())

    def test_install_hash_mismatch_stops_before_running(self):
        """Con hash non corrispondente l'installer scaricato non viene eseguito."""
        import unittest.mock as m
        src = os.path.join(self.tmp, "setup.exe"); open(src, "wb").write(b"MZfinto")
        with m.patch.object(self.scan.sys, "platform", "win32"), m.patch.object(self.scan, "TESSERACT_URL", "file://" + src), \
                m.patch.object(self.scan.subprocess, "run") as run:
            with self.assertRaises(self.scan.ScanError):
                self.scan.install_tesseract(os.path.join(self.tmp, "dest"))
            run.assert_not_called()

    def test_installer_and_cli_hooks(self):
        nsi = open(os.path.join(os.path.dirname(__file__), "..", "packaging", "windows", "pdfdesk.nsi"), encoding="utf-8").read()
        for needle in ('Section "$(SEC_OCR)" SecOcr', "--install-ocr", '"/OCR"', "OcrInstalled"):
            self.assertIn(needle, nsi)
        from pdfdesk import cli
        if sys.platform != "win32":
            self.assertEqual(cli.main(["--install-ocr", os.path.join(self.tmp, "d")]), 1)     # fuori da Windows: errore con il comando da usare

    def test_wia_script_no_case_insensitive_clash(self):
        """PowerShell non distingue maiuscole/minuscole: una variabile con lo stesso nome di un parametro tipizzato ne eredita il tipo
        (bug 0.7.8: «$dev = $info.Connect()» sovrascriveva il parametro [string] -Dev e l'oggetto diventava testo/null)."""
        import re
        sc = self.scan._WIA_SCAN
        params = [x.lower() for x in re.findall(r"\[\w+\]\$(\w+)", sc.split("\n")[1])]
        assigned = [x.lower() for x in re.findall(r"^\s*\$(\w+)\s*=", sc, re.M)]
        self.assertEqual(set(params) & set(assigned), set())
        self.assertIn("-DevId", open(self.scan.__file__, encoding="utf-8").read())

    def test_preferences_has_ocr_path(self):
        d = dialogs.PreferencesDialog(None); self.assertTrue(hasattr(d, "ocr_path")); d.ocr_path.setText(self.tmp); d.store()
        from pdfdesk.mainwindow import settings
        self.assertEqual(str(settings().value("ocr/path", "")), self.tmp)
        d.ocr_path.clear(); d.store(); d.close()


if __name__ == "__main__":
    unittest.main()
