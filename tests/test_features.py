# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Test di font TTF/OTF, moduli compilabili e firma con smart card (PKCS#11, token virtuale SoftHSM).
import glob, os, shutil, subprocess, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-feat-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")
import pymupdf as fitz
from make_samples import make_text_pdf
from pdfdesk import fonts, signing
from pdfdesk.core import PdfDocument, PdfError, T_FREETEXT

def first(*pats):
    for p in pats:
        g = sorted(glob.glob(p))
        if g: return g[0]
TTF = first("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/**/DejaVuSerif.ttf")
OTF = first("/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrepagella-bold.otf", "/usr/share/**/texgyre*.otf")


@unittest.skipUnless(TTF and OTF, "font di prova non presenti")
class FontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ttf = fonts.add_user_font(TTF); cls.otf = fonts.add_user_font(OTF)

    def doc(self):
        d = PdfDocument.new(); return d

    def test_ttf_and_otf_textboxes_render_and_roundtrip(self):
        d = self.doc()
        x1 = d.add_text(0, fitz.Rect(60, 100, 360, 160), "Àèìòù € ß", 16, self.ttf, (0, 0, .5), (1, 1, .85), 1)
        x2 = d.add_text(0, fitz.Rect(60, 200, 360, 260), "OTF Pagella", 18, self.otf, (0, .4, 0))
        i = d.annot_info(0, x1)
        self.assertEqual((i.fontname, i.text, i.fontsize), (self.ttf, "Àèìòù € ß", 16.0))
        pix = d.render(0, 1.0)
        self.assertTrue(any(b != 255 for b in bytes(pix.samples)[::7]))           # qualcosa è stato disegnato
        d2 = PdfDocument.open_bytes(d.current_bytes()) if hasattr(PdfDocument, "open_bytes") else None
        p = os.path.join(TMP, "ft.pdf"); open(p, "wb").write(d.current_bytes())
        d2 = PdfDocument.open(p)
        self.assertEqual(sorted(a.fontname for a in d2.list_annots(0)), sorted([self.ttf, self.otf]))
        self.assertIn("Pagella", " ".join(a.text for a in d2.list_annots(0)))

    def test_move_resize_edit_switch_font(self):
        d = self.doc()
        x = d.add_text(0, fitz.Rect(60, 100, 300, 160), "uno", 14, self.ttf)
        x = d.set_rect(0, x, fitz.Rect(80, 120, 400, 220))
        self.assertAlmostEqual(d.annot_info(0, x).rect.x0, 80, 1)
        x = d.set_props(0, x, text="due", fontname=self.otf, fontsize=20, text_color=(1, 0, 0))
        i = d.annot_info(0, x); self.assertEqual((i.text, i.fontname, i.fontsize), ("due", self.otf, 20.0))
        x = d.set_props(0, x, fontname="cour")                                    # ritorno a un base-14
        self.assertEqual(d.annot_info(0, x).fontname, "cour")
        d.undo(); d.undo(); d.undo()
        self.assertEqual(d.annot_info(0, d.list_annots(0)[0].xref).text, "uno")

    def ink_box(self, d, rect):
        pm = d.render(0, 1.0); r = fitz.IRect(int(rect.x0) + 3, int(rect.y0) + 3, int(rect.x1) - 3, int(rect.y1) - 3)
        xs, ys = [], []
        for y in range(r.y0, r.y1):
            for x in range(r.x0, r.x1):
                if sum(pm.pixel(x, y)[:3]) < 300: xs.append(x); ys.append(y)
        return (max(xs) - min(xs), max(ys) - min(ys)) if xs else None

    def test_text_reads_upright_on_every_page_rotation(self):
        for rot in (0, 90, 180, 270):
            d = self.doc(); d.page(0).set_rotation(rot)
            d.add_text(0, fitz.Rect(60, 100, 330, 160), "Una riga di testo lunga", 18, self.ttf, (0, 0, 0))
            w, h = self.ink_box(d, d.list_annots(0)[0].rect)
            self.assertGreater(w, 3 * h, f"testo non orizzontale con pagina a {rot}°")

    def test_page_rotated_after_creation_realigns_custom_and_base_boxes(self):
        d = self.doc()                                                           # caselle quadrate: il testo resta su una riga
        d.add_text(0, fitz.Rect(60, 100, 360, 400), "Una riga", 18, self.ttf, (0, 0, 0))
        d.add_text(0, fitz.Rect(60, 450, 360, 750), "Una riga", 18, "helv", (0, 0, 0))
        for step in range(3):
            d.rotate_pages([0], 90)
            for a in d.list_annots(0):
                w, h = self.ink_box(d, a.rect)
                self.assertGreater(w, 2 * h, f"{a.fontname} dopo rotazione a {d.page(0).rotation}°")

    def test_narrow_box_with_long_word_is_not_blank(self):
        d = self.doc()
        d.add_text(0, fitz.Rect(60, 100, 110, 300), "supercalifragilistichespiralidoso", 18, self.ttf, (0, 0, 0), None, 0)
        self.assertIsNotNone(self.ink_box(d, d.list_annots(0)[0].rect))
        d.add_text(0, fitz.Rect(200, 100, 400, 120), "riga1\nriga2\nriga3\nriga4", 18, self.ttf)   # troppo bassa: ritagliata
        self.assertIsNotNone(self.ink_box(d, d.list_annots(0)[1].rect))

    def test_move_without_font_allowed_resize_not(self):
        d = self.doc(); d.add_text(0, fitz.Rect(60, 100, 300, 160), "Sposta", 16, self.ttf)
        p = os.path.join(TMP, "mv.pdf"); open(p, "wb").write(d.current_bytes())
        saved = dict(fonts._user)
        try:
            fonts._user.pop(self.ttf[1:], None); fonts._system.pop(self.ttf[1:], None)
            d2 = PdfDocument.open(p); x = d2.list_annots(0)[0].xref
            x = d2.set_rect(0, x, fitz.Rect(100, 200, 340, 260))                  # solo spostamento: consentito
            with self.assertRaises(PdfError): d2.set_rect(0, x, fitz.Rect(100, 200, 500, 300))
        finally:
            fonts._user.update(saved)

    def test_missing_font_is_clear_error(self):
        d = self.doc()
        with self.assertRaises(PdfError): d.add_text(0, fitz.Rect(60, 100, 300, 160), "x", 12, "@FontInesistente")

    def test_replace_text_with_custom_font(self):
        p = os.path.join(TMP, "t.pdf"); make_text_pdf(p); d = PdfDocument.open(p)
        blk = d.text_block_at(0, (100, 100)) or d.text_block_at(0, (100, 90))
        if not blk: self.skipTest("nessun blocco di testo")
        d.replace_text_block(0, blk["rect"], "Testo con font TTF", blk["fontsize"], self.ttf, blk["color"])
        self.assertIn("Testo con font TTF", d.page(0).get_text())


