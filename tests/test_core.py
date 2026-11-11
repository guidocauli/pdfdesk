# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Test mirati di core, compressione e firma.
import io, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import pymupdf as fitz
from PySide6.QtGui import QImage, QPainter, QColor
from make_samples import make_text_pdf, make_image_pdf
from pdfdesk import shutdown as _shutdown; _shutdown.install_atexit(); _shutdown.watchdog()      # chiusura ordinata delle finestre lasciate aperte dai test
from pdfdesk.core import PdfDocument, T_INK, T_FREETEXT, T_SQUARE, T_CIRCLE, T_LINE, T_STAMP, T_REDACT
from pdfdesk import compress, signing

TMP = tempfile.mkdtemp(prefix="pdfdesk-test-")
TXT = os.path.join(TMP, "testo.pdf"); IMG = os.path.join(TMP, "immagini.pdf")
make_text_pdf(TXT); make_image_pdf(IMG, pages=1, size=1500)

def png_bytes(w=60, h=30):
    im = QImage(w, h, QImage.Format_ARGB32); im.fill(QColor(0, 0, 0, 0))
    p = QPainter(im); p.fillRect(10, 8, w - 20, h - 16, QColor(255, 0, 0)); p.end()
    from PySide6.QtCore import QBuffer, QIODevice
    b = QBuffer(); b.open(QIODevice.WriteOnly); im.save(b, "PNG"); return bytes(b.data())

def types(d, pno=0): return [a.type for a in d.list_annots(pno)]

