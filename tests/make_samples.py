# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Genera PDF di prova per i test.
import os, random
import pymupdf as fitz

def make_text_pdf(path, pages=3):
    d = fitz.open()
    for i in range(pages):
        p = d.new_page()
        p.insert_text((72, 100), f"Pagina {i+1}: Ciao mondo àèìòù", fontsize=16)
        p.insert_textbox(fitz.Rect(72, 140, 520, 260), "Questo è un paragrafo di prova con testo selezionabile. " * 4, fontsize=11)
        p.insert_text((72, 300), "Riga segreta: IBAN IT00X0000000000000000000000", fontsize=11)
    d.save(path); d.close()

def make_image_pdf(path, pages=2, size=1800):
    """PDF con grandi immagini rumorose (compressione significativa) e testo."""
    random.seed(1)
    d = fitz.open()
    for i in range(pages):
        pm = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, size, size), False)
        # gradiente + rumore, JPEG ad alta qualità
        for y in range(0, size, 3):
            for x in range(0, size, 3):
                pm.set_rect(fitz.IRect(x, y, x+3, y+3), ((x*255)//size, (y*255)//size, random.randrange(256)))
        jpg = pm.tobytes("jpeg", jpg_quality=95)
        p = d.new_page()
        p.insert_text((72, 60), f"Immagine pesante {i+1}", fontsize=18)
        p.insert_image(fitz.Rect(36, 90, 560, 614), stream=jpg)
    d.save(path); d.close()

if __name__ == "__main__":
    out = os.environ.get("OUT", "/tmp/pdfdesk-samples"); os.makedirs(out, exist_ok=True)
    make_text_pdf(f"{out}/testo.pdf"); make_image_pdf(f"{out}/immagini.pdf"); print(out)


def block_modal_dialogs():
    """Test: le finestre modali statiche (QMessageBox, QFileDialog…) non devono mai restare aperte aspettando un clic che non arriva:
    fanno fallire il test indicando titolo e testo, invece di bloccarlo per sempre (visto su Windows con «Salvataggio non riuscito»)."""
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    def boom(name):
        def f(*a, **k):
            txt = " | ".join(str(x) for x in a[1:4] if isinstance(x, str))
            raise AssertionError(f"finestra modale inattesa {name}: {txt}")
        return staticmethod(f)
    for n in ("critical", "warning", "information", "question", "about"):
        setattr(QMessageBox, n, boom("QMessageBox." + n))
    for n in ("getOpenFileName", "getOpenFileNames", "getSaveFileName", "getExistingDirectory"):
        setattr(QFileDialog, n, boom("QFileDialog." + n))