def make_form(path):
    doc = fitz.open(); p = doc.new_page()
    def add(t, r, name, **kw):
        w = fitz.Widget(); w.field_type = t; w.rect = fitz.Rect(*r); w.field_name = name
        for k, v in kw.items(): setattr(w, k, v)
        p.add_widget(w)
    add(fitz.PDF_WIDGET_TYPE_TEXT, (72, 100, 300, 120), "nome")
    add(fitz.PDF_WIDGET_TYPE_TEXT, (72, 140, 300, 200), "note", field_flags=fitz.PDF_TX_FIELD_IS_MULTILINE)
    add(fitz.PDF_WIDGET_TYPE_TEXT, (72, 210, 160, 230), "cap", text_maxlen=5)
    add(fitz.PDF_WIDGET_TYPE_CHECKBOX, (72, 250, 86, 264), "ok")
    add(fitz.PDF_WIDGET_TYPE_COMBOBOX, (72, 280, 200, 300), "citta", choice_values=["Roma", "Milano", "Torino"])
    add(fitz.PDF_WIDGET_TYPE_SIGNATURE, (72, 330, 260, 380), "firma")
    doc.save(path)

FORM = os.path.join(TMP, "form.pdf"); make_form(FORM)


class FormTests(unittest.TestCase):
    def setUp(self): self.d = PdfDocument.open(FORM); self.f = {x.name: x for x in self.d.list_fields(0)}
    def vals(self): return {x.name: x.value for x in self.d.list_fields(0)}

    def test_detect_and_kinds(self):
        self.assertTrue(self.d.has_form()); self.assertEqual(self.d.count_fields(), 6)
        self.assertEqual({k: v.kind for k, v in self.f.items()},
                         {"nome": "text", "note": "text", "cap": "text", "ok": "checkbox", "citta": "combo", "firma": "signature"})
        self.assertTrue(self.f["note"].multiline); self.assertEqual(self.f["cap"].maxlen, 5)
        self.assertEqual(self.f["citta"].choices, ["Roma", "Milano", "Torino"])
        self.assertFalse(PdfDocument.open(os.path.join(TMP, "t.pdf") if os.path.exists(os.path.join(TMP, "t.pdf")) else FORM) is None)

    def test_fill_undo_save_reload(self):
        d = self.d
        d.set_field(0, self.f["nome"].xref, "Guido Cauli"); d.set_field(0, self.f["note"].xref, "riga1\nriga2")
        d.set_field(0, self.f["ok"].xref, True); d.set_field(0, self.f["citta"].xref, "Milano")
        v = self.vals(); self.assertEqual((v["nome"], v["note"], v["ok"], v["citta"]), ("Guido Cauli", "riga1\nriga2", True, "Milano"))
        d.undo(); self.assertEqual(self.vals()["citta"], ""); d.redo()
        p = os.path.join(TMP, "filled.pdf"); open(p, "wb").write(d.current_bytes())
        d2 = PdfDocument.open(p); v2 = {x.name: x.value for x in d2.list_fields(0)}
        self.assertEqual((v2["nome"], v2["ok"], v2["citta"]), ("Guido Cauli", True, "Milano"))
        self.assertIn("Guido Cauli", d2.page(0).get_text())                      # l'aspetto è nella pagina

    def test_limits_and_errors(self):
        with self.assertRaises(PdfError): self.d.set_field(0, self.f["cap"].xref, "123456")
        with self.assertRaises(PdfError): self.d.set_field(0, self.f["firma"].xref, "x")
        self.assertEqual(self.d.field_at(0, (100, 110)).name, "nome"); self.assertIsNone(self.d.field_at(0, (500, 700)))

    def test_radio_without_on_state_is_clean_error(self):
        doc = fitz.open(); p = doc.new_page(); w = fitz.Widget(); w.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
        w.rect = fitz.Rect(72, 100, 86, 114); w.field_name = "r"; p.add_widget(w)
        pth = os.path.join(TMP, "radio.pdf"); doc.save(pth)
        d = PdfDocument.open(pth); f = d.list_fields(0)[0]
        n = len(d._undo)
        try: d.set_field(0, f.xref, True)
        except PdfError: self.assertEqual(len(d._undo), n)                       # nessuna voce di annullamento sporca

    def test_flatten(self):
        self.d.set_field(0, self.f["nome"].xref, "Piatto"); self.assertEqual(self.d.flatten_forms(), 6)
        self.assertEqual(self.d.count_fields(), 0); self.assertFalse(self.d.has_form())
        self.assertIn("Piatto", self.d.page(0).get_text())