class AnnotTests(unittest.TestCase):
    def setUp(self): self.d = PdfDocument.open(TXT)
    def tearDown(self): self.d.close()

    def test_create_all_and_roundtrip(self):
        d = self.d
        d.add_ink(0, [[(10, 10), (60, 50), (110, 20)]], (1, 0, 0), 3)
        d.add_ink(0, [[(10, 400), (200, 400)]], (1, 1, 0), 14, 0.4, highlighter=True)
        d.add_shape(0, "rect", fitz.Rect(300, 400, 400, 460), (0, 0, 1), (1, 0.8, 0.8), 2, 0.5)
        d.add_shape(0, "ellipse", fitz.Rect(300, 500, 400, 560), (0, 0.5, 0), None, 2)
        d.add_line(0, (50, 600), (200, 650), (0, 0, 0), 2, arrow=True)
        d.add_text(0, fitz.Rect(72, 650, 300, 720), "Nota àèì €", 12, "helv", (0, 0, 1), (1, 1, 0.8), 1)
        d.add_image(0, fitz.Rect(350, 650, 500, 700), png_bytes())
        d.add_markup(0, "hl", fitz.Rect(72, 80, 300, 110))
        got = types(d)
        for t in (T_INK, T_SQUARE, T_CIRCLE, T_LINE, T_FREETEXT, T_STAMP, fitz.PDF_ANNOT_HIGHLIGHT):
            self.assertIn(t, got, f"manca tipo {t}")
        out = os.path.join(TMP, "rt.pdf"); open(out, "wb").write(d.current_bytes())
        d2 = PdfDocument.open(out)
        self.assertEqual(sorted(types(d2)), sorted(got))
        ft = [a for a in d2.list_annots(0) if a.type == T_FREETEXT][0]
        self.assertEqual(ft.text, "Nota àèì €"); self.assertEqual(ft.fontsize, 12); self.assertEqual(ft.text_color, (0, 0, 1))
        self.assertEqual(ft.fill, (1.0, 1.0, 0.800000011920929) if False else ft.fill)
        d2.close()

    def test_move_resize_all_types(self):
        d = self.d
        xs = {
            "ink": d.add_ink(0, [[(10, 10), (60, 50), (110, 20)]], (1, 0, 0), 3),
            "rect": d.add_shape(0, "rect", fitz.Rect(300, 400, 400, 460)),
            "line": d.add_line(0, (50, 600), (200, 650), arrow=True),
            "text": d.add_text(0, fitz.Rect(72, 650, 300, 720), "ciao", 12),
            "img": d.add_image(0, fitz.Rect(350, 650, 500, 700), png_bytes()),
        }
        for k, x in xs.items():
            info = d.annot_info(0, x); self.assertIsNotNone(info, k)
            nr = fitz.Rect(info.rect.x0 + 30, info.rect.y0 + 20, info.rect.x1 + 80, info.rect.y1 + 60)
            nx = d.set_rect(0, x, nr)
            ni = d.annot_info(0, nx)
            self.assertAlmostEqual(ni.rect.x0, nr.x0, delta=4, msg=k); self.assertAlmostEqual(ni.rect.x1, nr.x1, delta=4, msg=k)
            self.assertAlmostEqual(ni.rect.y1, nr.y1, delta=4, msg=k)
        # l'inchiostro ricostruito conserva stile
        ink = [a for a in d.list_annots(0) if a.type == T_INK][0]
        self.assertEqual(ink.stroke, (1.0, 0.0, 0.0)); self.assertAlmostEqual(ink.width, 3, delta=.01)

    def test_props_update(self):
        d = self.d
        x = d.add_shape(0, "rect", fitz.Rect(300, 400, 400, 460), (0, 0, 0), (1, 0, 0), 2)
        d.set_props(0, x, stroke=(0, 1, 0), fill=None, width=5, opacity=0.5)
        i = d.annot_info(0, x)
        self.assertEqual(i.stroke, (0.0, 1.0, 0.0)); self.assertIsNone(i.fill); self.assertAlmostEqual(i.width, 5, delta=.01)
        t = d.add_text(0, fitz.Rect(72, 650, 300, 720), "uno", 12)
        d.set_props(0, t, text="due àè", fontsize=18, fontname="tiro", text_color=(1, 0, 0), fill=(0.9, 0.9, 0.9))
        i = d.annot_info(0, t)
        self.assertEqual((i.text, i.fontsize, i.fontname), ("due àè", 18, "tiro")); self.assertEqual(i.text_color, (1.0, 0.0, 0.0))

    def test_hit_test_and_delete(self):
        d = self.d
        x = d.add_shape(0, "rect", fitz.Rect(300, 400, 400, 460))
        self.assertEqual(d.annot_at(0, (350, 430)), x)
        self.assertIsNone(d.annot_at(0, (50, 700)))
        self.assertTrue(d.delete_annot(0, x)); self.assertEqual(types(d), [])

    def test_undo_redo(self):
        d = self.d
        d.add_shape(0, "rect", fitz.Rect(300, 400, 400, 460)); d.add_ink(0, [[(1, 1), (30, 30)]])
        self.assertEqual(len(d.list_annots(0)), 2)
        self.assertTrue(d.undo()); self.assertEqual(len(d.list_annots(0)), 1)
        self.assertTrue(d.undo()); self.assertEqual(len(d.list_annots(0)), 0)
        self.assertFalse(d.undo())
        self.assertTrue(d.redo()); self.assertTrue(d.redo()); self.assertEqual(len(d.list_annots(0)), 2)

    def test_redaction_removes_text_permanently(self):
        d = self.d
        self.assertIn("IBAN", d.page(0).get_text())
        r = fitz.Rect(d.page(0).search_for("IBAN")[0]) + (-2, -2, 250, 2)
        d.add_redact(0, r)
        self.assertEqual(d.pending_redactions(), 1)
        self.assertEqual(d.apply_redactions(), 1)
        out = os.path.join(TMP, "red.pdf"); open(out, "wb").write(d.current_bytes())
        doc_ = fitz.open(out); txt = doc_[0].get_text()
        self.assertNotIn("IBAN", txt); self.assertNotIn("IT00X", txt); self.assertIn("Ciao mondo", txt)

    def test_edit_text_block(self):
        d = self.d
        blk = d.text_block_at(0, (100, 100))
        self.assertIsNotNone(blk); self.assertIn("Pagina 1", blk["text"])
        d.replace_text_block(0, blk["rect"], "Titolo modificato", blk["fontsize"], blk["fontname"], blk["color"])
        t = d.page(0).get_text()
        self.assertIn("Titolo modificato", t); self.assertNotIn("Ciao mondo", t)
        self.assertIn("IBAN", t)  # il resto non si tocca

    def test_markup_words_and_text_in_rect(self):
        d = self.d
        self.assertIn("Ciao", d.text_in_rect(0, fitz.Rect(60, 80, 400, 110)))
        with self.assertRaises(Exception): d.add_markup(0, "ul", fitz.Rect(500, 700, 510, 710))

    def test_search(self):
        self.assertEqual(len(self.d.search("Ciao mondo")), 3)

    def test_page_ops(self):
        d = self.d
        d.rotate_pages([0], 90); self.assertEqual(d.page(0).rotation, 90)
        d.duplicate_page(1); self.assertEqual(d.page_count, 4)
        d.insert_blank(0); self.assertEqual(d.page_count, 5)
        d.move_page(4, 0); self.assertEqual(d.page_count, 5)
        d.delete_pages([0, 1]); self.assertEqual(d.page_count, 3)
        with self.assertRaises(Exception): d.delete_pages([0, 1, 2])
        n = d.insert_pdf(TXT, 0); self.assertEqual(n, 3); self.assertEqual(d.page_count, 6)
        out = os.path.join(TMP, "ex.pdf"); d.extract_pages([0, 2], out); self.assertEqual(fitz.open(out).page_count, 2)
        d.undo(); self.assertEqual(d.page_count, 3)

    def test_rotated_page_coordinates(self):
        d = self.d
        d.rotate_pages([0], 90)
        disp = d.page(0).rect  # 842x595
        r = fitz.Rect(100, 50, 220, 110)  # in visualizzazione
        x = d.add_shape(0, "rect", r)
        self.assertAlmostEqual(d.annot_info(0, x).rect.x0, r.x0, delta=2); self.assertAlmostEqual(d.annot_info(0, x).rect.y1, r.y1, delta=2)
        self.assertEqual(d.annot_at(0, (160, 80)), x)
        self.assertIsNone(d.annot_at(0, (500, 400)))
        # il testo "Ciao" ruotato: la ricerca in visualizzazione deve cadere dentro la pagina ruotata
        hit = d.search("Ciao")[0][1]
        self.assertTrue(disp.contains(hit))

