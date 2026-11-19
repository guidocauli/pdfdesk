# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Test: unione di più PDF e creazione di PDF da scansione (SANE simulato con uno scanimage finto).
import os, stat, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
TMP = tempfile.mkdtemp(prefix="pdfdesk-ms-")
os.environ["PDFDESK_DATA"] = os.path.join(TMP, "data")
import pymupdf as fitz
from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from pdfdesk import shutdown as _shutdown; _shutdown.install_atexit(); _shutdown.watchdog()      # chiusura ordinata delle finestre lasciate aperte dai test
from pdfdesk import merge, scan, dialogs
from pdfdesk.mainwindow import MainWindow

QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, TMP)
app = QApplication.instance() or QApplication([])
from make_samples import block_modal_dialogs; block_modal_dialogs()


def mkpdf(name, texts):
    p = os.path.join(TMP, name); d = fitz.open()
    for t in texts:
        d.new_page().insert_text((72, 100), t, fontsize=14)
    d.save(p); d.close(); return p


def mkimg(name, size=(300, 400), color=(200, 40, 40), dpi=150):
    p = os.path.join(TMP, name); Image.new("RGB", size, color).save(p, dpi=(dpi, dpi)); return p


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.a = mkpdf("a.pdf", ["A1", "A2", "A3"]); self.b = mkpdf("b.pdf", ["B1", "B2"])

    def test_order_ranges_bookmarks(self):
        out = os.path.join(TMP, "m.pdf")
        n = merge.merge_pdfs([{"path": self.b}, {"path": self.a, "pages": "1,3"}], out)
        self.assertEqual(n, 4)
        d = fitz.open(out)
        self.assertEqual([p.get_text().strip() for p in d], ["B1", "B2", "A1", "A3"])
        self.assertEqual(d.get_toc(), [[1, "b", 1], [1, "a", 3]])

    def test_image_and_errors(self):
        out = os.path.join(TMP, "mi.pdf")
        n = merge.merge_pdfs([{"path": self.a, "pages": "1"}, {"path": mkimg("i.png")}], out, bookmarks=False)
        self.assertEqual(n, 2)
        with self.assertRaises(merge.MergeError):
            merge.merge_pdfs([], out)
        with self.assertRaises(merge.MergeError):
            merge.merge_pdfs([{"path": self.a, "pages": "9"}], out)

    def test_encrypted_source(self):
        p = os.path.join(TMP, "enc.pdf"); d = fitz.open(); d.new_page().insert_text((72, 100), "SEGRETO")
        d.save(p, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw"); d.close()
        self.assertTrue(merge.probe(p)["locked"])
        out = os.path.join(TMP, "me.pdf")
        with self.assertRaises(merge.MergeError):
            merge.merge_pdfs([{"path": p, "password": "no"}], out)
        self.assertEqual(merge.merge_pdfs([{"path": p, "password": "pw"}], out), 1)

    def test_dialog_reorder(self):
        dlg = dialogs.MergeDialog(None, [self.a, self.b]); self.addCleanup(dlg.deleteLater)
        self.assertEqual(dlg.total_pages(), 5)
        dlg.list.setCurrentRow(1); dlg.list.item(1).setSelected(True); dlg.move(-1)
        self.assertEqual([i["path"] for i in dlg.items()], [self.b, self.a])
        dlg.list.setCurrentRow(1); dlg.set_pages("2-"); self.assertEqual(dlg.total_pages(), 4)
        dlg.sort_by_name(); self.assertEqual(dlg.items()[0]["path"], self.a)
        dlg.reverse(); self.assertEqual(dlg.items()[0]["path"], self.b)

    def test_gui_batch_opens_result(self):
        w = MainWindow(); w.show()
        self.assertTrue(w.a_merge.isEnabled() and w.a_scan.isEnabled())      # disponibili anche senza PDF aperto
        out = w.merge_dialog(items=[{"path": self.a}, {"path": self.b}], out=os.path.join(TMP, "g.pdf"))
        self.assertEqual(w.pdf.doc.page_count, 5)
        w.pdf.modified = False; w.close()

    def test_cli(self):
        from pdfdesk import cli
        out = os.path.join(TMP, "c.pdf")
        self.assertEqual(cli.main(["--merge", out, self.a, self.b]), 0)
        self.assertEqual(fitz.open(out).page_count, 5)


FAKE = r"""#!/bin/sh
# scanimage finto: -L/-f elenca un dispositivo; altrimenti produce PNG (o più file con --batch)
case "$*" in
  *"-f"*"%d"*) echo "fake:0|Acme ScanMaster 3000|flatbed scanner"; exit 0;;
esac
for a in "$@"; do case "$a" in --batch=*) B="${a#--batch=}";; --resolution=*) R="${a#--resolution=}";; esac; done
if [ -n "$B" ]; then
  for i in 1 2 3; do f=$(printf "$B" $i); python3 -c "from PIL import Image; Image.new('RGB',(210,297),(10,$((i*60)),10)).save('$f')"; done
  echo "scanimage: Document feeder out of documents" >&2; exit 7
fi
python3 -c "import sys; from PIL import Image; Image.new('RGB',(300,400),(20,20,200)).save(sys.stdout.buffer,'PNG')"
"""


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = os.path.join(TMP, "bin"); os.makedirs(d)
        p = os.path.join(d, "scanimage"); open(p, "w").write(FAKE); os.chmod(p, 0o755)
        cls.old = os.environ["PATH"]; os.environ["PATH"] = d + os.pathsep + cls.old

    @classmethod
    def tearDownClass(cls):
        os.environ["PATH"] = cls.old

    def test_list_and_flatbed(self):
        sc = scan.list_scanners()
        self.assertEqual(len(sc), 1); self.assertEqual(sc[0].backend, "sane"); self.assertIn("Acme", sc[0].name)
        f = scan.scan_pages(sc[0], scan.ScanParams(dpi=150), os.path.join(TMP, "s1"))
        self.assertEqual(len(f), 1); self.assertEqual(Image.open(f[0]).size, (300, 400))

    def test_adf_batch(self):
        sc = scan.list_scanners()[0]
        f = scan.scan_pages(sc, scan.ScanParams(source="adf"), os.path.join(TMP, "s2"))
        self.assertEqual(len(f), 3)

    def test_adf_twice_no_overwrite(self):
        sc = scan.list_scanners()[0]; folder = os.path.join(TMP, "s3")
        a = scan.scan_pages(sc, scan.ScanParams(source="adf"), folder)
        b = scan.scan_pages(sc, scan.ScanParams(), folder)
        c = scan.scan_pages(sc, scan.ScanParams(source="adf"), folder)
        self.assertEqual(len(set(a + b + c)), 7)

    def test_images_to_pdf(self):
        files = [mkimg("p1.png", (300, 400), dpi=150), mkimg("p2.png", (600, 400), dpi=300)]
        out = os.path.join(TMP, "s.pdf")
        self.assertEqual(scan.images_to_pdf(files, out, 300, jpeg_quality=70), 2)
        d = fitz.open(out)
        self.assertAlmostEqual(d[0].rect.width, 144, 0); self.assertAlmostEqual(d[0].rect.height, 192, 0)
        self.assertAlmostEqual(d[1].rect.width, 144, 0)
        with self.assertRaises(scan.ScanError):
            scan.images_to_pdf([], out)

    def test_dialog_flow(self):
        dlg = dialogs.ScanDialog(None, os.path.join(TMP, "dlg.pdf")); self.addCleanup(dlg.deleteLater)
        dlg.refresh(); self.assertEqual(dlg.dev.count(), 1)
        dlg.dpi.setCurrentIndex(dlg.dpi.findData(150))
        dlg._scanned(scan.scan_pages(dlg.dev.currentData(), dlg.params(), dlg.folder), "")
        self.assertEqual(dlg.pages.count(), 1)
        self.assertEqual(dlg.import_files([mkimg("x.png")]), 1)
        dlg.pages.item(0).setSelected(True); dlg.rotate(90)
        self.assertEqual(Image.open(dlg.files()[0]).size, (400, 300))
        self.assertEqual(dlg.pages.count(), 2)
        dlg.remove_selected(); self.assertEqual(dlg.pages.count(), 1)


class MergeBookmarkTests(unittest.TestCase):
    """Unione: i segnalibri originali di ogni file restano, sotto quello del file, e puntano alle pagine giuste."""

    def _docs(self):
        import tempfile
        t = tempfile.mkdtemp(); a = os.path.join(t, "rel.pdf"); b = os.path.join(t, "man.pdf")
        d = fitz.open()
        for i in range(5):
            d.new_page().insert_text((72, 72), f"A{i + 1}")
        d.set_toc([[1, "Introduzione", 1], [2, "Scopo", 2], [1, "Costi", 3], [2, "Server", 4], [3, "Dettaglio", 5]]); d.save(a)
        d = fitz.open()
        for i in range(3):
            d.new_page()
        d.set_toc([[1, "Capitolo 1", 1], [1, "Capitolo 2", 3]]); d.save(b)
        return t, a, b

    def test_bookmarks_nested_and_remapped(self):
        t, a, b = self._docs(); o = os.path.join(t, "o.pdf")
        merge.merge_pdfs([{"path": a, "pages": "1,4-5"}, {"path": b}], o)
        self.assertEqual(fitz.open(o).get_toc(), [
            [1, "rel", 1], [2, "Introduzione", 1], [2, "Costi", 2], [3, "Server", 2], [4, "Dettaglio", 3],
            [1, "man", 4], [2, "Capitolo 1", 4], [2, "Capitolo 2", 6]])

    def test_without_file_bookmarks_originals_kept(self):
        t, a, b = self._docs(); o = os.path.join(t, "o2.pdf")
        merge.merge_pdfs([{"path": b}, {"path": a, "pages": "2"}], o, bookmarks=False)
        self.assertEqual(fitz.open(o).get_toc(), [[1, "Capitolo 1", 1], [1, "Capitolo 2", 3], [1, "Introduzione", 4], [2, "Scopo", 4]])

    def test_fix_levels(self):
        self.assertEqual(merge._fix_levels([[3, "a", 1], [1, "b", 2], [4, "c", 3]]), [[1, "a", 1], [1, "b", 2], [2, "c", 3]])


class MergeSizeTests(unittest.TestCase):
    """Regressione: l'unione copiava font e immagini condivisi una volta per pagina (2 PDF da 300 KB → 6 MB)."""

    def test_shared_resources_copied_once(self):
        import tempfile
        t = tempfile.mkdtemp(); a = os.path.join(t, "a.pdf"); o = os.path.join(t, "o.pdf")
        logo = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 300), False); logo.clear_with(120)
        img = logo.tobytes("png")
        d = fitz.open()
        for i in range(12):
            pg = d.new_page(); pg.insert_text((72, 72), f"Pagina {i + 1}"); pg.insert_image(fitz.Rect(300, 40, 400, 140), stream=img)
        d.save(a, garbage=4, deflate=True)
        merge.merge_pdfs([{"path": a, "pages": "5,1-3,8-12"}, {"path": a}], o)
        r = fitz.open(o)
        self.assertEqual(len({x[0] for pg in r for x in pg.get_images()}), 1)        # una sola copia dell'immagine
        self.assertLess(os.path.getsize(o), os.path.getsize(a) * 1.3)
        # anche «Estrai pagine»
        from pdfdesk.core import PdfDocument
        e = os.path.join(t, "e.pdf")
        PdfDocument.open(a).extract_pages([0, 2, 3, 7, 9], e)
        r = fitz.open(e)
        self.assertEqual(r.page_count, 5); self.assertEqual(len({x[0] for pg in r for x in pg.get_images()}), 1)
        self.assertLess(os.path.getsize(e), os.path.getsize(a))