HSM = first("/usr/lib/softhsm/libsofthsm2.so", "/usr/lib/*/softhsm/libsofthsm2.so")

@unittest.skipUnless(HSM and shutil.which("softhsm2-util") and shutil.which("pkcs11-tool") and shutil.which("openssl"), "SoftHSM/OpenSC non installati")
class SmartCardTests(unittest.TestCase):
    PIN = "1234"

    @classmethod
    def setUpClass(cls):
        h = os.path.join(TMP, "hsm"); os.makedirs(os.path.join(h, "tokens"))
        conf = os.path.join(h, "conf")
        open(conf, "w").write(f"directories.tokendir = {h}/tokens\nobjectstore.backend = file\n")
        cls.env = dict(os.environ, SOFTHSM2_CONF=conf); os.environ["SOFTHSM2_CONF"] = conf
        def run(*a): subprocess.run(a, cwd=h, env=cls.env, check=True, capture_output=True)
        run("softhsm2-util", "--init-token", "--free", "--label", "TestCard", "--so-pin", "12345678", "--pin", cls.PIN)
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "k.pem", "-out", "c.pem", "-days", "30",
            "-subj", "/CN=Guido Cauli Test/O=PDFDesk", "-addext", "keyUsage=digitalSignature,nonRepudiation")
        run("openssl", "pkcs8", "-topk8", "-nocrypt", "-in", "k.pem", "-out", "k8.pem"); run("openssl", "x509", "-in", "c.pem", "-outform", "der", "-out", "c.der")
        run("softhsm2-util", "--import", "k8.pem", "--token", "TestCard", "--label", "chiave", "--id", "a1b2", "--pin", cls.PIN)
        run("pkcs11-tool", "--module", HSM, "--token-label", "TestCard", "--login", "--pin", cls.PIN, "--write-object", "c.der", "--type", "cert", "--label", "cert", "--id", "a1b2")

    def params(self, pin=None, **kw):
        t = [t for t in signing.list_tokens(HSM) if t.certs][0]
        return signing.SignParams("", pkcs11_lib=HSM, pkcs11_token_label=t.label, pkcs11_token_serial=t.serial,
                                  pkcs11_cert_id=t.certs[0].cert_id, pkcs11_pin=pin or self.PIN, **kw)

    def test_list_tokens_and_candidates(self):
        t = [t for t in signing.list_tokens(HSM) if t.certs][0]
        self.assertEqual(t.label, "TestCard"); self.assertIn("Guido Cauli Test", t.certs[0].subject)
        self.assertIn(HSM, signing.pkcs11_candidates())

    def test_sign_visible_and_cascade(self):
        data = open(FORM, "rb").read()
        out = signing.sign_pdf_bytes(data, self.params(field_name="FirmaCard", page=0, box=(72, 450, 260, 510), reason="prova"))
        st = signing.verify_pdf_bytes(out); self.assertEqual((len(st), st[0].intact, st[0].valid), (1, True, True))
        self.assertIn("Guido Cauli Test", st[0].signer)
        out2 = signing.sign_pdf_bytes(out, self.params(field_name="Firma2"))
        st = signing.verify_pdf_bytes(out2); self.assertEqual([s.valid for s in st], [True, True])
        bad = bytearray(out2); i = bad.find(b"Roma"); bad[i:i + 4] = b"Rima"
        if i > 0: self.assertFalse(all(s.intact for s in signing.verify_pdf_bytes(bytes(bad))))

    def test_sign_into_existing_form_field(self):
        out = signing.sign_pdf_bytes(open(FORM, "rb").read(), self.params(field_name="firma", existing_field=True))
        st = signing.verify_pdf_bytes(out); self.assertEqual((st[0].field, st[0].valid), ("firma", True))

    def test_missing_pin_and_unknown_token(self):
        with self.assertRaises(signing.SigningError) as c:
            signing.sign_pdf_bytes(open(FORM, "rb").read(), self.params(pin=" ").__class__(**{**self.params().__dict__, "pkcs11_pin": ""}))
        self.assertIn("PIN", str(c.exception))
        bad = self.params(); bad.pkcs11_token_label = "Inesistente"
        with self.assertRaises(signing.SigningError) as c: signing.sign_pdf_bytes(open(FORM, "rb").read(), bad)
        self.assertIn("scheda", str(c.exception))

    def test_wrong_pin_and_bad_module(self):
        with self.assertRaises(signing.SigningError) as c: signing.sign_pdf_bytes(open(FORM, "rb").read(), self.params(pin="0000"))
        self.assertIn("PIN", str(c.exception))
        with self.assertRaises(signing.SigningError): signing.list_tokens("/non/esiste.so")




