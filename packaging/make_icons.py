# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# make_icons.py: rigenera le icone dell'applicazione (PNG, ICO per Windows, ICNS per macOS, SVG) da pdfdesk/icons.py.
# Uso: QT_QPA_PLATFORM=offscreen python packaging/make_icons.py
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from PIL import Image
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtCore import QBuffer, QIODevice, Qt
app = QGuiApplication([])
from pdfdesk.icons import icon

OUT = os.path.join(HERE, "assets"); os.makedirs(OUT, exist_ok=True)


def render(size: int) -> Image.Image:
    pm = icon("app", size).pixmap(size, size)
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    buf = QBuffer(); buf.open(QIODevice.WriteOnly); img.save(buf, "PNG")
    import io
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


sizes = (16, 24, 32, 48, 64, 128, 256, 512)
imgs = {s: render(s) for s in sizes}
for s in (16, 32, 48, 64, 128, 256, 512):
    imgs[s].save(os.path.join(OUT, f"pdfdesk-{s}.png"))
imgs[256].save(os.path.join(OUT, "pdfdesk.png"))
imgs[256].save(os.path.join(OUT, "pdfdesk.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
imgs[512].save(os.path.join(OUT, "pdfdesk.icns"), sizes=[(s, s) for s in (16, 32, 64, 128, 256, 512)])
with open(os.path.join(OUT, "pdfdesk.svg"), "w", encoding="utf-8") as f:
    f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="256" height="256">'
            '<rect x="6" y="4" width="36" height="40" rx="5" fill="#c82828"/>'
            '<g fill="none" stroke="#fff" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M15 14V34M15 14H22A7 5 0 0 1 22 24H15M30 34H36M30 28H36"/></g></svg>')
print("icone scritte in", OUT)
