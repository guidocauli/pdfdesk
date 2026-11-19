"""Regressione: i font non devono essere incorporati più volte nei salvataggi."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf as fitz  # noqa: E402

from pdfdesk.core import PdfDocument  # noqa: E402


def _fontfiles(data):
    d = fitz.open("pdf", data)
    n = 0
    for xr in range(1, d.xref_length()):
        for k in ("FontFile", "FontFile2", "FontFile3"):
            if d.xref_get_key(xr, k)[0] != "null":
                n += 1
    return n


class FontDedupeTests(unittest.TestCase):
    def test_caselle_testo_un_solo_font(self):
        d = PdfDocument()
        d.doc = fitz.open()
        for _ in range(3):
            d.doc.new_page()
        for i in range(12):
            r = fitz.Rect(50, 50 + (i // 3) * 60, 300, 100 + (i // 3) * 60)
            d.add_text(i % 3, r, f"Casella {i} àèé", 12, "helv", style="u")
        b = d.current_bytes()
        self.assertLessEqual(_fontfiles(b), 2)
        self.assertLess(len(b), 150 * 1024)
        t = fitz.open("pdf", b)
        self.assertIn("Casella 11", "".join(p.get_text() for p in t))


if __name__ == "__main__":
    unittest.main()