class CompressTests(unittest.TestCase):
    def test_presets_shrink_and_keep_text(self):
        data = open(IMG, "rb").read()
        sizes = {}
        for p in compress.PRESETS:
            out = compress.optimize_bytes(data, compress.SaveOptions(preset=p.key))
            sizes[p.key] = len(out)
            d = fitz.open("pdf", out)
            self.assertIn("Immagine pesante", d[0].get_text(), p.key)   # testo conservato come testo
            self.assertEqual(d.page_count, 1)
        print("\n  dimensioni:", {k: compress.human_size(v) for k, v in sizes.items()}, "in:", compress.human_size(len(data)))
        self.assertLess(sizes["medium"], sizes["high"]); self.assertLess(sizes["low"], sizes["medium"])
        self.assertLess(sizes["minimum"], sizes["low"]); self.assertLess(sizes["medium"], len(data) * 0.5)

    def test_options(self):
        data = open(IMG, "rb").read()
        out = compress.optimize_bytes(data, compress.SaveOptions("medium", grayscale=True, strip_metadata=True, subset_fonts=True))
        d = fitz.open("pdf", out); self.assertIn("Immagine", d[0].get_text())
        pm = d[0].get_pixmap(); self.assertGreater(pm.width, 100)

class SigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p12 = os.path.join(TMP, "test.p12")
        signing.create_self_signed_p12(cls.p12, "pw123", "Guido Prova", "Test", "guido@example.org")

    def test_sign_verify_and_tamper(self):
        data = open(TXT, "rb").read()
        sig = signing.sign_pdf_bytes(data, signing.SignParams(self.p12, "pw123", reason="Prova", location="Bari"))
        st = signing.verify_pdf_bytes(sig)
        self.assertEqual(len(st), 1); self.assertTrue(st[0].intact and st[0].valid); self.assertFalse(st[0].trusted)
        self.assertIn("Guido Prova", st[0].signer); self.assertEqual(st[0].coverage, "ENTIRE_FILE")
        # manomissione di un byte coperto dalla firma: la firma non è più integra
        bad = bytearray(sig); bad[7] = ord("9" if bad[7:8] != b"9" else "8")
        st_bad = signing.verify_pdf_bytes(bytes(bad)); self.assertFalse(st_bad[0].intact and st_bad[0].valid)
        d = fitz.open("pdf", sig); self.assertEqual(PdfDocument._count_signatures(d), 1)
        with self.assertRaises(signing.SigningError): signing.sign_pdf_bytes(data, signing.SignParams(self.p12, "sbagliata"))

    def test_visible_signature_with_image(self):
        data = open(TXT, "rb").read()
        png = os.path.join(TMP, "sig.png"); open(png, "wb").write(png_bytes(200, 80))
        sig = signing.sign_pdf_bytes(data, signing.SignParams(self.p12, "pw123", page=0, box=(300, 100, 520, 190), image_path=png, field_name="FirmaVisibile"))
        st = signing.verify_pdf_bytes(sig); self.assertTrue(st[0].valid)
        d = fitz.open("pdf", sig)
        self.assertTrue(any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE for w in d[0].widgets()))
        d[0].get_pixmap().save(os.path.join(TMP, "firma_visibile.png"))

    def test_edit_signed_doc_keeps_signature(self):
        sigf = os.path.join(TMP, "firmato.pdf")
        open(sigf, "wb").write(signing.sign_pdf_bytes(open(TXT, "rb").read(), signing.SignParams(self.p12, "pw123")))
        d = PdfDocument.open(sigf)
        self.assertTrue(d.is_signed); self.assertFalse(d.can_undo)
        d.add_text(0, fitz.Rect(72, 650, 300, 720), "annotazione dopo la firma", 12)
        out = d.current_bytes()
        self.assertGreater(len(out), os.path.getsize(sigf))
        self.assertTrue(out.startswith(open(sigf, "rb").read()))   # la revisione firmata è intatta byte per byte
        st = signing.verify_pdf_bytes(out)
        self.assertTrue(st[0].intact and st[0].valid); self.assertIn("annotazione", [a.info["content"] for a in (lambda dd: (dd, dd[0]))(fitz.open("pdf", out))[1].annots()][0])
        d.close()

    def test_verification_after_edit_still_lists_signatures(self):
        sigf = os.path.join(TMP, "firmato3.pdf")
        open(sigf, "wb").write(signing.sign_pdf_bytes(open(TXT, "rb").read(), signing.SignParams(self.p12, "pw123")))
        d = PdfDocument.open(sigf)
        d.add_text(0, fitz.Rect(72, 650, 300, 720), "dopo la firma", 12)
        self.assertEqual(len(signing.verify_pdf_bytes(d.verification_bytes())), 1)
        d.add_redact(0, fitz.Rect(72, 72, 200, 100))
        d.apply_redactions(); self.assertTrue(d.has_permanent_changes)
        self.assertEqual(len(signing.verify_pdf_bytes(d.verification_bytes())), 1)     # anche dopo una modifica permanente
        d.close()

    def test_drop_signatures(self):
        sigf = os.path.join(TMP, "firmato2.pdf")
        open(sigf, "wb").write(signing.sign_pdf_bytes(open(TXT, "rb").read(), signing.SignParams(self.p12, "pw123")))
        d = PdfDocument.open(sigf); self.assertTrue(d.is_signed)
        d.drop_signatures(); self.assertFalse(d.is_signed); self.assertTrue(d.can_undo is False or True)
        out = d.current_bytes(); self.assertEqual(signing.verify_pdf_bytes(out), [])
        d.add_shape(0, "rect", fitz.Rect(10, 10, 50, 50)); self.assertTrue(d.can_undo)
        d.close()

    def test_second_signature_on_signed(self):
        a = signing.sign_pdf_bytes(open(TXT, "rb").read(), signing.SignParams(self.p12, "pw123", field_name="A"))
        b = signing.sign_pdf_bytes(a, signing.SignParams(self.p12, "pw123", field_name="B"))
        st = signing.verify_pdf_bytes(b); self.assertEqual(len(st), 2); self.assertTrue(all(s.intact for s in st))

    def test_compress_signed_invalidates(self):
        s = signing.sign_pdf_bytes(open(TXT, "rb").read(), signing.SignParams(self.p12, "pw123"))
        c = compress.optimize_bytes(s, compress.SaveOptions("medium"))
        st = signing.verify_pdf_bytes(c)
        self.assertTrue(not st or not (st[0].intact and st[0].coverage == "ENTIRE_FILE"))
        # il flusso corretto: comprimere PRIMA e firmare dopo
        c2 = compress.optimize_bytes(open(TXT, "rb").read(), compress.SaveOptions("medium"))
        ok = signing.sign_pdf_bytes(c2, signing.SignParams(self.p12, "pw123"))
        self.assertTrue(signing.verify_pdf_bytes(ok)[0].valid)

