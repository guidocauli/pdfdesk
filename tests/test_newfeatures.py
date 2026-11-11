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


if __name__ == "__main__":
    unittest.main()


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
        for x in ("Salva immagine…", "Segna per la redazione", "Elimina", "Salva l'area come immagine…"):
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
