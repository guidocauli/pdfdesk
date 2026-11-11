# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Test di conversione e verifica PDF/A e PDF/X (richiedono Ghostscript; veraPDF, se presente, valida i PDF/A).
import os, subprocess, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-std-test-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")
import pymupdf as fitz
import test_features as tf
from pdfdesk import shutdown as _shutdown; _shutdown.install_atexit()      # chiusura ordinata delle finestre lasciate aperte dai test
from pdfdesk import compress, fonts, pdfstd, signing
from pdfdesk.core import PdfDocument

GS = pdfstd.find_gs()
VERA = pdfstd.find_verapdf()
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def hard_doc():
    d = PdfDocument.open(tf.FORM)
    f = {x.name: x for x in d.list_fields(0)}
    d.set_field(0, f["nome"].xref, "Guido Cauli àèì")
    d.page(0).insert_text((72, 60), "Titolo Helvetica non incorporato", fontsize=14)
    pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 120), False); pm.set_rect(pm.irect, (30, 120, 200))
    d.add_image(0, fitz.Rect(300, 100, 500, 220), pm.tobytes("png"))
    d.add_shape(0, "rect", fitz.Rect(300, 400, 420, 460), (1, 0, 0), (1, .8, .8), 2, 0.4)       # opacità parziale
    d.add_markup(0, "hl", fitz.Rect(72, 50, 300, 64))                                          # fusione Multiply
    d.add_ink(0, [[(300, 500), (380, 540), (460, 510)]], (0, .6, 0), 3)
    if fonts.resolve("@DejaVu Sans Book") or os.path.exists(DEJAVU):
        code = fonts.add_user_font(DEJAVU)
        d.add_text(0, fitz.Rect(300, 300, 540, 360), "Привет мир Ελληνικά €", 14, code, (0, 0, .5), (1, 1, .8), 1)
    return d.current_bytes()


