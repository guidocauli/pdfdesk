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
from pdfdesk import merge, scan, dialogs
from pdfdesk.mainwindow import MainWindow

QSettings.setDefaultFormat(QSettings.IniFormat); QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, TMP)
app = QApplication.instance() or QApplication([])


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


if __name__ == "__main__":
    unittest.main()