def mkmeta(name, title, author, pdfa=False):
    p = os.path.join(TMP, name); d = fitz.open(); d.new_page().insert_text((72, 100), name)
    d.set_metadata({"title": title, "author": author, "subject": "sogg " + title, "keywords": "k1, k2"})
    xmp = ('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
           'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"'
           + (' pdfaid:part="2" pdfaid:conformance="B"' if pdfa else "")
           + f'><dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>'
           + ('<pdfaid:part>2</pdfaid:part>' if pdfa else "")
           + '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
    d.set_xml_metadata(xmp); d.save(p); d.close(); return p


class MergeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.plain = mkpdf("senza.pdf", ["x"])                       # nessun metadato descrittivo
        self.a = mkmeta("ma.pdf", "Titolo A", "Autore A")
        self.b = mkmeta("mb.pdf", "Titolo B", "Autore B", pdfa=True)
        self.out = os.path.join(TMP, "meta-out.pdf")

    def meta(self):
        d = fitz.open(self.out); m = d.metadata; x = d.get_xml_metadata(); d.close(); return m, x

    def test_probe(self):
        self.assertEqual(merge.probe(self.plain)["meta"], {})
        self.assertEqual(merge.probe(self.a)["meta"]["title"], "Titolo A")
        self.assertEqual(merge.probe(mkimg("mi.png"))["meta"], {})

    def test_automatico_primo_pdf_con_metadati(self):
        merge.merge_pdfs([{"path": mkimg("mi.png")}, {"path": self.plain}, {"path": self.a}, {"path": self.b}], self.out)
        m, x = self.meta()
        self.assertEqual((m["title"], m["author"], m["keywords"]), ("Titolo A", "Autore A", "k1, k2"))
        self.assertIn("Titolo A", x)

    def test_scelta_esplicita_e_conformita_tolta(self):
        merge.merge_pdfs([{"path": self.a}, {"path": self.b}], self.out, meta_from=1)
        m, x = self.meta()
        self.assertEqual(m["title"], "Titolo B")
        self.assertIn("Titolo B", x)
        self.assertNotIn("pdfaid:part", x)
        self.assertNotIn("pdfaid:conformance", x)

    def test_nessuno_e_titolo(self):
        merge.merge_pdfs([{"path": self.a}], self.out, meta_from=-1)
        self.assertFalse(self.meta()[0].get("title"))
        merge.merge_pdfs([{"path": self.a}], self.out, title="Nuovo")
        m, _ = self.meta()
        self.assertEqual((m["title"], m["author"]), ("Nuovo", "Autore A"))
        with self.assertRaises(merge.MergeError):
            merge.merge_pdfs([{"path": self.a}], self.out, meta_from=3)

    def test_dialogo_segue_il_file(self):
        dlg = dialogs.MergeDialog(None, [self.plain, self.a, self.b])
        self.assertTrue(dlg.meta.isEnabled())
        self.assertIsNone(dlg.meta_from())                           # automatico
        self.assertIn("ma.pdf", dlg.meta.itemText(0))
        dlg.meta.setCurrentIndex(dlg.meta.findData(self.b))
        self.assertEqual(dlg.meta_from(), 2)
        dlg.reverse()                                                # l'ordine cambia, la scelta resta su mb.pdf
        self.assertEqual(dlg.meta_from(), 0)
        self.assertIn("mb.pdf", dlg.meta.itemText(0))                # automatico ora indica il primo con metadati
        dlg.meta.setCurrentIndex(dlg.meta.findData("-"))
        self.assertEqual(dlg.meta_from(), -1)
        self.assertNotIn("meta", dlg.items()[0])
        dlg2 = dialogs.MergeDialog(None, [self.plain])
        self.assertFalse(dlg2.meta.isEnabled())
        dlg.deleteLater(); dlg2.deleteLater()


if __name__ == "__main__":
    unittest.main()
