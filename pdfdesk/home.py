# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# Pagina «Attività»: si apre all'avvio (se non ci sono file da aprire), quando si chiude l'ultimo documento e con il
# pulsante a forma di casa della barra principale. In alto le attività fondamentali, in basso i PDF recenti.
from __future__ import annotations

import os
import time

import pymupdf as fitz
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from .i18n import tr
from .icons import icon

# chiave, icona, titolo, descrizione. Le attività da «needs_doc» chiedono prima quale PDF aprire.
ACTIVITIES = (
    ("open", "open", "Apri un PDF", "Visualizza, annota e modifica un documento"),
    ("new", "new", "Crea un PDF vuoto", "Parti da una pagina bianca"),
    ("merge", "merge", "Unisci PDF e immagini", "Combina più file in un unico documento"),
    ("scan", "scan", "Crea PDF da scansione", "Acquisisci dallo scanner, con OCR facoltativo"),
    ("form", "form", "Compila un modulo", "Scrivi nei campi e spunta le caselle"),
    ("sign", "sigdig", "Firma un documento", "Firma digitale con certificato o smart card"),
    ("compress", "saveas", "Riduci le dimensioni", "Comprimi immagini e struttura del file"),
    ("standard", "std", "Converti in PDF/A o PDF/X", "Archiviazione a lungo termine o stampa"),
    ("export", "export", "Esporta in Word o immagini", "DOCX, ODT, PNG, JPG, TIFF o testo"),
    ("translate", "translate", "Traduci un PDF", "In un'altra lingua, anche più file insieme"),
    ("verify", "verify", "Verifica le firme", "Controlla integrità e validità delle firme"),
    ("redact", "redact", "Oscura informazioni", "Nascondi in modo permanente testo e immagini"),
)
NEEDS_DOC = {"form", "sign", "compress", "standard", "export", "verify", "redact"}
MAX_RECENT = 10