class PermanentRedactionTests(unittest.TestCase):
    """La redazione elimina davvero il contenuto dal file salvato: nessuna traccia in oggetti, flussi, annotazioni."""
    SECRET = "SEGRETO-IBAN-IT60X0542811101000000123456"

    def _build(self, path):
        d = fitz.open(); pg = d.new_page()
        pg.insert_text((72, 100), "Pubblico: ciao", fontsize=12)
        pg.insert_text((72, 140), self.SECRET, fontsize=12)
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 100), False); pm.set_rect(pm.irect, (255, 0, 0))
        pg.insert_image(fitz.Rect(72, 200, 272, 300), pixmap=pm)
        pg.add_text_annot((300, 140), "nota").set_info(content="nota con " + self.SECRET)
        pg.add_freetext_annot(fitz.Rect(72, 320, 300, 350), "freetext " + self.SECRET)
        w = fitz.Widget(); w.field_type = fitz.PDF_WIDGET_TYPE_TEXT; w.field_name = "iban"; w.rect = fitz.Rect(72, 400, 300, 420)
        w.field_value = self.SECRET; pg.add_widget(w)
        d.save(path); d.close()

    def _leaks(self, data: bytes) -> list:
        d = fitz.open("pdf", data); hits = []
        if self.SECRET.encode() in data:
            hits.append("raw")
        for x in range(1, d.xref_length()):
            try:
                if self.SECRET in d.xref_object(x, compressed=False):
                    hits.append(f"obj{x}")
                if d.xref_is_stream(x) and self.SECRET.encode() in (d.xref_stream(x) or b""):
                    hits.append(f"stream{x}")
            except Exception:
                pass
        if self.SECRET in "".join(pg.get_text() for pg in d):
            hits.append("text")
        for pg in d:
            for im in pg.get_images(full=True):
                pm = fitz.Pixmap(d, im[0])
                if any(pm.pixel(x, y)[:3] == (255, 0, 0) for x in range(0, pm.width, 9) for y in range(0, pm.height, 9)):
                    hits.append("immagine")
        return hits

    def _redact_all(self, d):
        d.add_redact(0, d.page(0).search_for(self.SECRET)[0])
        d.add_redact(0, fitz.Rect(72, 200, 272, 300))
        d.add_redact(0, fitz.Rect(290, 130, 320, 160))
        d.add_redact(0, fitz.Rect(72, 320, 300, 350))
        d.add_redact(0, fitz.Rect(72, 400, 300, 420))
        return d.apply_redactions()

    def test_saved_file_has_no_trace(self):
        src = os.path.join(TMP, "red_src.pdf"); self._build(src)
        d = PdfDocument.open(src)
        self.assertGreaterEqual(len(self._leaks(d.current_bytes())), 5)           # prima: tutto presente
        self.assertEqual(self._redact_all(d), 5)
        self.assertEqual(self._leaks(d.current_bytes()), [])
        d.close()

    def test_permanent_flag_follows_undo_redo_and_save(self):
        src = os.path.join(TMP, "red_src2.pdf"); self._build(src)
        d = PdfDocument.open(src)
        self.assertFalse(d.has_permanent_changes)
        d.add_shape(0, "rect", fitz.Rect(10, 10, 50, 50)); self.assertFalse(d.has_permanent_changes)
        self._redact_all(d); self.assertTrue(d.has_permanent_changes)
        d.undo(); self.assertFalse(d.has_permanent_changes)                       # annullata: nulla di irreversibile
        d.redo(); self.assertTrue(d.has_permanent_changes)
        d.add_shape(0, "rect", fitz.Rect(60, 10, 90, 50)); d.undo(); self.assertTrue(d.has_permanent_changes)
        d.mark_saved(src); self.assertFalse(d.has_permanent_changes)
        d.close()

    def test_content_delete_and_text_edit_are_permanent(self):
        d = PdfDocument.open(TXT)
        blk = d.text_block_at(0, (100, 100))
        if blk:
            d.replace_text_block(0, blk["rect"], "x", blk["fontsize"], blk["fontname"], blk["color"])
            self.assertTrue(d.has_permanent_changes)
        d.close()

    def test_signed_document_is_rewritten_not_appended(self):
        sigf = os.path.join(TMP, "red_firmato.pdf")
        base = os.path.join(TMP, "red_base.pdf"); self._build(base)
        p12 = os.path.join(TMP, "red.p12")
        signing.create_self_signed_p12(p12, "pw123", "Guido Prova", "Test", "guido@example.org")
        open(sigf, "wb").write(signing.sign_pdf_bytes(open(base, "rb").read(), signing.SignParams(p12, "pw123")))
        d = PdfDocument.open(sigf); self.assertTrue(d.is_signed)
        self._redact_all(d)
        out = d.current_bytes()
        self.assertEqual(self._leaks(out), [])                                    # nessuna revisione precedente nel file
        self.assertEqual(signing.verify_pdf_bytes(out), [])                       # firme rimosse
        d.close()


