# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
import ast, os, re, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pdfdesk import i18n
from pdfdesk.i18n_en import EN

PKG = os.path.join(os.path.dirname(__file__), "..", "pdfdesk")


class I18nTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("it")

    def test_italian_is_identity_and_english_translates(self):
        i18n.set_language("it"); self.assertEqual(i18n.tr("Annulla"), "Annulla")
        i18n.set_language("en")
        self.assertEqual(i18n.tr("Annulla"), "Cancel")
        self.assertEqual(i18n.tr("testo mai tradotto xyz"), "testo mai tradotto xyz")      # manca: resta l'italiano

    def test_catalog_placeholders_and_mnemonics(self):
        for k, v in EN.items():
            self.assertEqual(sorted(re.findall(r"\{[^}]*\}", k)), sorted(re.findall(r"\{[^}]*\}", v)), k)

    def test_every_tokenized_text_has_translation(self):
        miss = set()
        for f in ("mainwindow", "dialogs", "core", "scan", "merge"):
            t = ast.parse(open(os.path.join(PKG, f + ".py"), encoding="utf-8").read())
            for n in ast.walk(t):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tr" and n.args \
                        and isinstance(n.args[0], ast.Constant):
                    k = n.args[0].value
                    if k not in EN and len(k) > 3 and re.search(r"[a-zà-ú]{4}", k) and not re.fullmatch(r"[\w+&. ()*/,-]+", k):
                        miss.add(k)
        # alcuni «testi» sono identificatori/formati senza traduzione
        ignore = {"GuidoCauli", "CreationDate", "Keywords", "ModDate", "Producer", "Subject", "Trapped", "Password:"}
        self.assertEqual(sorted(m for m in miss if m not in ignore), [])


if __name__ == "__main__":
    unittest.main()