def _when(path: str) -> str:
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return ""
    if age < 86400:
        return tr("oggi")
    if age < 2 * 86400:
        return tr("ieri")
    return tr("{} giorni fa").format(int(age // 86400))


def _short_dir(path: str) -> str:
    d = os.path.dirname(path)
    home = os.path.expanduser("~")
    if d == home or d.startswith(home + os.sep):
        d = "~" + d[len(home):]
    return d


class _Card(QToolButton):
    """Scheda di un'attività: icona, titolo in grassetto, una riga di spiegazione."""

    def __init__(self, ico: str, title: str, desc: str) -> None:
        super().__init__()
        self.setObjectName("homeCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(72); self.setMinimumWidth(220)
        self.setToolTip(desc); self.setAccessibleName(title)
        h = QHBoxLayout(self); h.setContentsMargins(14, 10, 14, 10); h.setSpacing(12)
        self.ic = QLabel(); self.ic.setFixedSize(34, 34); self._ico = ico
        v = QVBoxLayout(); v.setSpacing(2)
        t = QLabel(title); t.setObjectName("cardTitle")
        d = QLabel(desc); d.setObjectName("cardDesc"); d.setWordWrap(True)
        for w in (self.ic, t, d):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        v.addWidget(t); v.addWidget(d)
        h.addWidget(self.ic, 0, Qt.AlignTop); h.addLayout(v, 1)
        self.refresh_icon()

    def refresh_icon(self) -> None:               # l'icona segue i colori del tema
        self.ic.setPixmap(icon(self._ico).pixmap(32, 32))


class _RecentRow(QToolButton):
    def __init__(self, path: str, thumb: QPixmap) -> None:
        super().__init__()
        self.path = path
        self.setObjectName("homeRecent")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.setMinimumHeight(64)
        self.setToolTip(path); self.setAccessibleName(os.path.basename(path))
        h = QHBoxLayout(self); h.setContentsMargins(10, 6, 10, 6); h.setSpacing(12)
        th = QLabel(); th.setObjectName("recThumb"); th.setFixedSize(QSize(48, 52)); th.setAlignment(Qt.AlignCenter)
        th.setPixmap(thumb)
        v = QVBoxLayout(); v.setSpacing(1)
        t = QLabel(os.path.basename(path)); t.setObjectName("cardTitle")
        d = QLabel("  ·  ".join(x for x in (_short_dir(path), _when(path)) if x)); d.setObjectName("cardDesc")
        for w in (th, t, d):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        v.addStretch(1); v.addWidget(t); v.addWidget(d); v.addStretch(1)
        h.addWidget(th); h.addLayout(v, 1)


class HomePage(QWidget):
    """Pagina «Attività». Segnali: activity(chiave), open_recent(percorso), remove_recent(percorso)."""
    activity = Signal(str)
    open_recent = Signal(str)
    remove_recent = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("home")
        self._thumbs: dict = {}                   # (percorso, data di modifica) -> miniatura
        self.cards: dict = {}
        self.rows: list = []
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(sc)
        inner = QWidget(); inner.setObjectName("homeInner"); sc.setWidget(inner)
        center = QHBoxLayout(inner); center.setContentsMargins(32, 24, 32, 24)
        body = QWidget(); body.setMaximumWidth(1060)
        center.addStretch(1); center.addWidget(body, 100); center.addStretch(1)
        col = QVBoxLayout(body); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(10)
        h1 = QLabel(tr("Attività")); h1.setObjectName("homeH1"); col.addWidget(h1)
        self._section(col, tr("Cosa vuoi fare?"), tr("Scegli un'attività: PDFDesk ti guida passo per passo."))
        grid = QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(12)
        for i, (key, ico, title, desc) in enumerate(ACTIVITIES):
            c = _Card(ico, tr(title), tr(desc))
            c.clicked.connect(self._on_card)
            c.setProperty("activity", key)
            self.cards[key] = c
            grid.addWidget(c, i // 3, i % 3)
        col.addLayout(grid)
        col.addSpacing(18)
        self._section(col, tr("Continua a lavorare"), tr("I documenti aperti di recente."))
        self.recbox = QFrame(); self.recbox.setObjectName("recBox")
        self.rgrid = QGridLayout(self.recbox); self.rgrid.setContentsMargins(8, 8, 8, 8)
        self.rgrid.setHorizontalSpacing(8); self.rgrid.setVerticalSpacing(2)
        self.empty = QLabel(tr("Nessun documento recente: i PDF che apri compariranno qui."))
        self.empty.setObjectName("cardDesc"); self.empty.setContentsMargins(10, 10, 10, 10)
        col.addWidget(self.recbox); col.addWidget(self.empty); col.addStretch(1)

    @staticmethod
    def _section(col, title: str, sub: str) -> None:
        t = QLabel(title); t.setObjectName("homeH2")
        s = QLabel(sub); s.setObjectName("homeSub")
        col.addWidget(t); col.addWidget(s)

    def _on_card(self) -> None:
        self.activity.emit(self.sender().property("activity"))

    # ------------------------------------------------------------ recenti
    def _thumb(self, path: str) -> QPixmap:
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            key = (path, 0)
        pm = self._thumbs.get(key)
        if pm is None:
            pm = self._render_thumb(path)
            self._thumbs[key] = pm
        return pm

    @staticmethod
    def _render_thumb(path: str) -> QPixmap:
        try:
            with fitz.open(path) as d:
                if d.needs_pass or d.page_count == 0:
                    raise ValueError
                r = d[0].rect
                z = min(46 / max(r.width, 1), 50 / max(r.height, 1))
                p = d[0].get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
                img = QImage(p.samples, p.width, p.height, p.stride, QImage.Format_RGB888).copy()
            return QPixmap.fromImage(img)
        except Exception:
            return icon("open").pixmap(32, 32)          # protetto da password o non leggibile

    def set_recent(self, paths: list) -> None:
        for r in self.rows:
            self.rgrid.removeWidget(r); r.deleteLater()
        self.rows = []
        paths = [p for p in paths if p and os.path.isfile(p)][:MAX_RECENT]
        half = (len(paths) + 1) // 2
        for i, p in enumerate(paths):
            r = _RecentRow(p, self._thumb(p))
            r.clicked.connect(self._on_recent)
            r.setContextMenuPolicy(Qt.CustomContextMenu)
            r.customContextMenuRequested.connect(self._recent_menu)
            self.rows.append(r)
            self.rgrid.addWidget(r, i % half, i // half)
        self.recbox.setVisible(bool(paths)); self.empty.setVisible(not paths)

    def _on_recent(self) -> None:
        self.open_recent.emit(self.sender().path)

    def _recent_menu(self, pos) -> None:
        row = self.sender()
        m = QMenu(self)
        m.addAction(tr("Apri"), lambda: self.open_recent.emit(row.path))
        m.addAction(tr("Rimuovi dall'elenco"), lambda: self.remove_recent.emit(row.path))
        m.exec(row.mapToGlobal(pos))

    # ------------------------------------------------------------ aspetto
    def restyle(self) -> None:
        """Colori dal tema corrente (chiamata anche dopo un cambio di tema)."""
        pal = QApplication.instance().palette()
        text = pal.text().color(); hl = pal.highlight().color()
        win, card = pal.window().color().name(), pal.base().color().name()
        sub = f"rgba({text.red()},{text.green()},{text.blue()},0.62)"
        brd = f"rgba({text.red()},{text.green()},{text.blue()},0.22)"
        hov = f"rgba({hl.red()},{hl.green()},{hl.blue()},0.14)"
        self.setStyleSheet(f"""
#homeInner {{ background: {win}; }}
#homeH1 {{ font-size: 26px; font-weight: 600; }}
#homeH2 {{ font-size: 17px; font-weight: 600; padding-top: 6px; }}
#homeSub, #cardDesc {{ color: {sub}; }}
#cardTitle {{ font-weight: 600; font-size: 14px; }}
QToolButton#homeCard {{ background: {card}; border: 1px solid {brd}; border-radius: 10px; }}
QToolButton#homeCard:hover, QToolButton#homeCard:focus {{ border: 2px solid {hl.name()}; }}
#recBox {{ background: {card}; border: 1px solid {brd}; border-radius: 10px; }}
QToolButton#homeRecent {{ background: transparent; border: none; border-radius: 8px; }}
QToolButton#homeRecent:hover, QToolButton#homeRecent:focus {{ background: {hov}; }}
#recThumb {{ border: 1px solid {brd}; background: {card}; }}
""")
        for c in self.cards.values():
            c.refresh_icon()

    def showEvent(self, e) -> None:
        self.restyle()
        super().showEvent(e)