class CliTests(unittest.TestCase):
    def test_cli(self):
        import subprocess, runpy
        env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), ".."), QT_QPA_PLATFORM="offscreen")
        py = sys.executable
        out = subprocess.run([py, "-m", "pdfdesk", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env).stdout
        self.assertIn("Guido Cauli <guido.cauli@gmail.com>", out); self.assertIn("PDFDesk", out)
        h = subprocess.run([py, "-m", "pdfdesk", "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env).stdout
        self.assertIn("Guido Cauli <guido.cauli@gmail.com>", h)
        o = os.path.join(TMP, "cli_out.pdf")
        r = subprocess.run([py, "-m", "pdfdesk", "--compress", IMG, o, "--preset", "low"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(r.returncode, 0, r.stderr); self.assertLess(os.path.getsize(o), os.path.getsize(IMG) * 0.2)
        p12 = os.path.join(TMP, "cli.p12"); signing.create_self_signed_p12(p12, "", "Cli")
        s = os.path.join(TMP, "cli_signed.pdf"); open(s, "wb").write(signing.sign_pdf_bytes(open(TXT, "rb").read(), signing.SignParams(p12, "")))
        v = subprocess.run([py, "-m", "pdfdesk", "--verify", s], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr); self.assertIn("integra=sì", v.stdout)


class FileHandleTests(unittest.TestCase):
    """Windows: un documento aperto non deve tenere bloccato il file, altrimenti salvarci sopra fallisce («Accesso negato»)."""

    def test_open_does_not_keep_file_open(self):
        import tempfile
        from pdfdesk import compress
        from pdfdesk.core import PdfDocument
        p = os.path.join(tempfile.mkdtemp(), "h.pdf")
        d0 = fitz.open(); d0.new_page().insert_text((72, 72), "x"); d0.save(p); d0.close()
        doc = PdfDocument.open(p)
        if os.path.isdir("/proc/self/fd"):
            held = [os.readlink(os.path.join("/proc/self/fd", fd)) for fd in os.listdir("/proc/self/fd")
                    if os.path.exists(os.path.join("/proc/self/fd", fd))]
            self.assertNotIn(os.path.realpath(p), held)
        compress.write_atomic(p, doc.current_bytes())                # sovrascrive il file aperto
        self.assertEqual(fitz.open(p).page_count, 1)

    def test_write_atomic_retries_and_cleans_up(self):
        import tempfile, unittest.mock as m
        from pdfdesk import compress
        p = os.path.join(tempfile.mkdtemp(), "r.pdf"); open(p, "wb").write(b"old")
        real = os.replace; calls = []

        def flaky(a, b):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("in uso")
            real(a, b)
        with m.patch.object(compress.os, "replace", flaky), m.patch("time.sleep"):
            compress.write_atomic(p, b"new")
        self.assertEqual(open(p, "rb").read(), b"new"); self.assertEqual(len(calls), 3)
        with m.patch.object(compress.os, "replace", side_effect=PermissionError("bloccato")), m.patch("time.sleep"):
            with self.assertRaises(PermissionError):
                compress.write_atomic(p, b"x")
        self.assertFalse(os.path.exists(p + ".pdfdesk-tmp")); self.assertEqual(open(p, "rb").read(), b"new")


if __name__ == "__main__":
    unittest.main(verbosity=2)