class ExportStructureTests(unittest.TestCase):
    """DOCX e ODT mantengono titoli, tabelle e immagini; TXT/TIFF/PNG/JPG producono file validi."""
    def setUp(self):
        import tempfile
        from pdfdesk import export
        self.export = export
        self.tmp = tempfile.mkdtemp(prefix="pdfdesk-exp-")
        d = fitz.open()
        p = d.new_page()
        p.insert_text((72, 80), "Titolo del documento", fontsize=24)
        p.insert_text((72, 110), "Testo normale del paragrafo.", fontsize=11)
        for r in range(3):
            for c in range(3):
                rc = fitz.Rect(72 + c * 100, 140 + r * 24, 172 + c * 100, 164 + r * 24)
                p.draw_rect(rc, color=(0, 0, 0), width=0.8)
                p.insert_text((rc.x0 + 4, rc.y0 + 16), f"r{r}c{c}", fontsize=11)
        p.insert_image(fitz.Rect(72, 300, 172, 380), pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 40), False))
        d.new_page().insert_text((72, 80), "Seconda pagina", fontsize=11)
        self.doc = d

    def test_pages_spec(self):
        self.assertEqual(self.export.parse_pages("1-2,5", 6), [0, 1, 4])
        self.assertEqual(self.export.parse_pages("", 3), [0, 1, 2])
        self.assertEqual(self.export.parse_pages("2-", 4), [1, 2, 3])
        with self.assertRaises(ValueError):
            self.export.parse_pages("9", 3)

    def test_docx_structure(self):
        import docx
        out = os.path.join(self.tmp, "o.docx")
        self.export.export(self.doc, "docx", [0, 1], out, keep_layout=False)
        d = docx.Document(out)
        self.assertEqual(d.paragraphs[0].style.name, "Heading 1")
        self.assertEqual(len(d.tables), 1); self.assertEqual([c.text for c in d.tables[0].rows[1].cells], ["r1c0", "r1c1", "r1c2"])
        self.assertEqual(len(d.inline_shapes), 1)
        self.assertTrue(any("Seconda pagina" in p.text for p in d.paragraphs))
        self.assertIn('w:pageBreakBefore', d.element.xml)

    def test_odt_structure(self):
        import odf.opendocument as od
        from odf import table, text, draw
        out = os.path.join(self.tmp, "o.odt")
        self.export.export(self.doc, "odt", [0, 1], out, keep_layout=False)
        d = od.load(out)
        self.assertEqual(len(d.getElementsByType(text.H)), 1)
        self.assertEqual(len(d.getElementsByType(table.TableRow)), 3)
        self.assertEqual(len(d.getElementsByType(draw.Image)), 1)
        import zipfile
        self.assertEqual(zipfile.ZipFile(out).infolist()[0].filename, "mimetype")

    def test_cancel(self):
        with self.assertRaises(self.export.Cancelled):
            self.export.export(self.doc, "txt", [0, 1], os.path.join(self.tmp, "c.txt"), progress=lambda i, n: False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