@unittest.skipUnless(GS, "Ghostscript non installato")
class StandardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = hard_doc()

    def test_every_standard_converts_and_checks(self):
        for key, st in pdfstd.STANDARDS.items():
            with self.subTest(key):
                out = pdfstd.convert(self.src, key, title="Prova")
                rep = pdfstd.check(out, key)
                self.assertTrue(rep.ok, rep.text())
                self.assertEqual(pdfstd.detect(out), {"pdfa-1b": "PDF/A-1b", "pdfa-2b": "PDF/A-2b", "pdfa-3b": "PDF/A-3b",
                                                        "pdfx-1a": "PDF/X-1a:2001", "pdfx-3": "PDF/X-3:2002", "pdfx-4": "PDF/X-4"}[key])
                doc = fitz.open("pdf", out)
                text = doc[0].get_text()
                for w in ("Titolo", "Guido", "Привет", "Ελληνικά"):                              # il testo resta testo, anche non latino
                    self.assertIn(w, text, f"{key}: «{w}» perso")
                self.assertLess(len(doc[0].get_images()), 3, "la pagina è stata rasterizzata")
                self.assertLess(len(out), 400_000)

    def test_detect_on_plain_pdf_and_unsigned_check_fails(self):
        self.assertIsNone(pdfstd.detect(self.src))
        rep = pdfstd.check(self.src, "pdfa-2b")
        self.assertFalse(rep.ok)
        self.assertTrue(any("incorporati" in t or "OutputIntent" in t for _, t in rep.issues))

    @unittest.skipUnless(VERA, "veraPDF non installato")
    def test_verapdf_validates_pdfa(self):
        for key in ("pdfa-1b", "pdfa-2b", "pdfa-3b"):
            out = pdfstd.convert(self.src, key)
            r = pdfstd.check(out, key)
            self.assertIn("veraPDF", r.validator)
            self.assertTrue(r.ok, r.text())

    def test_signed_document_is_refused(self):
        p12 = os.path.join(TMP, "t.p12"); signing.create_self_signed_p12(p12, "pw", "T")
        signed = signing.sign_pdf_bytes(open(tf.FORM, "rb").read(), signing.SignParams(p12, "pw", field_name="Firma9", page=0, box=(72, 500, 260, 560)))
        with self.assertRaises(pdfstd.StandardError) as c: pdfstd.convert(signed, "pdfa-2b")
        self.assertIn("firme", str(c.exception))

    def test_invalid_input_is_clean_error(self):
        for bad in (b"", b"%PDF-1.4\ngarbage"):
            with self.assertRaises(pdfstd.StandardError): pdfstd.convert(bad, "pdfa-2b")
        with self.assertRaises(pdfstd.StandardError): pdfstd.convert(self.src, "pdfa-9z")

    def test_links_kept_in_pdfa_removed_in_pdfx(self):
        d = fitz.open(); d.new_page(); d.new_page(); p = d[0]; p.insert_text((72, 100), "Link", fontsize=14)
        p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 90, 200, 110), "uri": "https://example.org"})
        p.insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 120, 200, 140), "page": 1, "to": fitz.Point(0, 0)})
        s = d.tobytes()
        a = fitz.open("pdf", pdfstd.convert(s, "pdfa-2b"))[0].get_links()
        self.assertEqual({(l["kind"]) for l in a}, {fitz.LINK_URI, fitz.LINK_GOTO})
        self.assertTrue(pdfstd.check(pdfstd.convert(s, "pdfa-2b"), "pdfa-2b").ok)
        x = pdfstd.convert(s, "pdfx-1a")
        self.assertEqual(fitz.open("pdf", x)[0].get_links(), [])
        self.assertTrue(pdfstd.check(x, "pdfx-1a").ok)

    def test_metadata_and_cropbox_preserved(self):
        d = fitz.open()
        for i in range(2):
            p = d.new_page(); p.insert_text((72, 100), f"Pagina {i}", fontsize=14)
        d[1].set_cropbox(fitz.Rect(20, 20, 500, 700))
        d.set_metadata({"title": "Titolo X", "author": "Guido Cauli", "subject": "Oggetto"})
        o = fitz.open("pdf", pdfstd.convert(d.tobytes(), "pdfa-2b"))
        self.assertEqual((o.metadata["title"], o.metadata["author"], o.metadata["subject"]), ("Titolo X", "Guido Cauli", "Oggetto"))
        self.assertEqual(o[1].cropbox, fitz.Rect(20, 20, 500, 700))

    def test_reconvert_between_standards_and_embedded_files(self):
        a2 = pdfstd.convert(self.src, "pdfa-2b")
        self.assertTrue(pdfstd.check(pdfstd.convert(a2, "pdfa-1b"), "pdfa-1b").ok)
        self.assertTrue(pdfstd.check(pdfstd.convert(pdfstd.convert(self.src, "pdfx-4"), "pdfa-2b"), "pdfa-2b").ok)

    def test_compress_then_standard_pipeline_and_cli(self):
        out = compress.optimize_bytes(self.src, compress.SaveOptions("low", standard="pdfa-2b"))
        self.assertTrue(pdfstd.check(out, "pdfa-2b").ok)
        src = os.path.join(TMP, "s.pdf"); dst = os.path.join(TMP, "o.pdf"); open(src, "wb").write(self.src)
        env = dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), ".."))
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "pdfdesk", "--compress", src, dst, "--preset", "medium", "--standard", "pdfx-4"],
                           capture_output=True, text=True, env=env); self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "pdfdesk", "--check", dst], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout); self.assertIn("CONFORME", r.stdout)
        r = subprocess.run([sys.executable, "-W", "ignore", "-m", "pdfdesk", "--check", src, "--standard", "pdfa-2b"], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2); self.assertIn("NON conforme", r.stdout)

    def test_sign_after_conversion_keeps_standard(self):
        out = pdfstd.convert(self.src, "pdfa-2b")
        p12 = os.path.join(TMP, "t2.p12"); signing.create_self_signed_p12(p12, "pw", "T")
        signed = signing.sign_pdf_bytes(out, signing.SignParams(p12, "pw", field_name="FirmaA", page=0, box=(72, 700, 260, 760)))
        self.assertEqual(pdfstd.detect(signed), "PDF/A-2b")
        st = signing.verify_pdf_bytes(signed); self.assertTrue(st and st[0].valid)

    def test_document_detects_standard_on_open(self):
        p = os.path.join(TMP, "a2.pdf"); open(p, "wb").write(pdfstd.convert(self.src, "pdfa-2b"))
        self.assertEqual(PdfDocument.open(p).standard, "PDF/A-2b")
        self.assertIsNone(PdfDocument.open(tf.FORM).standard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
