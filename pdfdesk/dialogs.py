# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# dialogs.py: finestre di dialogo e pannelli laterali.
from __future__ import annotations

import os
import sys
from typing import Optional

from PySide6.QtCore import QEvent, QObject, QPointF, QSettings, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QApplication, QCheckBox, QColorDialog, QComboBox, QDialog as _QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QProgressDialog,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QStackedWidget,
                               QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from . import AUTHOR, CREDITS, VERSION_LINE, __version__, compress, pdfstd, signing, sigstore
from . import fonts as fontlib
from . import textbox
from .core import FONT_NAMES, FONTS
from .icons import app_icon
from .i18n import tr


class QDialog(_QDialog):
    """Base di tutte le finestre di PDFDesk: sempre modale sull'intera applicazione (nessun clic sulla finestra
    principale finché la finestra non viene chiusa)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)


class ModalPlacer(QObject):
    """Fa comparire ogni finestra di dialogo (anche QMessageBox, QInputDialog…) sullo stesso schermo della finestra
    principale, centrata su di essa, e la lega alla principale (transient parent) così che anche sotto Wayland
    il compositor la collochi nella stessa uscita."""

    def __init__(self, main) -> None:
        super().__init__(main)
        self.main = main

    def _owner(self, dlg):
        p = dlg.parentWidget()
        while p is not None:
            if p is self.main:
                return True
            p = p.parentWidget()
        return dlg.parentWidget() is None

    def eventFilter(self, obj, ev) -> bool:
        if ev.type() == QEvent.Show and isinstance(obj, _QDialog) and obj.isWindow() and obj is not self.main:
            try:
                self._place(obj)
            except Exception:
                pass
        return False

    def _place(self, dlg) -> None:
        mw = self.main
        if not mw.isVisible() or not self._owner(dlg):
            return
        mh, dh = mw.windowHandle(), dlg.windowHandle()
        if mh is None or dh is None:
            return
        if dh.transientParent() is None and dh is not mh:
            top = QApplication.activeModalWidget()
            par = top.windowHandle() if top is not None and top is not dlg and top.windowHandle() is not None else mh
            dh.setTransientParent(par)
        scr = mh.screen()
        if scr is not None and dh.screen() is not scr:
            dh.setScreen(scr)
        geo = scr.availableGeometry() if scr is not None else None
        if geo is None:
            return
        fr = dlg.frameGeometry()
        if not geo.intersects(fr) or dlg.parentWidget() is None:
            c = mw.frameGeometry().center()
            x = max(geo.left(), min(c.x() - fr.width() // 2, geo.right() - fr.width()))
            y = max(geo.top(), min(c.y() - fr.height() // 2, geo.bottom() - fr.height()))
            dlg.move(x, y)


def settings() -> QSettings:
    return QSettings(tr("GuidoCauli"), tr("PDFDesk"))


def qcolor(c) -> QColor:
    return QColor.fromRgbF(*c) if c else QColor(Qt.transparent)


def tuple_color(q: QColor) -> tuple[float, float, float]:
    return (q.redF(), q.greenF(), q.blueF())


class ColorButton(QPushButton):
    changed = Signal(object)

    def __init__(self, color=(0, 0, 0), allow_none: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.color = color
        self.allow_none = allow_none
        self.setFixedWidth(52)
        self.clicked.connect(self._pick)
        self._paint()

    def set_color(self, c) -> None:
        self.color = c
        self._paint()

    def _paint(self) -> None:
        pm = QPixmap(32, 14)
        pm.fill(qcolor(self.color) if self.color else QColor(Qt.white))
        if not self.color:
            p = QPainter(pm)
            p.setPen(QPen(QColor(200, 0, 0), 2))
            p.drawLine(0, 13, 31, 0)
            p.end()
        self.setIcon(pm)
        self.setIconSize(QSize(32, 14))

    def _pick(self) -> None:
        c = QColorDialog.getColor(qcolor(self.color) if self.color else QColor(Qt.white), self, tr("Scegli colore"))
        if c.isValid():
            self.color = tuple_color(c)
            self._paint()
            self.changed.emit(self.color)



# ---------------------------------------------------------------------- selettore carattere (base-14 + TTF/OTF)
class FontCombo(QComboBox):
    """Elenco dei caratteri: base-14, font dell'utente e di sistema; «Aggiungi font…» importa TTF/OTF."""
    codeChanged = Signal(str)
    ADD = "__add__"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(150)
        self.setMaxVisibleItems(20)
        self._code = "helv"
        self._n = -1
        self.refill()
        self.activated.connect(self._activated)

    def refill(self) -> None:
        ch = fontlib.choices()
        if len(ch) == self._n:
            return
        self._n = len(ch)
        cur = self._code
        self.blockSignals(True)
        self.clear()
        for label, code in ch:
            self.addItem(label, code)
        self.insertSeparator(self.count())
        self.addItem(tr("Aggiungi font…"), self.ADD)
        self.blockSignals(False)
        self.set_code(cur, emit=False)

    def code(self) -> str:
        return self._code

    def set_code(self, code: str, emit: bool = False) -> None:
        self._code = code or "helv"
        i = self.findData(self._code)
        if i < 0:                                  # font non presente: lo mostra comunque
            self.blockSignals(True)
            self.insertItem(0, fontlib.label_for(self._code) + tr(" (non disponibile)"), self._code)
            self.blockSignals(False)
            i = 0
        self.blockSignals(True)
        self.setCurrentIndex(i)
        self.blockSignals(False)
        if emit:
            self.codeChanged.emit(self._code)

    def _activated(self, i: int) -> None:
        data = self.itemData(i)
        if data == self.ADD:
            paths, _ = QFileDialog.getOpenFileNames(self, tr("Aggiungi font"), "", tr("Font (*.ttf *.otf *.TTF *.OTF)"))
            added = None
            for p in paths:
                try:
                    added = fontlib.add_user_font(p)
                except Exception as ex:
                    QMessageBox.warning(self, tr("Font non valido"), str(ex))
            self._n = -1
            self.refill()
            self.set_code(added or self._code, emit=bool(added))
            return
        self._code = data
        self.codeChanged.emit(data)

    def showPopup(self) -> None:
        self.refill()                              # include i font di sistema quando la scansione è finita
        super().showPopup()


# ---------------------------------------------------------------------- pannello proprietà
class StyleButtons(QWidget):
    """Quattro pulsanti attivabili: grassetto, corsivo, sottolineato, barrato. Il valore è una stringa di lettere «bius»."""
    changed = Signal(str)
    LETTERS = (("b", "B", tr("Grassetto")), ("i", "I", tr("Corsivo")), ("u", "U", tr("Sottolineato")), ("s", "S", tr("Barrato")))

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(2)
        self.btn: dict[str, QToolButton] = {}
        for key, label, tip in self.LETTERS:
            b = QToolButton(); b.setText(label); b.setCheckable(True); b.setToolTip(tip); b.setAutoRaise(False)
            side = max(26, int(self.fontMetrics().height() * 1.7))
            b.setFixedSize(side, side)
            f = b.font(); f.setBold(key == "b"); f.setItalic(key == "i"); f.setUnderline(key == "u"); f.setStrikeOut(key == "s")
            b.setFont(f)
            b.toggled.connect(lambda _on: self._emit())
            lay.addWidget(b)
            self.btn[key] = b
        self._lock = False

    def _emit(self) -> None:
        if not self._lock:
            self.changed.emit(self.style())

    def style(self) -> str:
        return "".join(k for k in "bius" if self.btn[k].isChecked() and self.btn[k].isEnabled())

    def set_style(self, st: str) -> None:
        self._lock = True
        for k, b in self.btn.items():
            b.setChecked(k in (st or ""))
        self._lock = False

    def set_custom_font(self, custom: bool) -> None:
        """Un font TTF/OTF ha un solo file: grassetto e corsivo non sono disponibili, sottolineato e barrato sì."""
        for k in "bi":
            self.btn[k].setEnabled(not custom)
            self.btn[k].setToolTip(tr("Non disponibile con i font TTF/OTF aggiunti (un solo stile per file)") if custom else dict((a, c) for a, _, c in self.LETTERS)[k])


class PropertiesPanel(QWidget):
    """Proprietà dello strumento corrente o dell'annotazione selezionata (barra orizzontale compatta)."""
    changed = Signal(dict)

    def __init__(self, parent=None, compact: bool = False) -> None:
        super().__init__(parent)
        self._lock = False
        self.stroke = ColorButton((0, 0, 0))
        self.fill = ColorButton(None, allow_none=True)
        self.fill_on = QCheckBox(tr("Riempimento"))
        self.width = QDoubleSpinBox(); self.width.setRange(0, 60); self.width.setSingleStep(0.5); self.width.setValue(2)
        self.width.setKeyboardTracking(False)
        self.opacity = QSlider(Qt.Horizontal); self.opacity.setRange(5, 100); self.opacity.setValue(100)
        self.font = FontCombo()
        self.size = QDoubleSpinBox(); self.size.setRange(4, 200); self.size.setValue(12); self.size.setKeyboardTracking(False)
        self.styles_ = StyleButtons()
        tips = ((self.stroke, tr("Colore del tratto / del testo (è anche il bordo della casella)")),
                (self.fill, tr("Colore di riempimento")), (self.fill_on, tr("Attiva o disattiva il riempimento")),
                (self.width, tr("Spessore del tratto in punti")), (self.opacity, tr("Opacità del tratto (5–100%)")),
                (self.font, tr("Carattere del testo (anche TTF/OTF installati o aggiunti)")), (self.size, tr("Dimensione del testo in punti")))
        for w, t in tips:
            w.setToolTip(t)
        if compact:
            self.opacity.setFixedWidth(70)
            self.font.setMinimumWidth(110); self.font.setMaximumWidth(150)
            self.width.setFixedWidth(62); self.size.setFixedWidth(62)
            h = QBoxLayout(QBoxLayout.LeftToRight, self)
            self._box = h
            h.setContentsMargins(4, 0, 4, 0); h.setSpacing(5)
            for label, w in ((None, self.stroke), (None, self.fill_on), (None, self.fill), (tr("Spess."), self.width),
                             (tr("Opac."), self.opacity), (None, self.font), (tr("Dim."), self.size), (None, self.styles_)):
                if label:
                    l = QLabel(label); l.setToolTip(w.toolTip()); h.addWidget(l)
                h.addWidget(w)
            h.addStretch(0)
        else:
            f = QFormLayout(self)
            f.addRow(tr("Colore"), self.stroke)
            fr = QHBoxLayout(); fr.addWidget(self.fill_on); fr.addWidget(self.fill); fr.addStretch()
            f.addRow(fr)
            f.addRow(tr("Spessore"), self.width)
            f.addRow(tr("Opacità"), self.opacity)
            f.addRow(tr("Carattere"), self.font)
            f.addRow(tr("Dimensione"), self.size)
            f.addRow(tr("Stile"), self.styles_)
        self.stroke.changed.connect(lambda c: self._emit(stroke=c))
        self.fill.changed.connect(lambda c: (self.fill_on.setChecked(True), self._emit(fill=c)))
        self.fill_on.toggled.connect(lambda on: self._emit(fill=self.fill.color if on and self.fill.color else (None if not on else (1, 1, 0.8))))
        self.width.valueChanged.connect(lambda v: self._emit(width=v))
        self.opacity.sliderReleased.connect(lambda: self._emit(opacity=self.opacity.value() / 100))
        self.font.codeChanged.connect(lambda c: self._emit(fontname=c))
        self.size.valueChanged.connect(lambda v: self._emit(fontsize=v))
        self.styles_.changed.connect(lambda st: self._emit(style=st))
        self.font.codeChanged.connect(lambda c: self.styles_.set_custom_font(c.startswith("@")))

    def set_vertical(self, vertical: bool) -> None:
        """Barra agganciata ai lati: i controlli si dispongono in colonna."""
        box = getattr(self, "_box", None)
        if box is None:
            return
        box.setDirection(QBoxLayout.TopToBottom if vertical else QBoxLayout.LeftToRight)
        box.setContentsMargins(2, 4, 2, 4) if vertical else box.setContentsMargins(4, 0, 4, 0)
        self.font.setMaximumWidth(110 if vertical else 150); self.font.setMinimumWidth(80 if vertical else 110)
        self.opacity.setFixedWidth(62 if vertical else 70)
        self.adjustSize()

    def _emit(self, **kw) -> None:
        if self._lock:
            return
        if "fill" in kw and kw["fill"] and not self.fill.color:
            self.fill.set_color(kw["fill"])
        self.changed.emit(kw)

    def load(self, style: dict) -> None:
        self._lock = True
        try:
            self.stroke.set_color(style.get("pen", (0, 0, 0)))
            fill = style.get("fill")
            self.fill.set_color(fill)
            self.fill_on.setChecked(bool(fill))
            self.width.setValue(style.get("width", 2.0))
            self.opacity.setValue(int(style.get("opacity", 1.0) * 100))
            self.font.set_code(style.get("fontname", "helv"))
            self.size.setValue(style.get("fontsize", 12.0))
            self.styles_.set_custom_font(str(style.get("fontname", "helv")).startswith("@"))
            self.styles_.set_style(style.get("style", ""))
        finally:
            self._lock = False

    def enable_for(self, tool: str) -> None:
        pen = tool in ("pen", "highlighter", "rect", "ellipse", "line", "arrow", "text", "select", "hl", "ul", "st")
        self.stroke.setEnabled(pen)
        self.width.setEnabled(tool in ("pen", "highlighter", "rect", "ellipse", "line", "arrow", "text", "select"))
        self.opacity.setEnabled(tool in ("pen", "highlighter", "rect", "ellipse", "line", "arrow", "select"))
        shape = tool in ("rect", "ellipse", "text", "select")
        self.fill.setEnabled(shape); self.fill_on.setEnabled(shape)
        txt = tool in ("text", "select", "edittext")
        self.font.setEnabled(txt); self.size.setEnabled(txt); self.styles_.setEnabled(txt)


# ---------------------------------------------------------------------- miniature
class ThumbPanel(QListWidget):
    """Miniature delle pagine: l'ingrandimento segue automaticamente la larghezza della colonna."""
    pageSelected = Signal(int)
    pageMoved = Signal(int, int)
    action = Signal(str, list)
    PAD = 14                 # spazio laterale e tra le miniature
    MAX_W = 420              # larghezza massima di una miniatura

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(110, 150))
        self.setGridSize(QSize(132, 188))
        self.setResizeMode(QListWidget.Adjust)
        self.setLayoutMode(QListWidget.SinglePass)
        self.setUniformItemSizes(True)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.customContextMenuRequested.connect(self._menu)
        self.currentRowChanged.connect(lambda r: r >= 0 and self.pageSelected.emit(r))
        self.model().rowsMoved.connect(self._rows_moved)
        self._lock = False
        self._pix: dict = {}                 # pagina → miniatura a risoluzione piena
        self._timer = QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(60)
        self._timer.timeout.connect(self.relayout)

    def _rows_moved(self, parent, start, end, dest, row) -> None:
        if self._lock:
            return
        self.pageMoved.emit(start, row)

    def set_count(self, n: int) -> None:
        self._lock = True
        self.clear()
        self._pix = {}
        for i in range(n):
            it = QListWidgetItem(str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            it.setSizeHint(self.gridSize())
            self.addItem(it)
        self._lock = False

    # --- ingrandimento automatico
    def thumb_width(self) -> int:
        """Larghezza della miniatura: tutta la colonna, meno i margini (e la barra di scorrimento, già esclusa dal viewport)."""
        return int(max(48, min(self.MAX_W, self.viewport().width() - self.PAD * 2)))

    def relayout(self) -> None:
        w = self.thumb_width()
        ratio = max([p.height() / p.width() for p in self._pix.values() if p.width()] or [1.414])
        h = int(w * min(ratio, 2.2))
        txt = self.fontMetrics().height() + 6
        self.setIconSize(QSize(w, h))
        self.setGridSize(QSize(w + self.PAD * 2, h + txt + self.PAD))
        for i in range(self.count()):                 # dimensione fissa: la posizione non dipende dal formato della singola pagina
            self.item(i).setSizeHint(self.gridSize())
        for i, pm in self._pix.items():
            self._apply(i, pm)
        self.doItemsLayout()                          # ricalcola subito tutte le posizioni con la nuova griglia

    def _apply(self, i: int, pm: QPixmap) -> None:
        if 0 <= i < self.count():
            sz = self.iconSize()
            self.item(i).setIcon(pm.scaled(sz, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._timer.start()

    def set_thumb(self, i: int, pm: QPixmap) -> None:
        if 0 <= i < self.count():
            first = not self._pix
            self._pix[i] = pm
            if first:
                self.relayout()
            else:
                self._apply(i, pm)

    def mark_current(self, i: int) -> None:
        if 0 <= i < self.count() and self.currentRow() != i:
            self._lock = True
            self.setCurrentRow(i, self.selectionModel().SelectionFlag.ClearAndSelect)
            self._lock = False
            self.scrollToItem(self.item(i))

    def selected_pages(self) -> list[int]:
        return sorted(self.row(i) for i in self.selectedItems())

    def _menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        for key, label in (("rot_l", tr("Ruota a sinistra")), ("rot_r", tr("Ruota a destra")), ("dup", tr("Duplica")),
                           ("blank", tr("Inserisci pagina vuota dopo")), ("insert", tr("Inserisci pagine da PDF dopo…")),
                           ("extract", tr("Estrai in un nuovo PDF…")), ("delete", "Elimina")):
            m.addAction(label).setData(key)
        a = m.exec(self.mapToGlobal(pos))
        if a:
            self.action.emit(a.data(), self.selected_pages() or [self.currentRow()])


# ---------------------------------------------------------------------- testo
class TextDialog(QDialog):
    def __init__(self, parent, title: str, text: str = "", fontsize: float = 12, fontname: str = "helv",
                 color=(0, 0, 0), fill=None, show_style: bool = True, style: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 320)
        lay = QVBoxLayout(self)
        self.edit = QPlainTextEdit(text)
        lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        if not fontname.startswith("@"):                       # hebo, tiit… → carattere base + stile
            st = set(style)
            if fontname.endswith(("bo", "bi")):
                st.add("b")
            if fontname.endswith(("it", "bi")):
                st.add("i")
            style = "".join(k for k in "bius" if k in st)
            fontname = textbox.base_code(fontname)
        self.font = FontCombo(); self.font.set_code(fontname)
        self.styles_ = StyleButtons(); self.styles_.set_style(style)
        self.styles_.set_custom_font(fontname.startswith("@"))
        self.font.codeChanged.connect(lambda c: (self.styles_.set_custom_font(c.startswith("@"))))
        self.size = QDoubleSpinBox(); self.size.setRange(4, 200); self.size.setValue(fontsize)
        self.color = ColorButton(color)
        self.fill_on = QCheckBox(tr("Sfondo")); self.fill_on.setChecked(bool(fill))
        self.fill = ColorButton(fill or (1, 1, 0.8), allow_none=False)
        for w in (QLabel(tr("Carattere")), self.font, QLabel(tr("Dim.")), self.size, self.styles_, QLabel(tr("Colore")), self.color, self.fill_on, self.fill):
            row.addWidget(w)
        row.addStretch()
        lay.addLayout(row)
        if not show_style:
            for w in (self.fill_on, self.fill):
                w.hide()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.edit.setFocus()
        self.edit.selectAll()

    def values(self) -> dict:
        return {"text": self.edit.toPlainText(), "fontsize": self.size.value(), "fontname": self.font.code(),
                "style": self.styles_.style(),
                "color": self.color.color, "fill": self.fill.color if self.fill_on.isChecked() else None}


# ---------------------------------------------------------------------- campo di modulo
class FieldTextDialog(QDialog):
    def __init__(self, parent, name: str, value: str, multiline: bool, maxlen: int = 0, password: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Campo «{}»").format(name) if name else tr("Campo"))
        self.resize(420, 220 if multiline else 120)
        lay = QVBoxLayout(self)
        self.multi = multiline
        if multiline:
            self.edit = QPlainTextEdit(value)
        else:
            self.edit = QLineEdit(value)
            if maxlen:
                self.edit.setMaxLength(maxlen)
            if password:
                self.edit.setEchoMode(QLineEdit.Password)
        lay.addWidget(self.edit)
        if maxlen:
            lay.addWidget(QLabel(tr("Massimo {} caratteri").format(maxlen)))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.edit.setFocus()

    def value(self) -> str:
        return self.edit.toPlainText() if self.multi else self.edit.text()


# ---------------------------------------------------------------------- firma disegnata
class SignatureCanvas(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 220)
        self.strokes: list[list[QPointF]] = []
        self.color = QColor(10, 20, 120)
        self.pen_width = 3.0        # NB: non «width», che coprirebbe QWidget.width() e bloccherebbe il disegno
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), Qt.white)
        p.setPen(QPen(QColor(210, 210, 210), 1, Qt.DashLine))
        p.drawLine(20, int(self.height() * 0.72), self.width() - 20, int(self.height() * 0.72))
        self._draw(p)

    def _draw(self, p: QPainter) -> None:
        p.setPen(QPen(self.color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for s in self.strokes:
            if len(s) == 1:
                p.drawPoint(s[0])
            else:
                path = QPainterPath(s[0])
                for pt in s[1:]:
                    path.lineTo(pt)
                p.drawPath(path)

    def mousePressEvent(self, e) -> None:
        self.strokes.append([e.position()])
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self.strokes:
            self.strokes[-1].append(e.position())
            self.update()

    def clear(self) -> None:
        self.strokes.clear()
        self.update()

    def image(self) -> Optional[QImage]:
        if not self.strokes:
            return None
        scale = 2
        img = QImage(self.width() * scale, self.height() * scale, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(scale, scale)
        self._draw(p)
        p.end()
        return sigstore.crop_to_content(img, 8)


class DrawSignatureDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Disegna la tua firma"))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Firma qui con il mouse, la penna o il dito:")))
        self.canvas = SignatureCanvas()
        lay.addWidget(self.canvas)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Spessore")))
        sl = QSlider(Qt.Horizontal); sl.setRange(1, 10); sl.setValue(3)
        sl.valueChanged.connect(lambda v: (setattr(self.canvas, "pen_width", float(v)), self.canvas.update()))
        row.addWidget(sl)
        self.col = ColorButton((10 / 255, 20 / 255, 120 / 255))
        self.col.changed.connect(lambda c: (setattr(self.canvas, "color", qcolor(c)), self.canvas.update()))
        row.addWidget(QLabel(tr("Colore"))); row.addWidget(self.col)
        clr = QPushButton(tr("Cancella")); clr.clicked.connect(self.canvas.clear); row.addWidget(clr)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self) -> None:
        if self.canvas.image() is None:
            QMessageBox.information(self, tr("Firma"), tr("Disegna prima la firma."))
            return
        self.accept()

    def result_image(self) -> Optional[QImage]:
        return self.canvas.image()


class SignatureLibraryDialog(QDialog):
    """Libreria delle firme olografiche: scegli, disegna o importa da immagine."""

    def __init__(self, parent=None, select_mode: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Firme olografiche (immagine)"))
        self.resize(560, 400)
        self.chosen: Optional[str] = None
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Scegli una firma da inserire nel documento oppure creane una nuova.")))
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(200, 80))
        self.list.setGridSize(QSize(220, 110))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.itemDoubleClicked.connect(lambda _: self._use())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn in ((tr("Disegna nuova…"), self._draw), (tr("Da immagine…"), self._import), ("Elimina", self._delete)):
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        if select_mode:
            ok = bb.addButton(tr("Usa questa firma"), QDialogButtonBox.AcceptRole)
            ok.clicked.connect(self._use)
        else:
            bb.setStandardButtons(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._fill()

    def _fill(self) -> None:
        self.list.clear()
        for path in sigstore.list_signatures():
            pm = QPixmap(path)
            canvas = QPixmap(200, 80); canvas.fill(Qt.white)
            p = QPainter(canvas); scaled = pm.scaled(190, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap((200 - scaled.width()) // 2, (80 - scaled.height()) // 2, scaled); p.end()
            it = QListWidgetItem(canvas, "")
            it.setData(Qt.UserRole, path)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _draw(self) -> None:
        d = DrawSignatureDialog(self)
        if d.exec() == QDialog.Accepted and d.result_image() is not None:
            sigstore.add_signature(d.result_image())
            self._fill()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Immagine della firma"), "", tr("Immagini (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"))
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, tr("Firma"), tr("Impossibile leggere l'immagine."))
            return
        if sigstore.has_transparency(img):
            img = sigstore.remove_background(img)           # già trasparente: si ritaglia soltanto
        elif QMessageBox.question(self, tr("Sfondo"), tr("Rendere trasparente lo sfondo chiaro (consigliato per firme su carta bianca)?"),
                                  QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            img = sigstore.remove_background(img)
        else:
            img = sigstore.limit_size(img)
        sigstore.add_signature(img)
        self._fill()

    def _delete(self) -> None:
        it = self.list.currentItem()
        if it and QMessageBox.question(self, tr("Elimina"), tr("Eliminare la firma selezionata?")) == QMessageBox.Yes:
            sigstore.delete_signature(it.data(Qt.UserRole))
            self._fill()

    def _use(self) -> None:
        it = self.list.currentItem()
        if not it:
            QMessageBox.information(self, tr("Firma"), tr("Crea o seleziona una firma."))
            return
        self.chosen = it.data(Qt.UserRole)
        self.accept()


# ---------------------------------------------------------------------- salvataggio / compressione
class SaveDialog(QDialog):
    def __init__(self, parent, default_path: str, signed: bool, orig_size: int = 0, standard: Optional[str] = None, raw=None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QTabWidget
        self.setWindowTitle(tr("Salva con nome / Ottimizza"))
        self.resize(620, 560)
        self.signed = signed
        self._raw = raw                      # callable → bytes del documento attuale (per analisi e stima)
        self._orig = 0
        lay = QVBoxLayout(self)
        prow = QHBoxLayout()
        self.path = QLineEdit(default_path)
        b = QPushButton(tr("Sfoglia…")); b.clicked.connect(self._browse)
        prow.addWidget(QLabel(tr("File di destinazione"))); prow.addWidget(self.path, 1); prow.addWidget(b)
        lay.addLayout(prow)
        tabs = QTabWidget(); lay.addWidget(tabs, 1)

        # ---- scheda «Qualità»
        t1 = QWidget(); v1 = QVBoxLayout(t1)
        f = QFormLayout()
        self.preset = QComboBox()
        for p in compress.PRESETS_UI:
            self.preset.addItem(p.label, p.key)
        self.preset.currentIndexChanged.connect(self._update)
        f.addRow(tr("Qualità / compressione"), self.preset)
        v1.addLayout(f)
        self.desc = QLabel(); self.desc.setWordWrap(True); self.desc.setStyleSheet("color: gray")
        v1.addWidget(self.desc)
        self.gray = QCheckBox(tr("Immagini in scala di grigi"))
        self.meta = QCheckBox(tr("Rimuovi metadati (autore, titolo, XMP)"))
        self.fonts = QCheckBox(tr("Riduci i font incorporati ai soli caratteri usati"))
        for c in (self.gray, self.meta, self.fonts):
            v1.addWidget(c)
        self.std = StandardPicker(self, StandardDialog._key_for(standard))
        self.std.changed.connect(self._update)
        v1.addWidget(self.std)
        self.std_note = QLabel(tr("PDF/A e PDF/X impongono parametri obbligatori (immagini, colori, font, metadati): la compressione "
                               "è decisa dalla conversione e le opzioni di questa finestra sono disattivate."))
        self.std_note.setWordWrap(True); self.std_note.setStyleSheet("color: #8a6d00")
        v1.addWidget(self.std_note)
        note = QLabel(tr("Il testo resta sempre testo selezionabile e ricercabile: la compressione agisce solo sulle immagini e sulla struttura del file."))
        note.setWordWrap(True)
        v1.addWidget(note)
        self.warn = QLabel(tr("⚠ Questo PDF contiene firme digitali. Ricomprimerlo riscrive il file e le firme esistenti diventeranno NON valide. "
                           "Per mantenerle valide scegli «Originale»; per comprimere e firmare usa Firma → Firma digitale (comprime prima, poi firma)."))
        self.warn.setWordWrap(True); self.warn.setStyleSheet("color: #b00020")
        self.ack = QCheckBox(tr("Ho capito: invalida le firme esistenti"))
        v1.addWidget(self.warn); v1.addWidget(self.ack)
        v1.addStretch()
        tabs.addTab(t1, tr("Qualità"))

        # ---- scheda «Avanzate»
        t2 = QWidget(); v2 = QVBoxLayout(t2)
        self.g_img = QGroupBox(tr("Immagini"))
        fi = QFormLayout(self.g_img)
        self.resample = QCheckBox(tr("Ricampiona le immagini troppo grandi"))
        self.thr = QSpinBox(); self.thr.setRange(36, 1200); self.thr.setSuffix(tr(" dpi")); self.thr.setToolTip(tr("Si ricampionano solo le immagini sopra questa risoluzione"))
        self.target = QSpinBox(); self.target.setRange(36, 600); self.target.setSuffix(tr(" dpi")); self.target.setToolTip(tr("Risoluzione di arrivo"))
        self.quality = QSpinBox(); self.quality.setRange(1, 100); self.quality.setToolTip(tr("Qualità JPEG: 100 = massima, 1 = minima"))
        self.k_color = QCheckBox(tr("a colori")); self.k_gray = QCheckBox(tr("in grigio")); self.k_bw = QCheckBox(tr("bianco e nero (1 bit)"))
        kr = QHBoxLayout()
        for c in (self.k_color, self.k_gray, self.k_bw):
            c.setChecked(True); kr.addWidget(c)
        self.lossy = QCheckBox(tr("Ricomprimi con perdita (JPEG)")); self.lossy.setChecked(True)
        self.lossless = QCheckBox(tr("Ricomprimi senza perdita (Flate)")); self.lossless.setChecked(True)
        fi.addRow(self.resample)
        fi.addRow(tr("Solo se sopra"), self.thr)
        fi.addRow(tr("Risoluzione di arrivo"), self.target)
        fi.addRow(tr("Qualità JPEG"), self.quality)
        fi.addRow(tr("Tipi di immagine"), kr)
        fi.addRow(self.lossy); fi.addRow(self.lossless)
        v2.addWidget(self.g_img)
        self.g_str = QGroupBox(tr("Struttura e pulizia"))
        fs = QFormLayout(self.g_str)
        self.garbage = QComboBox()
        for lab, val in ((tr("Automatico"), None), (tr("Nessuna"), 0), (tr("Base: oggetti inutilizzati"), 1), (tr("Media: + oggetti compattati"), 2),
                         (tr("Completa: + oggetti duplicati"), 4)):
            self.garbage.addItem(lab, val)
        self.clean = QCheckBox(tr("Normalizza i flussi di contenuto delle pagine"))
        self.objstm = QComboBox()
        for lab, val in ((tr("Automatico"), None), (tr("Sì (file più piccolo; richiede PDF 1.5+)"), True), (tr("No (massima compatibilità)"), False)):
            self.objstm.addItem(lab, val)
        self.thumbs = QCheckBox(tr("Elimina le miniature incorporate"))
        self.attach = QCheckBox(tr("Elimina gli allegati incorporati"))
        self.js = QCheckBox(tr("Elimina JavaScript e azioni automatiche"))
        self.lin = QCheckBox(tr("Ottimizza per la visualizzazione web (linearizza)"))
        fs.addRow(tr("Pulizia degli oggetti"), self.garbage)
        fs.addRow(tr("Flussi di oggetti"), self.objstm)
        for c in (self.clean, self.thumbs, self.attach, self.js, self.lin):
            fs.addRow(c)
        v2.addWidget(self.g_str)
        v2.addStretch()
        tabs.addTab(t2, tr("Avanzate"))

        # ---- scheda «Analisi e stima»
        t3 = QWidget(); v3 = QVBoxLayout(t3)
        row = QHBoxLayout()
        self.b_an = QPushButton(tr("Analizza il file")); self.b_an.clicked.connect(self._analyze)
        self.b_est = QPushButton(tr("Stima la dimensione con queste opzioni")); self.b_est.clicked.connect(self._estimate)
        row.addWidget(self.b_an); row.addWidget(self.b_est); row.addStretch()
        v3.addLayout(row)
        self.report = QPlainTextEdit(); self.report.setReadOnly(True)
        self.report.setPlaceholderText(tr("«Analizza» mostra cosa occupa spazio (immagini, font, contenuto…); «Stima» esegue la compressione "
                                       "e mostra la dimensione risultante senza salvare nulla."))
        v3.addWidget(self.report, 1)
        tabs.addTab(t3, tr("Analisi e stima"))
        if raw is None:
            self.b_an.setEnabled(False); self.b_est.setEnabled(False)

        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.accepted.connect(self._ok); self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)
        for w in (self.resample, self.k_color, self.k_gray, self.k_bw):
            w.toggled.connect(self._update)
        self._load_preset()
        self._update()

    def _browse(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, tr("Salva PDF"), self.path.text(), tr("PDF (*.pdf)"))
        if p:
            self.path.setText(p if p.lower().endswith(".pdf") else p + ".pdf")

    def _load_preset(self) -> None:
        """Mostra nei controlli i valori del preset scelto (modificabili solo con «Personalizzata»)."""
        key = self.preset.currentData()
        if key == "custom":
            return
        thr, target, q = compress.resolve(compress.SaveOptions(key))
        self.resample.setChecked(thr is not None)
        self.thr.setValue(thr or 200); self.target.setValue(target or 150); self.quality.setValue(q or 75)

    def _update(self) -> None:
        key = self.preset.currentData()
        std = hasattr(self, "std") and self.std.key()
        if self.sender() is self.preset:
            self._load_preset()
        custom = key == "custom" and not std
        self.desc.setText(compress.PRESET_BY_KEY[key].description if key in compress.PRESET_BY_KEY else compress.CUSTOM.description)
        self.resample.setEnabled(custom)
        self.thr.setEnabled(custom and self.resample.isChecked())
        self.target.setEnabled(custom and self.resample.isChecked())
        for w in (self.quality, self.k_color, self.k_gray, self.k_bw, self.lossy, self.lossless):
            w.setEnabled(custom and (self.resample.isChecked() or w in (self.k_color, self.k_gray, self.k_bw, self.lossy, self.lossless)))
        # i parametri obbligatori degli standard (PDF/A, PDF/X) escludono ogni scelta di compressione
        self.preset.setEnabled(not std)
        for w in (self.gray, self.fonts, self.g_str, self.g_img):
            w.setEnabled(not std)
        if std:
            self.preset.blockSignals(True); self.preset.setCurrentIndex(self.preset.findData("original")); self.preset.blockSignals(False)
            self.gray.setChecked(False); self.fonts.setChecked(False)
            self.meta.setChecked(False); self.meta.setEnabled(False)       # i metadati XMP sono obbligatori negli standard
        elif hasattr(self, "std"):
            self.meta.setEnabled(True)
        if hasattr(self, "std_note"):
            self.std_note.setVisible(bool(std))
            self.b_est.setEnabled(self._raw is not None and not std)
        danger = self.signed and (key != "original" or bool(std) or self._has_extras())
        self.warn.setVisible(danger); self.ack.setVisible(danger)

    def _has_extras(self) -> bool:
        return any(c.isChecked() for c in (self.clean, self.thumbs, self.attach, self.js, self.lin, self.gray, self.meta, self.fonts)) \
            or self.garbage.currentData() not in (None, 1) or self.objstm.currentData() is not None

    def _ok(self) -> None:
        if not self.path.text().strip():
            return
        if not self.std.validate():
            return
        if self.signed and self.warn.isVisible() and not self.ack.isChecked():
            QMessageBox.warning(self, tr("Firme digitali"), tr("Conferma di voler invalidare le firme esistenti, oppure scegli «Originale» senza altre opzioni."))
            return
        self.accept()

    def preserves_signatures(self) -> bool:
        """True se le opzioni scelte non riscrivono il file (le firme restano valide)."""
        return self.preset.currentData() == "original" and not self.std.key() and not self._has_extras()

    def options(self) -> compress.SaveOptions:
        std = self.std.key()
        if std:                                   # parametri obbligatori: solo la conversione
            return compress.SaveOptions("original", False, False, False, std, self.std.icc_path())
        key = self.preset.currentData()
        o = compress.SaveOptions(key, self.gray.isChecked(), self.meta.isChecked(), self.fonts.isChecked(), None, None)
        o.garbage = self.garbage.currentData(); o.objstms = self.objstm.currentData(); o.clean_streams = self.clean.isChecked()
        o.drop_thumbnails = self.thumbs.isChecked(); o.drop_attachments = self.attach.isChecked(); o.drop_javascript = self.js.isChecked()
        o.linearize = self.lin.isChecked()
        o.kinds = (self.k_color.isChecked(), self.k_gray.isChecked(), self.k_bw.isChecked())
        o.lossy = self.lossy.isChecked(); o.lossless = self.lossless.isChecked()
        if key == "custom":
            o.dpi_threshold = self.thr.value() if self.resample.isChecked() else None
            o.dpi_target = self.target.value(); o.quality = self.quality.value()
        return o

    def _bg(self, fn, text: str):
        p = self.parent()
        return p.run_bg(fn, text) if hasattr(p, "run_bg") else fn()

    def _analyze(self) -> None:
        raw = self._raw()
        self._orig = len(raw)
        try:
            a = self._bg(lambda: compress.analyze(raw), tr("Analisi in corso…"))
        except Exception as e:
            self.report.setPlainText(tr("Analisi non riuscita: {}").format(e))
            return
        self.report.setPlainText(compress.format_analysis(a))

    def _estimate(self) -> None:
        raw = self._raw()
        o = self.options()
        try:
            n = len(self._bg(lambda: compress.optimize_bytes(raw, o), tr("Stima in corso…")))
        except Exception as e:
            self.report.appendPlainText(f"Stima non riuscita: {e}")
            return
        before = len(raw)
        self.report.appendPlainText(f"\nStima con le opzioni attuali: {compress.human_size(before)} → {compress.human_size(n)} "
                                    f"({(1 - n / before) * 100:+.0f}% di risparmio)" if before else "")


# ---------------------------------------------------------------------- scelta dello standard PDF/A, PDF/X
class StandardPicker(QWidget):
    """Elenco «Nessuno / PDF/A / PDF/X» con profilo ICC facoltativo per la stampa."""
    changed = Signal()

    def __init__(self, parent=None, current: str = "") -> None:
        super().__init__(parent)
        lay = QFormLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItem(tr("Nessuno (PDF normale)"), None)
        have = pdfstd.gs_available()
        for k, st in pdfstd.STANDARDS.items():
            self.combo.addItem(f"{st.label} — {st.note}", k)
            if not have:
                self.combo.model().item(self.combo.count() - 1).setEnabled(False)
        icc_row = QHBoxLayout()
        self.icc = QLineEdit(); self.icc.setPlaceholderText(tr("profilo ICC di stampa (.icc/.icm) — vuoto: CMYK generico di Ghostscript"))
        bb = QPushButton(tr("Sfoglia…")); bb.clicked.connect(self._browse_icc)
        icc_row.addWidget(self.icc, 1); icc_row.addWidget(bb)
        self.icc_box = QWidget(); il = QHBoxLayout(self.icc_box); il.setContentsMargins(0, 0, 0, 0)
        il.addWidget(self.icc, 1); il.addWidget(bb)
        lay.addRow(tr("Conformità"), self.combo)
        lay.addRow(tr("Profilo colore"), self.icc_box)
        self.hint = QLabel(); self.hint.setWordWrap(True); self.hint.setStyleSheet("color: gray")
        lay.addRow(self.hint)
        if not have:
            self.hint.setText(tr("Ghostscript non trovato: la conversione a PDF/A e PDF/X non è disponibile (è incluso nei pacchetti ufficiali)."))
        self.combo.currentIndexChanged.connect(self._upd)
        i = self.combo.findData(current)
        if i >= 0:
            self.combo.setCurrentIndex(i)
        self._upd()

    def _browse_icc(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("Profilo colore ICC"), self.icc.text(), tr("Profili ICC (*.icc *.icm);;Tutti i file (*)"))
        if p:
            self.icc.setText(p)

    def _upd(self) -> None:
        k = self.combo.currentData()
        st = pdfstd.STANDARDS.get(k) if k else None
        self.icc_box.setVisible(bool(st and st.family == "X"))
        if st:
            extra = (tr("Il documento viene convertito in RGB con profilo sRGB; annotazioni e moduli sono appiattiti, "
                     "i font incorporati, le trasparenze portate su sfondo bianco se non ammesse.") if st.family == "A" else
                     tr("Il documento viene convertito in CMYK; per la stampa vera scegli il profilo del tuo stampatore."))
            self.hint.setText(extra)
        elif pdfstd.gs_available():
            self.hint.setText("")
        self.changed.emit()

    def key(self) -> Optional[str]:
        return self.combo.currentData()

    def icc_path(self) -> Optional[str]:
        return (self.icc.text().strip() or None) if self.icc_box.isVisible() else None

    def validate(self) -> bool:
        p = self.icc_path()
        if p and not os.path.isfile(p):
            QMessageBox.warning(self, tr("Profilo colore"), tr("Il file del profilo ICC non esiste."))
            return False
        return True


class StandardDialog(QDialog):
    """Mostra lo standard dichiarato dal documento e ne verifica la conformità."""
    def __init__(self, parent, data_fn, declared: Optional[str], signed: bool) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Conformità PDF/A e PDF/X"))
        self.resize(640, 480)
        self.data_fn = data_fn
        self.convert_requested = False
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Standard dichiarato dal documento: <b>{}</b>").format(declared or 'nessuno')))
        self.pick = StandardPicker(self, self._key_for(declared))
        lay.addWidget(self.pick)
        self.out = QPlainTextEdit(); self.out.setReadOnly(True)
        lay.addWidget(self.out, 1)
        v = pdfstd.find_verapdf()
        lay.addWidget(self._note(tr("Controllo interno") + (tr(" + veraPDF (installato)") if v else "") +
                                 tr(". Per PDF/X non esiste un validatore libero incluso: per la stampa professionale ricontrolla con il preflight dello stampatore.")))
        if signed:
            lay.addWidget(self._note(tr("Il documento è firmato: convertirlo invaliderebbe le firme. Converti prima, firma dopo.")))
        row = QHBoxLayout()
        self.b_check = QPushButton(tr("Verifica")); self.b_check.clicked.connect(self._check)
        self.b_conv = QPushButton(tr("Converti e salva con nome…")); self.b_conv.clicked.connect(self._convert)
        self.b_conv.setEnabled(not signed)
        row.addWidget(self.b_check); row.addStretch(); row.addWidget(self.b_conv)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Close); bb.rejected.connect(self.reject); bb.accepted.connect(self.accept)
        lay.addWidget(bb)

    @staticmethod
    def _note(t: str) -> QLabel:
        l = QLabel(t); l.setWordWrap(True); l.setStyleSheet("color: gray"); return l

    @staticmethod
    def _key_for(declared: Optional[str]) -> Optional[str]:
        if not declared:
            return None
        d = declared.lower()
        for k, st in pdfstd.STANDARDS.items():
            if st.label.lower().split(":")[0] == d or st.label.lower() == d:
                return k
        return {"pdf/x-1:2001": "pdfx-1a", "pdf/x-1a:2001": "pdfx-1a", "pdf/x-3:2002": "pdfx-3", "pdf/x-4": "pdfx-4"}.get(d)

    def _check(self) -> None:
        k = self.pick.key()
        if not k:
            self.out.setPlainText(tr("Scegli lo standard da verificare."))
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            rep = pdfstd.check(self.data_fn(), k)
            self.out.setPlainText(rep.text())
        except Exception as e:
            self.out.setPlainText(tr("Verifica non riuscita: {}").format(e))
        finally:
            QApplication.restoreOverrideCursor()

    def _convert(self) -> None:
        if not self.pick.key():
            self.out.setPlainText(tr("Scegli lo standard di destinazione."))
            return
        if self.pick.validate():
            self.convert_requested = True
            self.accept()

    def choice(self) -> tuple[Optional[str], Optional[str]]:
        return self.pick.key(), self.pick.icc_path()


# ---------------------------------------------------------------------- certificato
class CertDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Crea certificato di firma autofirmato"))
        self.resize(480, 300)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.cn = QLineEdit(); self.org = QLineEdit(); self.mail = QLineEdit()
        self.pw = QLineEdit(); self.pw.setEchoMode(QLineEdit.Password)
        self.pw2 = QLineEdit(); self.pw2.setEchoMode(QLineEdit.Password)
        self.years = QSpinBox(); self.years.setRange(1, 30); self.years.setValue(5)
        self.path = QLineEdit(); b = QPushButton(tr("Sfoglia…")); b.clicked.connect(self._browse)
        r = QHBoxLayout(); r.addWidget(self.path, 1); r.addWidget(b)
        f.addRow(tr("Nome e cognome"), self.cn); f.addRow(tr("Organizzazione"), self.org); f.addRow(tr("E-mail"), self.mail)
        f.addRow(tr("Password del file"), self.pw); f.addRow(tr("Ripeti password"), self.pw2); f.addRow(tr("Validità (anni)"), self.years)
        f.addRow(tr("Salva come (.p12)"), r)
        lay.addLayout(f)
        n = QLabel(tr("Un certificato autofirmato garantisce l'integrità del documento ma i lettori PDF lo segnalano come «non attendibile». "
                   "Per firme con valore legale (FEA/FEQ/CAdES) serve un certificato di un prestatore qualificato (es. smart card o firma remota)."))
        n.setWordWrap(True); n.setStyleSheet("color: gray")
        lay.addWidget(n)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _browse(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, tr("Certificato"), self.path.text(), tr("PKCS#12 (*.p12 *.pfx)"))
        if p:
            self.path.setText(p if p.lower().endswith((".p12", ".pfx")) else p + ".p12")

    def _ok(self) -> None:
        if not self.cn.text().strip() or not self.path.text().strip():
            QMessageBox.warning(self, tr("Certificato"), tr("Nome e percorso sono obbligatori."))
            return
        if self.pw.text() != self.pw2.text():
            QMessageBox.warning(self, tr("Certificato"), tr("Le password non coincidono."))
            return
        try:
            signing.create_self_signed_p12(self.path.text(), self.pw.text(), self.cn.text().strip(), self.org.text().strip(),
                                           self.mail.text().strip(), self.years.value() * 365)
        except Exception as e:
            QMessageBox.critical(self, tr("Certificato"), str(e))
            return
        self.accept()


# ---------------------------------------------------------------------- firma digitale
class SignDialog(QDialog):
    def __init__(self, parent, default_out: str, page_count: int, signed: bool, in_field: bool = False, standard: Optional[str] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Firma digitale (PAdES)"))
        self.resize(560, 520)
        s = settings()
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.src = QComboBox(); self.src.addItem(tr("Certificato su file (.p12/.pfx)"), "file"); self.src.addItem(tr("Smart card / token USB"), "card")
        f.addRow(tr("Firma con"), self.src)
        self.cert = QLineEdit(s.value("sign/cert", "")); cb = QPushButton(tr("Sfoglia…")); cb.clicked.connect(self._browse_cert)
        nb = QPushButton(tr("Crea…")); nb.setToolTip(tr("Crea un certificato autofirmato")); nb.clicked.connect(self._new_cert)
        cr = QHBoxLayout(); cr.addWidget(self.cert, 1); cr.addWidget(cb); cr.addWidget(nb)
        self.pw = QLineEdit(); self.pw.setEchoMode(QLineEdit.Password)
        self.file_box = QWidget(); fl = QFormLayout(self.file_box); fl.setContentsMargins(0, 0, 0, 0)
        fl.addRow(tr("Certificato"), cr); fl.addRow(tr("Password"), self.pw)
        f.addRow(self.file_box)
        # --- smart card (PKCS#11)
        self.lib = QComboBox(); self.lib.setEditable(True)
        for p in signing.pkcs11_candidates():
            self.lib.addItem(p)
        last = s.value("sign/pkcs11", "")
        if last:
            self.lib.setEditText(last)
        elif not self.lib.count():
            self.lib.setEditText("")
            self.lib.lineEdit().setPlaceholderText(tr("modulo PKCS#11 del produttore (es. opensc-pkcs11.so / bit4ipki.dll)"))
        lb = QPushButton(tr("Sfoglia…")); lb.clicked.connect(self._browse_lib)
        rb = QPushButton(tr("Rileva")); rb.setToolTip(tr("Legge le schede inserite e i certificati di firma")); rb.clicked.connect(self._detect)
        lr = QHBoxLayout(); lr.addWidget(self.lib, 1); lr.addWidget(lb); lr.addWidget(rb)
        self.card_cert = QComboBox(); self.card_cert.setMinimumWidth(280)
        self.pin = QLineEdit(); self.pin.setEchoMode(QLineEdit.Password)
        self.pinpad = QCheckBox(tr("Digito il PIN sul lettore (pinpad)"))
        self.pinpad.toggled.connect(lambda on: self.pin.setEnabled(not on))
        self.card_box = QWidget(); cl = QFormLayout(self.card_box); cl.setContentsMargins(0, 0, 0, 0)
        cl.addRow(tr("Modulo PKCS#11"), lr); cl.addRow(tr("Certificato"), self.card_cert); cl.addRow(tr("PIN"), self.pin); cl.addRow(self.pinpad)
        f.addRow(self.card_box)
        self.src.currentIndexChanged.connect(self._src_changed); self._src_changed()
        self.reason = QLineEdit(s.value("sign/reason", "")); self.loc = QLineEdit(s.value("sign/loc", ""))
        f.addRow(tr("Motivo"), self.reason); f.addRow(tr("Luogo"), self.loc)
        lay.addLayout(f)
        self.visible = QCheckBox(tr("Firma visibile (riquadro sulla pagina)"))
        lay.addWidget(self.visible)
        vf = QFormLayout()
        self.page = QSpinBox(); self.page.setRange(1, max(page_count, 1)); self.page.setValue(page_count)
        self.use_img = QCheckBox(tr("Includi firma olografica (immagine) nel riquadro"))
        self.img_btn = QPushButton(tr("Scegli firma…")); self.img_btn.clicked.connect(self._pick_img)
        self.img_path: Optional[str] = None
        self.img_lbl = QLabel("")
        self.show_text = QCheckBox(tr("Mostra testo (firmatario e data)")); self.show_text.setChecked(True)
        vf.addRow(tr("Pagina"), self.page); vf.addRow(self.use_img, self.img_btn); vf.addRow("", self.img_lbl); vf.addRow(self.show_text)
        self.vbox = QWidget(); self.vbox.setLayout(vf); lay.addWidget(self.vbox)
        self.visible.toggled.connect(self.vbox.setEnabled); self.vbox.setEnabled(False)
        if in_field:                                   # firma in un campo del modulo: il riquadro è quello del campo
            self.visible.setChecked(True); self.visible.setEnabled(False); self.page.setEnabled(False)
        g = QFormLayout()
        self.preset = QComboBox()
        for p in compress.PRESETS:
            self.preset.addItem(p.label, p.key)
        g.addRow(tr("Comprimi prima di firmare"), self.preset)
        self.std = StandardPicker(self, StandardDialog._key_for(standard) if not signed else None)
        if signed or in_field:                         # convertire cancellerebbe le firme esistenti / il campo firma stesso
            self.std.setEnabled(False)
        g.addRow(self.std)
        self.tsa = QLineEdit(s.value("sign/tsa", "")); self.tsa.setPlaceholderText(tr("opzionale: URL server marca temporale (RFC 3161)"))
        g.addRow(tr("Marca temporale"), self.tsa)
        po = QHBoxLayout(); self.out = QLineEdit(default_out); ob = QPushButton(tr("Sfoglia…")); ob.clicked.connect(self._browse_out)
        po.addWidget(self.out, 1); po.addWidget(ob)
        g.addRow(tr("Salva firmato come"), po)
        lay.addLayout(g)
        if signed:
            self.preset.setEnabled(False)
            lay.addWidget(self._note(tr("Il documento è già firmato: verrà aggiunta una firma successiva senza ricomprimere (le firme esistenti restano valide).")))
        lay.addWidget(self._note(tr("La firma digitale viene applicata per ultima: dopo la firma il file non va più modificato, altrimenti la firma risulta non valida.")))
        lay.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @staticmethod
    def _note(t: str) -> QLabel:
        l = QLabel(t); l.setWordWrap(True); l.setStyleSheet("color: gray"); return l

    def _src_changed(self) -> None:
        card = self.src.currentData() == "card"
        self.file_box.setVisible(not card); self.card_box.setVisible(card)

    def _browse_lib(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("Modulo PKCS#11"), self.lib.currentText(), tr("Librerie (*.dll *.so *.dylib *.so.*);;Tutti i file (*)"))
        if p:
            self.lib.setEditText(p)

    def _detect(self) -> None:
        self.card_cert.clear()
        try:
            toks = signing.list_tokens(self.lib.currentText().strip())
        except signing.SigningError as e:
            QMessageBox.warning(self, tr("Smart card"), str(e))
            return
        n = 0
        for t in toks:
            for c in t.certs:
                self.card_cert.addItem(f"{c.subject}  —  {t.label or 'scheda'}", (t.label, t.serial, c.cert_id))
                n += 1
        if not n:
            QMessageBox.information(self, tr("Smart card"), tr("Nessuna scheda con certificati trovata.\nInserisci la scheda nel lettore e riprova, oppure verifica il modulo PKCS#11."))

    def card_params(self) -> dict:
        label, serial, cid = self.card_cert.currentData()
        return dict(pkcs11_lib=self.lib.currentText().strip(), pkcs11_token_label=label or None, pkcs11_token_serial=serial or None,
                    pkcs11_cert_id=cid or None, pkcs11_pin=self.pin.text() or None, pkcs11_pinpad=self.pinpad.isChecked())

    def _browse_cert(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, tr("Certificato"), self.cert.text(), tr("PKCS#12 (*.p12 *.pfx)"))
        if p:
            self.cert.setText(p)

    def _new_cert(self) -> None:
        d = CertDialog(self)
        if d.exec() == QDialog.Accepted:
            self.cert.setText(d.path.text()); self.pw.setText(d.pw.text())

    def _browse_out(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, tr("Salva PDF firmato"), self.out.text(), tr("PDF (*.pdf)"))
        if p:
            self.out.setText(p if p.lower().endswith(".pdf") else p + ".pdf")

    def _pick_img(self) -> None:
        d = SignatureLibraryDialog(self)
        if d.exec() == QDialog.Accepted and d.chosen:
            self.img_path = d.chosen; self.use_img.setChecked(True)
            self.img_lbl.setText(os.path.basename(d.chosen))

    def _ok(self) -> None:
        card = self.src.currentData() == "card"
        if card:
            if self.card_cert.currentIndex() < 0:
                QMessageBox.warning(self, tr("Firma"), tr("Premi «Rileva» e scegli il certificato della smart card."))
                return
            if not self.pinpad.isChecked() and not self.pin.text():
                QMessageBox.warning(self, tr("Firma"), tr("Inserisci il PIN della smart card."))
                return
        elif not os.path.isfile(self.cert.text()):
            QMessageBox.warning(self, tr("Firma"), tr("Seleziona un certificato valido."))
            return
        if not self.out.text().strip():
            return
        if self.std.isEnabled() and not self.std.validate():
            return
        if self.visible.isChecked() and self.use_img.isChecked() and not self.img_path:
            QMessageBox.warning(self, tr("Firma"), tr("Scegli l'immagine della firma olografica."))
            return
        if not card:
            try:
                signing.load_signer(self.cert.text(), self.pw.text())
            except signing.SigningError as e:
                QMessageBox.warning(self, tr("Firma"), str(e))
                return
        s = settings(); s.setValue("sign/pkcs11", self.lib.currentText()); s.setValue("sign/cert", self.cert.text()); s.setValue("sign/reason", self.reason.text())
        s.setValue("sign/loc", self.loc.text()); s.setValue("sign/tsa", self.tsa.text())
        self.accept()


class VerifyDialog(QDialog):
    """Elenco delle firme + dettaglio completo e copiabile della firma selezionata."""

    def __init__(self, parent, statuses: list[signing.SigStatus]) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Verifica firme digitali"))
        self.resize(900, 640)
        self.statuses = statuses
        lay = QVBoxLayout(self)
        self.table = None
        self.detail = None
        if not statuses:
            lay.addWidget(QLabel(tr("Nessuna firma digitale nel documento.")))
        else:
            t = QTableWidget(len(statuses), 5)
            t.setHorizontalHeaderLabels([tr("Campo"), tr("Firmatario"), tr("Integra"), tr("Attendibile"), tr("Copertura")])
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.setSelectionMode(QAbstractItemView.SingleSelection)
            t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            for r, s in enumerate(statuses):
                cov = tr("tutto il file") if s.coverage == "ENTIRE_FILE" else (tr("modificato dopo la firma") if s.modified_after else s.coverage)
                vals = [s.field, s.signer, "sì" if s.intact and s.valid else "NO", "sì" if s.trusted else "no", cov]
                for c, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    if c == 2:
                        it.setForeground(QColor(0, 130, 0) if v == "sì" else QColor(200, 0, 0))
                    t.setItem(r, c, it)
            t.resizeColumnsToContents()
            t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            t.setMaximumHeight(170)
            lay.addWidget(t)
            self.table = t
            self.detail = QPlainTextEdit(); self.detail.setReadOnly(True)
            self.detail.setLineWrapMode(QPlainTextEdit.NoWrap)
            f = self.detail.font(); f.setFamily("monospace"); f.setStyleHint(f.StyleHint.Monospace); self.detail.setFont(f)
            lay.addWidget(self.detail, 1)
            t.itemSelectionChanged.connect(self._show)
            t.selectRow(0)
            self._show()
            n = QLabel(tr("«Integra»: il contenuto firmato non è stato alterato. «Attendibile»: il certificato risale a un'autorità "
                       "presente nel tuo archivio fiduciario (un certificato autofirmato risulta non attendibile)."))
            n.setWordWrap(True); n.setStyleSheet("color: gray"); lay.addWidget(n)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        if statuses:
            b1 = bb.addButton(tr("Copia dettagli"), QDialogButtonBox.ActionRole)
            b1.clicked.connect(lambda: QApplication.clipboard().setText(self.detail.toPlainText()))
            b2 = bb.addButton(tr("Copia tutte"), QDialogButtonBox.ActionRole)
            b2.clicked.connect(lambda: QApplication.clipboard().setText("\n\n".join(signing.describe_status(s) for s in statuses)))
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        lay.addWidget(bb)

    def _show(self) -> None:
        r = self.table.currentRow()
        if 0 <= r < len(self.statuses):
            self.detail.setPlainText(signing.describe_status(self.statuses[r]))


class AboutDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Informazioni su PDFDesk"))
        self.setMinimumSize(620, 460); self.resize(680, 520)
        lay = QVBoxLayout(self)
        ic = QLabel(); ic.setPixmap(app_icon().pixmap(72, 72)); ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        t = QLabel(tr("<h2 align='center'>PDFDesk</h2><p align='center'>{}<br>versione {}</p><p>Visualizza, annota, redigi, firma e comprimi PDF su Windows, Linux e macOS.</p><p>Licenza AGPL-3.0-or-later. Componenti: PyMuPDF (AGPL), Qt/PySide6 (LGPL), pyHanko (MIT).</p>").format(AUTHOR, __version__))
        t.setWordWrap(True); t.setTextFormat(Qt.RichText); t.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok); bb.accepted.connect(self.accept); lay.addWidget(bb)


# ---------------------------------------------------------------------- preferenze
class PreferencesDialog(QDialog):
    """Opzioni principali. Le impostazioni sono salvate in QSettings e applicate subito dalla finestra principale."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Preferenze"))
        s = settings()
        self.setMinimumSize(780, 480)
        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        self.nav = QListWidget()                       # elenco laterale delle sezioni (come nelle preferenze di VLC)
        self.nav.setFixedWidth(190); self.nav.setFrameShape(QFrame.StyledPanel)
        self.nav.setStyleSheet("QListWidget::item { padding: 7px 10px; }")
        self.stack = QStackedWidget()
        body.addWidget(self.nav); body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)

        def page(title: str) -> QVBoxLayout:
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(6, 0, 6, 0)
            sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame); sc.setWidget(w)
            self.stack.addWidget(sc); self.nav.addItem(title)
            return v
        pg_gen = page(tr("Generale")); pg_look = page(tr("Aspetto")); pg_bars = page(tr("Barre degli strumenti"))
        pg_view = page(tr("Visualizzazione")); pg_perf = page(tr("Prestazioni")); pg_ocr = page(tr("Scansione e OCR"))
        g = QGroupBox(tr("Barre degli strumenti")); f = QFormLayout(g)
        self.icons = QComboBox(); self.icons.addItems([tr("Piccole (18 px)"), tr("Medie (22 px)"), tr("Grandi (32 px)")])
        self.icons.setCurrentIndex(int(s.value("ui/iconsize", 1)))
        self.icons.setToolTip(tr("Dimensione delle icone nelle barre"))
        self.style = QComboBox(); self.style.addItems([tr("Solo icone"), tr("Icone e testo accanto"), tr("Icone e testo sotto")])
        self.style.setCurrentIndex(int(s.value("ui/btnstyle", 0)))
        self.style.setToolTip(tr("Mostra anche il nome delle funzioni nelle barre"))
        self.rows = QComboBox(); self.rows.addItems([tr("Automatica (una riga se c'è spazio)"), tr("Sempre una riga (le barre eccedenti stanno dietro la freccia »)"), tr("Sempre due righe")])
        self.rows.setCurrentIndex(int(s.value("ui/rows", 0)))
        self.rows.setToolTip(tr("Disposizione predefinita delle barre; si possono comunque trascinare con la maniglia a sinistra"))
        self.locked = QCheckBox(tr("Blocca la posizione delle barre"))
        self.locked.setChecked(str(s.value("ui/locked", "false")).lower() == "true")
        self.locked.setToolTip(tr("Impedisce di spostare le barre per errore"))
        self.theme = QComboBox(); self.theme.addItems([tr("Come il sistema"), tr("Chiaro"), tr("Scuro")])
        self.theme.setCurrentIndex(int(s.value("ui/theme", 0)))
        self.theme.setToolTip(tr("Tema dell'interfaccia: «Come il sistema» segue il tema chiaro/scuro del sistema operativo"))
        self.menus = QComboBox(); self.menus.addItems([tr("Automatico (integrati)"), tr("Integrati nella finestra"), tr("Standard di Qt")])
        self.menus.setCurrentIndex(int(s.value("ui/inmenus", 0)))
        self.menus.setToolTip(tr("Aspetto dei menu a tendina: «integrati» li disegna dentro la finestra, sempre attaccati alla barra dei menu"))
        ga = QGroupBox(tr("Tema e menu")); fa = QFormLayout(ga)
        fa.addRow(tr("Menu a tendina"), self.menus); fa.addRow(tr("Tema"), self.theme)
        f.addRow(tr("Icone"), self.icons); f.addRow(tr("Pulsanti"), self.style); f.addRow(tr("Disposizione"), self.rows)
        f.addRow(self.locked)
        pg_look.addWidget(ga); pg_bars.addWidget(g)
        g2 = QGroupBox(tr("Visualizzazione")); f2 = QFormLayout(g2)
        self.zoom = QComboBox(); self.zoom.addItems([tr("Adatta alla larghezza"), tr("Adatta alla pagina"), tr("Dimensione reale (100%)"), tr("Mantieni lo zoom attuale")])
        self.zoom.setCurrentIndex(int(s.value("view/initzoom", 0)))
        self.zoom.setToolTip(tr("Ingrandimento applicato all'apertura di un documento"))
        self.thumbs = QCheckBox(tr("Mostra il pannello delle miniature all'avvio"))
        self.thumbs.setChecked(str(s.value("view/thumbs", "true")).lower() == "true")
        self.fields = QCheckBox(tr("Evidenzia i campi dei moduli"))
        self.fields.setChecked(str(s.value("view/fields", "true")).lower() == "true")
        f2.addRow(tr("Ingrandimento iniziale"), self.zoom); f2.addRow(self.thumbs); f2.addRow(self.fields)
        pg_view.addWidget(g2)
        g4 = QGroupBox(tr("Griglia")); f4 = QFormLayout(g4)
        self.grid_snap = QCheckBox(tr("Aggancia gli oggetti agli incroci della griglia quando li sposti o ridimensioni"))
        self.grid_snap.setChecked(str(s.value("grid/snap", "false")).lower() == "true")
        self.grid_show = QCheckBox(tr("Mostra la griglia sulle pagine"))
        self.grid_show.setChecked(str(s.value("grid/show", "false")).lower() == "true")
        self.grid_unit = QComboBox()
        for u, t in (("mm", "millimetri"), ("cm", "centimetri"), ("pt", "punti"), ("in", "pollici")):
            self.grid_unit.addItem(t, u)
        self.grid_unit.setCurrentIndex(max(0, self.grid_unit.findData(str(s.value("grid/unit", "mm")))))
        self.grid_x = QDoubleSpinBox(); self.grid_y = QDoubleSpinBox()
        for sp, k in ((self.grid_x, "grid/x"), (self.grid_y, "grid/y")):
            sp.setDecimals(2); sp.setRange(0.1, 500.0); sp.setSingleStep(0.5)
            try:
                sp.setValue(float(s.value(k, 5.0)))
            except (TypeError, ValueError):
                sp.setValue(5.0)
        self.grid_x.setToolTip(tr("Distanza tra le linee verticali")); self.grid_y.setToolTip(tr("Distanza tra le linee orizzontali"))
        row = QHBoxLayout(); row.addWidget(self.grid_x); row.addWidget(QLabel(tr("×"))); row.addWidget(self.grid_y); row.addWidget(self.grid_unit)
        f4.addRow(self.grid_snap); f4.addRow(self.grid_show); f4.addRow(tr("Passo (orizzontale × verticale)"), row)
        pg_view.addWidget(g4)
        g5 = QGroupBox(tr("Selezione del testo")); f5 = QFormLayout(g5)
        self.textsel = QComboBox()
        self.textsel.addItem(tr("A righe (come in un lettore PDF): dal punto iniziale al finale"), "flow")
        self.textsel.addItem(tr("Ad area (rettangolo)"), "area")
        self.textsel.setCurrentIndex(max(0, self.textsel.findData(str(s.value("view/textsel", "flow")))))
        self.textsel.setToolTip(tr("Vale per copia testo, evidenzia, sottolinea e barra. Tenendo premuto Alt durante il trascinamento si usa l'altra modalità."))
        f5.addRow(tr("Modalità"), self.textsel)
        pg_view.addWidget(g5)
        g7 = QGroupBox(tr("Lingua")); f7 = QFormLayout(g7)
        self.lang = QComboBox()
        from .i18n import LANGUAGES, language
        for code, name in LANGUAGES:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(language())))
        self.lang.setToolTip(tr("Lingua dell'interfaccia (si applica al riavvio del programma)"))
        f7.addRow(tr("Lingua dell'interfaccia"), self.lang)
        pg_gen.addWidget(g7)
        g6 = QGroupBox(tr("Dimensioni dell'interfaccia")); f6 = QFormLayout(g6)
        self.fontpct = QSpinBox(); self.fontpct.setRange(70, 200); self.fontpct.setSingleStep(5); self.fontpct.setSuffix(" %")
        self.fontpct.setValue(int(s.value("ui/fontpct", 100)))
        self.fontpct.setToolTip(tr("Ingrandisce o rimpicciolisce il testo di menu, barre, pannelli e finestre (100 % = dimensione di sistema)"))
        f6.addRow(tr("Dimensione"), self.fontpct)
        self.scale = QComboBox()
        self.scale.addItem(tr("Automatica (segue lo schermo)"), 0)
        for pct in (100, 125, 150, 175, 200, 250, 300):
            self.scale.addItem(f"{pct} %", pct)
        cur = int(s.value("ui/scale", 0))
        i = self.scale.findData(cur)
        if i < 0:
            self.scale.addItem(f"{cur} %", cur); i = self.scale.count() - 1
        self.scale.setCurrentIndex(i)
        self.scale.setToolTip(tr("Ingrandisce tutta l'interfaccia (testo, icone, pulsanti) per gli schermi ad alta densità (HiDPI, Retina). "
                                 "«Automatica» usa la scala del sistema operativo. Si applica al riavvio del programma."))
        f6.addRow(tr("Scala dell'interfaccia"), self.scale)
        pg_look.addWidget(g6)
        g6 = QGroupBox(tr("Prestazioni")); f6 = QFormLayout(g6)
        self.gpu = QComboBox()
        self.gpu.addItem(tr("Software (predefinito)"), "software")
        self.gpu.addItem(tr("OpenGL (sperimentale)"), "opengl")
        self.gpu.setCurrentIndex(max(0, self.gpu.findData(str(s.value("ui/gpu", "software")))))
        self.gpu.setToolTip(tr("Come viene disegnata la vista delle pagine. «Software» usa solo la CPU ed è il più compatibile; «OpenGL» usa la scheda grafica "
                               "per scorrimento e zoom. Se OpenGL non è disponibile il programma torna al software. Si applica al riavvio. "
                               "Direct3D e Metal non sono selezionabili: Qt li usa solo nei suoi moduli grafici moderni, non nella vista a widget."))
        f6.addRow(tr("Disegno della vista"), self.gpu)
        from . import parallel
        self.cores = QComboBox()
        n_all = parallel.cpu_total()
        self.cores.addItem(tr("Automatico (tutti meno uno: {})").format(max(1, n_all - 1)), 0)
        for k in range(1, n_all + 1):
            self.cores.addItem(tr("{} processori").format(k) if k > 1 else tr("1 processore (nessun calcolo parallelo)"), k)
        self.cores.setCurrentIndex(max(0, self.cores.findData(int(s.value("perf/cores", 0)))))
        self.cores.setToolTip(tr("Quanti processori usare, al bisogno, per le operazioni lunghe su documenti con molte pagine (esportazione in immagini o testo, ricerca). "
                                 "Con «Automatico» si usano al massimo tutti i processori meno uno, così il computer resta reattivo."))
        f6.addRow(tr("Processori da usare"), self.cores)
        pg_perf.addWidget(g6)
        g6 = QGroupBox(tr("Tesseract (OCR)")); f6 = QFormLayout(g6)
        self.ocr_path = QLineEdit(str(s.value("ocr/path", "")))
        self.ocr_path.setPlaceholderText(tr("Automatico (cerca Tesseract da solo)"))
        self.ocr_path.setToolTip(tr("Percorso di tesseract (file eseguibile o cartella che lo contiene), per l'OCR nelle scansioni. Vuoto = ricerca automatica nel PATH e nelle "
                                    "cartelle usuali (anche C:\\Program Files\\Tesseract-OCR): non serve modificare la variabile PATH."))
        b_browse = QPushButton(tr("Sfoglia…")); b_auto = QPushButton(tr("Cerca"))
        orow = QHBoxLayout(); orow.addWidget(self.ocr_path, 1); orow.addWidget(b_browse); orow.addWidget(b_auto)
        self.ocr_state = QLabel(); self.ocr_state.setWordWrap(True)
        # metodi (non funzioni locali): una funzione che cattura «self» e resta collegata a un segnale tiene vivo il dialogo
        # e ne rende la distruzione, alla chiusura del programma, fuori ordine (crash «malloc(): unaligned tcache chunk»)
        b_browse.clicked.connect(self._ocr_browse); b_auto.clicked.connect(self._ocr_auto); self.ocr_path.editingFinished.connect(self._ocr_refresh)
        self._ocr_refresh()
        f6.addRow(tr("Percorso di Tesseract (OCR)"), orow)
        f6.addRow("", self.ocr_state)
        pg_ocr.addWidget(g6)
        g3 = QGroupBox(tr("File recenti")); f3 = QFormLayout(g3)
        self.recent = QSpinBox(); self.recent.setRange(0, 30); self.recent.setValue(int(s.value("recent_max", 10)))
        self.recent.setToolTip(tr("Quanti file mostrare in File → Apri recenti (0 = nessuno)"))
        f3.addRow(tr("Numero massimo"), self.recent)
        pg_gen.addWidget(g3)
        for v in (pg_gen, pg_look, pg_bars, pg_view, pg_perf, pg_ocr):
            v.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._defaults)
        outer.addWidget(bb)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        try:
            row = int(s.value("ui/prefpage", 0))
        except (TypeError, ValueError):
            row = 0
        self.nav.setCurrentRow(min(max(row, 0), self.nav.count() - 1))      # riapre l'ultima sezione usata

    def _ocr_refresh(self) -> None:
        from . import scan
        scan.set_tesseract_path(self.ocr_path.text())
        p = scan.tesseract_path()
        self.ocr_state.setText(tr("Trovato: {}").format(p) if p else tr("Tesseract non trovato") + " — " + scan.ocr_hint())

    def _ocr_browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, tr("Percorso di Tesseract"), self.ocr_path.text() or os.path.expanduser("~"))
        if f:
            self.ocr_path.setText(f); self._ocr_refresh()

    def _ocr_auto(self) -> None:
        from . import scan
        self.ocr_path.clear(); self._ocr_refresh()
        if not scan.tesseract_path():
            QMessageBox.information(self, tr("OCR"), tr("Tesseract non trovato") + "\n" + scan.ocr_hint())

    def _defaults(self) -> None:
        self.theme.setCurrentIndex(0); self.menus.setCurrentIndex(0); self.icons.setCurrentIndex(1); self.style.setCurrentIndex(0); self.rows.setCurrentIndex(0); self.locked.setChecked(False)
        self.zoom.setCurrentIndex(0); self.thumbs.setChecked(True); self.fields.setChecked(True); self.recent.setValue(10)
        self.grid_snap.setChecked(False); self.grid_show.setChecked(False); self.grid_unit.setCurrentIndex(0); self.grid_x.setValue(5.0); self.grid_y.setValue(5.0); self.textsel.setCurrentIndex(0); self.fontpct.setValue(100); self.lang.setCurrentIndex(0); self.scale.setCurrentIndex(0); self.gpu.setCurrentIndex(0); self.cores.setCurrentIndex(0); self.ocr_path.clear(); self._ocr_refresh()

    def store(self) -> None:
        s = settings()
        s.setValue("ui/prefpage", self.nav.currentRow())
        s.setValue("ui/theme", self.theme.currentIndex()); s.setValue("ui/inmenus", self.menus.currentIndex()); s.setValue("ui/iconsize", self.icons.currentIndex()); s.setValue("ui/btnstyle", self.style.currentIndex())
        s.setValue("ui/rows", self.rows.currentIndex()); s.setValue("ui/locked", self.locked.isChecked())
        s.setValue("view/initzoom", self.zoom.currentIndex()); s.setValue("view/thumbs", self.thumbs.isChecked())
        s.setValue("view/fields", self.fields.isChecked()); s.setValue("recent_max", self.recent.value())
        s.setValue("grid/snap", self.grid_snap.isChecked()); s.setValue("grid/show", self.grid_show.isChecked())
        s.setValue("view/textsel", self.textsel.currentData()); s.setValue("ui/fontpct", self.fontpct.value()); s.setValue("ui/scale", self.scale.currentData()); s.setValue("ui/gpu", self.gpu.currentData()); s.setValue("perf/cores", self.cores.currentData()); s.setValue("ocr/path", self.ocr_path.text().strip()); s.setValue("ui/lang", self.lang.currentData()); s.setValue("grid/unit", self.grid_unit.currentData()); s.setValue("grid/x", self.grid_x.value()); s.setValue("grid/y", self.grid_y.value())



class ExportDialog(QDialog):
    """Opzioni di esportazione: formato, pagine, risoluzione/qualità."""
    def __init__(self, parent, page_count: int, current_page: int, fmt: str = "png") -> None:
        super().__init__(parent)
        from .export import FORMATS
        self.setWindowTitle(tr("Esporta"))
        self.page_count = page_count
        self.current = current_page
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.fmt = QComboBox()
        for k, (label, _) in FORMATS.items():
            self.fmt.addItem(label, k)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(fmt)))
        f.addRow(tr("Formato"), self.fmt)
        self.pages = QComboBox()
        self.pages.addItems([tr("Tutte le pagine"), tr("Pagina corrente"), tr("Intervallo…")])
        self.range = QLineEdit(); self.range.setPlaceholderText(tr("es. 1-3, 5, 8-   (il documento ha {} pagine)").format(page_count))
        f.addRow(tr("Pagine"), self.pages)
        f.addRow(tr("Intervallo"), self.range)
        self.dpi = QSpinBox(); self.dpi.setRange(36, 1200); self.dpi.setValue(150); self.dpi.setSuffix(tr(" dpi"))
        self.dpi.setToolTip(tr("Risoluzione delle immagini"))
        self.quality = QSpinBox(); self.quality.setRange(1, 100); self.quality.setValue(85)
        self.quality.setToolTip(tr("Qualità JPEG (100 = massima)"))
        self.multi = QCheckBox(tr("Un solo file TIFF multipagina")); self.multi.setChecked(True)
        self.comp = QComboBox()
        for label, key in ((tr("LZW (senza perdita)"), "tiff_lzw"), (tr("Nessuna"), "raw"), (tr("Deflate (senza perdita)"), "tiff_adobe_deflate"),
                           ("JPEG", "jpeg")):
            self.comp.addItem(label, key)
        f.addRow(tr("Risoluzione"), self.dpi)
        f.addRow(tr("Qualità JPG"), self.quality)
        f.addRow(tr("Compressione TIFF"), self.comp)
        f.addRow("", self.multi)
        self.keep = QCheckBox(tr("Mantieni l'impaginazione originale")); self.keep.setChecked(True)
        self.keep.setToolTip(tr("Testo, immagini e filetti restano nella stessa posizione del PDF (riquadri di testo). "
                                "Disattivando si ottiene un testo scorrevole, più comodo da riscrivere ma con impaginazione diversa."))
        f.addRow("", self.keep)
        self.note = QLabel(); self.note.setWordWrap(True)
        lay.addLayout(f)
        lay.addWidget(self.note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._rows = {"Risoluzione": (self.dpi,), "Qualità JPG": (self.quality,), "Compressione TIFF": (self.comp,), "": (self.multi,)}
        self._form = f
        self.fmt.currentIndexChanged.connect(self._sync)
        self.pages.currentIndexChanged.connect(self._sync)
        self.keep.toggled.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        k = self.fmt.currentData()
        img = k in ("png", "jpg", "tiff")
        for w, show in ((self.dpi, img), (self.quality, k == "jpg"), (self.comp, k == "tiff"), (self.multi, k == "tiff"), (self.keep, k in ("txt", "docx", "odt"))):
            w.setVisible(show); lab = self._form.labelForField(w)
            if lab:
                lab.setVisible(show)
        self.range.setEnabled(self.pages.currentIndex() == 2)
        self._form.labelForField(self.range).setEnabled(self.range.isEnabled())
        keep = self.keep.isChecked()
        flow = tr("La struttura (titoli, paragrafi, tabelle, immagini, interruzioni di pagina) viene ricostruita dal contenuto del PDF; "
                  "l'impaginazione esatta può differire.")
        fixed = tr("Ogni blocco di testo diventa un riquadro nella stessa posizione e con gli stessi font del PDF; immagini, filetti e "
                   "rettangoli sono riposizionati come nell'originale.")
        self.note.setText({"docx": fixed if keep else flow, "odt": fixed if keep else flow,
                           "txt": tr("Il testo mantiene colonne, rientri e spaziature della pagina. I PDF scansionati senza testo producono un file vuoto.") if keep
                           else tr("Solo il testo, in ordine di lettura. I PDF scansionati senza testo producono un file vuoto.")}.get(k, ""))
        self.adjustSize()

    def _ok(self) -> None:
        try:
            self.page_list()
        except ValueError as e:
            QMessageBox.warning(self, tr("Pagine"), str(e))
            return
        self.accept()

    def page_list(self) -> list[int]:
        from .export import parse_pages
        i = self.pages.currentIndex()
        if i == 0:
            return list(range(self.page_count))
        if i == 1:
            return [self.current]
        return parse_pages(self.range.text() or "1-", self.page_count)

    def options(self) -> dict:
        return {"fmt": self.fmt.currentData(), "pages": self.page_list(), "dpi": self.dpi.value(), "quality": self.quality.value(),
                "tiff_multipage": self.multi.isChecked(), "tiff_compression": self.comp.currentData(), "keep_layout": self.keep.isChecked()}


class MetadataDialog(QDialog):
    """Visualizza, modifica e aggiunge i metadati del documento (Info standard, chiavi personalizzate, XMP)."""
    LABELS = {"title": tr("Titolo"), "author": tr("Autore"), "subject": tr("Oggetto"), "keywords": tr("Parole chiave"), "creator": tr("Applicazione creatrice"),
              "producer": tr("Produttore PDF"), "creationDate": tr("Data di creazione"), "modDate": tr("Data di modifica")}

    def __init__(self, parent, meta: dict, info: list, standard: Optional[str] = None) -> None:
        super().__init__(parent)
        from .core import pdf_date_to_display
        from PySide6.QtWidgets import QTabWidget
        self.setWindowTitle(tr("Metadati del documento"))
        self.resize(640, 520)
        self._meta = meta
        lay = QVBoxLayout(self)
        tabs = QTabWidget(); lay.addWidget(tabs, 1)
        # --- campi standard
        w = QWidget(); f = QFormLayout(w)
        self.fields: dict[str, QLineEdit] = {}
        for k, label in self.LABELS.items():
            e = QLineEdit(pdf_date_to_display(meta["standard"].get(k, "")) if k.endswith("Date") else meta["standard"].get(k, ""))
            if k.endswith("Date"):
                e.setPlaceholderText(tr("AAAA-MM-GG hh:mm:ss +hh:mm  (vuoto = nessuna)"))
                row = QHBoxLayout(); row.addWidget(e, 1)
                b = QPushButton(tr("Adesso")); b.setToolTip(tr("Imposta data e ora attuali"))
                b.clicked.connect(lambda _=False, ed=e: ed.setText(self._now()))
                row.addWidget(b); f.addRow(label, row)
            else:
                f.addRow(label, e)
            e.setToolTip({"title": tr("Titolo mostrato nella barra del visualizzatore"), "keywords": tr("Parole separate da virgole")}.get(k, label))
            self.fields[k] = e
        tabs.addTab(w, tr("Campi standard"))
        # --- personalizzati
        w = QWidget(); v = QVBoxLayout(w)
        v.addWidget(QLabel(tr("Campi aggiuntivi (chiave → valore) memorizzati nel dizionario Info del PDF.")))
        self.table = QTableWidget(0, 2); self.table.setHorizontalHeaderLabels([tr("Chiave"), tr("Valore")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for k, val in meta["custom"].items():
            self._add_row(k, val)
        v.addWidget(self.table, 1)
        row = QHBoxLayout()
        ba = QPushButton(tr("Aggiungi campo")); ba.clicked.connect(lambda: (self._add_row("", ""), self.table.editItem(self.table.item(self.table.rowCount() - 1, 0))))
        br = QPushButton(tr("Rimuovi campo")); br.clicked.connect(self._remove_row)
        row.addWidget(ba); row.addWidget(br); row.addStretch(); v.addLayout(row)
        tabs.addTab(w, tr("Campi personalizzati"))
        # --- XMP
        w = QWidget(); v = QVBoxLayout(w)
        self.xmp = QPlainTextEdit(meta["xmp"] or tr("(nessun blocco XMP)")); self.xmp.setReadOnly(True)
        self.xmp.setLineWrapMode(QPlainTextEdit.NoWrap)
        v.addWidget(self.xmp, 1)
        self.regen = QCheckBox(tr("Rigenera l'XMP dai campi standard (titolo, autore, oggetto, parole chiave, date)"))
        self.rm_xmp = QCheckBox(tr("Rimuovi il blocco XMP"))
        self.rm_xmp.toggled.connect(lambda on: self.regen.setEnabled(not on and not standard))
        v.addWidget(self.regen); v.addWidget(self.rm_xmp)
        if standard:
            self.regen.setEnabled(False)
            v.addWidget(QLabel(tr("Il documento dichiara {}: i suoi metadati XMP sono obbligatori e non vengono rigenerati qui. Modificando i campi standard, XMP e Info possono diventare incoerenti: salvando, PDFDesk propone di ripristinare la conformità.").format(standard)))
            self.rm_xmp.setEnabled(False)
            v.itemAt(v.count() - 1).widget().setWordWrap(True)
        elif not meta["xmp"]:
            self.rm_xmp.setEnabled(False)
        tabs.addTab(w, tr("XMP"))
        # --- informazioni
        t = QTableWidget(len(info), 2); t.setHorizontalHeaderLabels([tr("Proprietà"), tr("Valore")]); t.verticalHeader().hide()
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for i, (a, b) in enumerate(info):
            t.setItem(i, 0, QTableWidgetItem(a)); t.setItem(i, 1, QTableWidgetItem(b))
        tabs.addTab(t, tr("Informazioni"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @staticmethod
    def _now() -> str:
        import datetime
        n = datetime.datetime.now().astimezone()
        off = n.strftime("%z")
        return n.strftime("%Y-%m-%d %H:%M:%S ") + off[:3] + ":" + off[3:]

    def _add_row(self, k: str, v: str) -> None:
        r = self.table.rowCount(); self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(k)); self.table.setItem(r, 1, QTableWidgetItem(v))

    def _remove_row(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def _ok(self) -> None:
        from .core import display_to_pdf_date
        try:
            self.values = self._collect(display_to_pdf_date)
        except ValueError as e:
            QMessageBox.warning(self, tr("Metadati"), str(e))
            return
        self.accept()

    def _collect(self, conv) -> dict:
        std = {}
        for k, e in self.fields.items():
            std[k] = conv(e.text()) if k.endswith("Date") else e.text().strip()
        custom = {}
        reserved = {tr("Title"), tr("Author"), tr("Subject"), tr("Keywords"), tr("Creator"), tr("Producer"), tr("CreationDate"), tr("ModDate"), tr("Trapped")}
        for r in range(self.table.rowCount()):
            k = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip().replace(" ", "_")
            v = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            if not k:
                continue
            if k in reserved:
                raise ValueError(tr("«{}» è un campo standard: modificalo nella prima scheda.").format(k))
            if k in custom:
                raise ValueError(tr("Chiave duplicata: «{}».").format(k))
            custom[k] = v
        return {"standard": std, "custom": custom, "regen_xmp": self.regen.isChecked() and self.regen.isEnabled(),
                "remove_xmp": self.rm_xmp.isChecked()}


class ImageDialog(QDialog):
    """Dimensioni numeriche (varie unità di misura), blocco proporzioni, rotazione, sostituzione ed esportazione di un'immagine."""
    UNITS = [(tr("pt (punti)"), 1.0), ("mm", 72 / 25.4), ("cm", 72 / 2.54), ("pollici", 72.0), (tr("px a 96 dpi"), 0.75)]

    def __init__(self, parent, w_pt: float, h_pt: float, px: tuple, on_export=None, title: str = tr("Proprietà immagine")) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.w_pt, self.h_pt = float(w_pt), float(h_pt)
        self.ratio = self.w_pt / self.h_pt if self.h_pt else 1.0
        self.px = px
        self.replacement: Optional[bytes] = None
        self.on_export = on_export
        self._busy = False
        s = settings()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.unit = QComboBox()
        for t, _f in self.UNITS:
            self.unit.addItem(t)
        self.unit.setCurrentIndex(int(s.value("img/unit", 1)))
        self.wsp, self.hsp = QDoubleSpinBox(), QDoubleSpinBox()
        for sp in (self.wsp, self.hsp):
            sp.setDecimals(3); sp.setRange(0.01, 100000.0); sp.setKeyboardTracking(False)
        self.lock = QCheckBox(tr("Mantieni le proporzioni")); self.lock.setChecked(True)
        self.angle = QDoubleSpinBox(); self.angle.setRange(-360, 360); self.angle.setDecimals(1); self.angle.setSuffix(" °")
        self.angle.setToolTip(tr("Rotazione oraria applicata all'immagine (si ricalcola l'ingombro mantenendo il centro)"))
        rl = QPushButton("↺ 90°"); rr = QPushButton("↻ 90°")
        rl.clicked.connect(lambda: self.angle.setValue(self._wrap(self.angle.value() - 90)))
        rr.clicked.connect(lambda: self.angle.setValue(self._wrap(self.angle.value() + 90)))
        arow = QHBoxLayout(); arow.addWidget(self.angle); arow.addWidget(rl); arow.addWidget(rr)
        form.addRow(tr("Unità di misura"), self.unit)
        form.addRow(tr("Larghezza"), self.wsp); form.addRow(tr("Altezza"), self.hsp)
        form.addRow("", self.lock)
        form.addRow(tr("Ruota di"), arow)
        lay.addLayout(form)
        self.info = QLabel(); self.info.setStyleSheet("color: gray"); lay.addWidget(self.info)
        br = QHBoxLayout()
        self.b_rep = QPushButton(tr("Sostituisci immagine…")); self.b_exp = QPushButton(tr("Esporta immagine…"))
        self.b_rep.clicked.connect(self._replace); self.b_exp.clicked.connect(self._export)
        br.addWidget(self.b_rep); br.addWidget(self.b_exp); lay.addLayout(br)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject); lay.addWidget(bb)
        self.unit.currentIndexChanged.connect(self._unit_changed)
        self.wsp.valueChanged.connect(lambda v: self._edited("w"))
        self.hsp.valueChanged.connect(lambda v: self._edited("h"))
        self._show_values()

    @staticmethod
    def _wrap(a: float) -> float:
        return (a + 180) % 360 - 180 if abs(a) > 180 else a

    def factor(self) -> float:
        return self.UNITS[self.unit.currentIndex()][1]

    def _show_values(self) -> None:
        self._busy = True
        f = self.factor()
        self.wsp.setValue(self.w_pt / f); self.hsp.setValue(self.h_pt / f)
        self._busy = False
        dpi = self.px[0] / (self.w_pt / 72) if self.w_pt else 0
        self.info.setText(tr("Immagine originale: {} × {} px — risoluzione attuale circa {:.0f} dpi").format(self.px[0], self.px[1], dpi))

    def _unit_changed(self) -> None:
        settings().setValue("img/unit", self.unit.currentIndex())
        self._show_values()

    def _edited(self, which: str) -> None:
        if self._busy:
            return
        f = self.factor()
        self._busy = True
        if which == "w":
            self.w_pt = self.wsp.value() * f
            if self.lock.isChecked():
                self.h_pt = self.w_pt / self.ratio; self.hsp.setValue(self.h_pt / f)
        else:
            self.h_pt = self.hsp.value() * f
            if self.lock.isChecked():
                self.w_pt = self.h_pt * self.ratio; self.wsp.setValue(self.w_pt / f)
        self._busy = False
        if not self.lock.isChecked() and self.h_pt:
            self.ratio = self.w_pt / self.h_pt          # proporzioni sbloccate: sono quelle impostate a mano

    def _replace(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Scegli l'immagine sostitutiva"), str(settings().value("lastimgdir", "")),
                                              tr("Immagini (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)"))
        if not path:
            return
        try:
            from . import imgutil
            data = imgutil.to_png_bytes(path)
            img = QImage.fromData(data)
        except Exception as e:
            QMessageBox.warning(self, tr("Immagine"), tr("Impossibile leggere l'immagine:\n{}").format(e))
            return
        settings().setValue("lastimgdir", os.path.dirname(path))
        self.replacement = data
        self.px = (img.width(), img.height())
        if self.lock.isChecked() and img.height():                     # le proporzioni seguono la nuova immagine
            self.ratio = img.width() / img.height()
            self.h_pt = self.w_pt / self.ratio
        self._show_values()
        self.b_rep.setText(tr("Sostituisci immagine… (scelta: ") + os.path.basename(path) + ")")

    def _export(self) -> None:
        if self.on_export:
            self.on_export()

    def values(self) -> tuple:
        """(larghezza pt, altezza pt, angolo, immagine sostitutiva o None)"""
        return self.w_pt, self.h_pt, self.angle.value(), self.replacement


class ImageOutDialog(QDialog):
    """Formato (PNG/JPG/TIFF), risoluzione e qualità per salvare un'immagine o un'area della pagina."""
    def __init__(self, parent, title: str, with_dpi: bool = True, with_annots: bool = False, copy_button: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        s = settings()
        f = QFormLayout()
        self.fmt = QComboBox()
        for k, (label, _) in (("png", (tr("PNG (senza perdita, trasparenza)"), "")), ("jpg", (tr("JPG (compatto, con perdita)"), "")),
                              ("tiff", (tr("TIFF (senza perdita, stampa/archivio)"), ""))):
            self.fmt.addItem(label, k)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(str(s.value("extract/fmt", "png")))))
        f.addRow(tr("Formato"), self.fmt)
        self.dpi = QSpinBox(); self.dpi.setRange(36, 1200); self.dpi.setSuffix(tr(" dpi")); self.dpi.setValue(int(s.value("extract/dpi", 200)))
        self.dpi.setToolTip(tr("Risoluzione con cui l'area viene resa"))
        if with_dpi:
            f.addRow(tr("Risoluzione"), self.dpi)
        self.quality = QSpinBox(); self.quality.setRange(1, 100); self.quality.setValue(int(s.value("extract/quality", 90)))
        f.addRow(tr("Qualità JPG"), self.quality)
        self.annots = QCheckBox(tr("Includi annotazioni e campi")); self.annots.setChecked(True)
        if with_annots:
            f.addRow("", self.annots)
        lay = QVBoxLayout(self); lay.addLayout(f)
        self.copy_requested = False
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Salva con nome…"))
        bb.accepted.connect(self._ok); bb.rejected.connect(self.reject)
        if copy_button:
            b = bb.addButton(tr("Copia negli appunti"), QDialogButtonBox.ActionRole)
            b.clicked.connect(lambda: (setattr(self, "copy_requested", True), self._ok()))
        lay.addWidget(bb)
        self.fmt.currentIndexChanged.connect(self._sync); self._sync()

    def _sync(self) -> None:
        j = self.fmt.currentData() == "jpg"
        self.quality.setEnabled(j)

    def _ok(self) -> None:
        s = settings()
        s.setValue("extract/fmt", self.fmt.currentData()); s.setValue("extract/dpi", self.dpi.value()); s.setValue("extract/quality", self.quality.value())
        self.accept()


class ExtractImagesDialog(QDialog):
    """Elenco delle immagini incorporate nel PDF: si scelgono quelle da salvare (JPG, TIFF o PNG)."""
    def __init__(self, parent, doc, items: list, current_page: int = 0) -> None:
        super().__init__(parent)
        from . import extract
        self.setWindowTitle(tr("Estrai immagini"))
        self.resize(640, 520)
        self.items = items
        self._doc = doc
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.scope = QComboBox(); self.scope.addItems([tr("Tutte le pagine"), tr("Solo la pagina {}").format(current_page + 1)])
        self.scope.currentIndexChanged.connect(self._fill)
        top.addWidget(QLabel(tr("Mostra"))); top.addWidget(self.scope)
        ba = QPushButton(tr("Seleziona tutte")); ba.clicked.connect(lambda: self._all(True))
        bn = QPushButton(tr("Nessuna")); bn.clicked.connect(lambda: self._all(False))
        top.addStretch(); top.addWidget(ba); top.addWidget(bn)
        lay.addLayout(top)
        self.list = QListWidget(); self.list.setIconSize(QSize(64, 64)); lay.addWidget(self.list, 1)
        self.current = current_page
        f = QFormLayout()
        self.fmt = QComboBox()
        for k, label in (("png", tr("PNG (senza perdita, trasparenza)")), ("jpg", tr("JPG (compatto, con perdita)")), ("tiff", tr("TIFF (senza perdita)"))):
            self.fmt.addItem(label, k)
        s = settings()
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(str(s.value("extract/fmt", "png")))))
        self.quality = QSpinBox(); self.quality.setRange(1, 100); self.quality.setValue(int(s.value("extract/quality", 90)))
        f.addRow(tr("Formato"), self.fmt); f.addRow(tr("Qualità JPG"), self.quality)
        lay.addLayout(f)
        self.count = QLabel(); lay.addWidget(self.count)
        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText(tr("Estrai in una cartella…"))
        self.bb.accepted.connect(self._ok); self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)
        self.list.itemChanged.connect(self._count)
        self.fmt.currentIndexChanged.connect(lambda: self.quality.setEnabled(self.fmt.currentData() == "jpg"))
        self.quality.setEnabled(self.fmt.currentData() == "jpg")
        self._fill()

    def _fill(self) -> None:
        from . import extract
        self.list.blockSignals(True); self.list.clear()
        only = self.scope.currentIndex() == 1
        for it in self.items:
            if only and it["page"] != self.current:
                continue
            txt = f"Pagina {it['page'] + 1} — {it['w']}×{it['h']} px"
            if it["dpi"]:
                txt += f", ~{it['dpi']} dpi"
            txt += f"\n{compress.human_size(it['bytes'])} nel file" + (tr(" · con trasparenza") if it["mask"] else "")
            li = QListWidgetItem(txt)
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable); li.setCheckState(Qt.Checked); li.setData(Qt.UserRole, it)
            try:
                pix = extract.image_pixmap(self._doc, it["xref"])
                k = max(pix.width, pix.height) / 64.0
                if k > 1:
                    pix = fitz_shrink(pix, k)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888 if pix.alpha else
                             (QImage.Format_RGB888 if pix.n == 3 else QImage.Format_Grayscale8)).copy()
                li.setIcon(QPixmap.fromImage(img))
            except Exception:
                pass
            self.list.addItem(li)
        self.list.blockSignals(False)
        self._count()

    def _all(self, on: bool) -> None:
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Checked if on else Qt.Unchecked)
        self.list.blockSignals(False); self._count()

    def selected(self) -> list:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.Checked]

    def _count(self) -> None:
        n = len(self.selected())
        self.count.setText(tr("{} immagini selezionate su {}").format(n, self.list.count()) if self.list.count() else tr("Nessuna immagine incorporata."))
        self.bb.button(QDialogButtonBox.Ok).setEnabled(n > 0)

    def _ok(self) -> None:
        s = settings(); s.setValue("extract/fmt", self.fmt.currentData()); s.setValue("extract/quality", self.quality.value())
        self.accept()


def fitz_shrink(pix, k: float):
    """Riduce l'anteprima di una potenza di 2 vicina a k (Pixmap.shrink lavora per potenze di 2)."""
    import math
    n = int(math.log2(k)) if k >= 2 else 0
    if n >= 1:
        pix.shrink(n)
    return pix


# ---------------------------------------------------------------------- unione di più PDF
class MergeDialog(QDialog):
    """Elenco ordinabile (trascinamento o pulsanti) dei PDF/immagini da unire in un unico PDF."""

    def __init__(self, parent=None, files: Optional[list] = None, default_out: str = "") -> None:
        super().__init__(parent)
        from . import merge as mg
        self._mg = mg
        self.setWindowTitle(tr("Unisci PDF"))
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Aggiungi i file e disponili nell'ordine voluto (trascinali o usa Su/Giù). "
                             "Puoi anche limitare le pagine di ciascun file.")))
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setAlternatingRowColors(True)
        self.list.itemDoubleClicked.connect(lambda _i: self.set_pages())
        row.addWidget(self.list, 1)
        col = QVBoxLayout()
        for text, fn in ((tr("Aggiungi…"), self.add_dialog), (tr("Rimuovi"), self.remove_selected), ("Su", lambda: self.move(-1)),
                         ("Giù", lambda: self.move(1)), (tr("Ordina per nome"), self.sort_by_name),
                         (tr("Pagine…"), self.set_pages), (tr("Inverti ordine"), self.reverse)):
            b = QPushButton(text); b.clicked.connect(fn); col.addWidget(b)
        col.addStretch(1)
        row.addLayout(col)
        lay.addLayout(row, 1)
        self.summary = QLabel(); lay.addWidget(self.summary)
        f = QFormLayout()
        orow = QHBoxLayout()
        self.out = QLineEdit(default_out)
        bb0 = QPushButton(tr("Sfoglia…")); bb0.clicked.connect(self._browse)
        orow.addWidget(self.out, 1); orow.addWidget(bb0)
        f.addRow(tr("PDF finale"), orow)
        self.bookmarks = QCheckBox(tr("Aggiungi un segnalibro per ogni file sorgente")); self.bookmarks.setChecked(True)
        self.open_after = QCheckBox(tr("Apri il risultato dopo l'unione")); self.open_after.setChecked(True)
        f.addRow(self.bookmarks); f.addRow(self.open_after)
        lay.addLayout(f)
        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText(tr("Unisci"))
        self.bb.accepted.connect(self._ok); self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)
        self.list.model().rowsMoved.connect(self._refresh)
        for p in files or []:
            self.add_file(p)
        self._refresh()

    # --- gestione elenco
    def add_file(self, path: str) -> bool:
        pw = ""
        try:
            info = self._mg.probe(path)
            while info["locked"]:
                pw, ok = QInputDialog.getText(self, tr("PDF protetto"), tr("Password di {}:").format(os.path.basename(path)), QLineEdit.Password)
                if not ok:
                    return False
                info = self._mg.probe(path, pw)
                if info["locked"]:
                    QMessageBox.warning(self, tr("Password"), tr("Password errata."))
        except self._mg.MergeError as e:
            QMessageBox.warning(self, tr("Unisci PDF"), str(e))
            return False
        it = QListWidgetItem()
        it.setData(Qt.UserRole, {"path": path, "pages": "", "password": pw, "count": info["pages"]})
        self.list.addItem(it)
        self._label(it)
        self._refresh()
        return True

    def _label(self, it: QListWidgetItem) -> None:
        d = it.data(Qt.UserRole)
        sel = f"  — pagine {d['pages']}" if d["pages"] else ""
        it.setText(tr("{}   ({} pag.){}").format(os.path.basename(d['path']), d['count'], sel))
        it.setToolTip(d["path"])

    def add_dialog(self) -> None:
        s = settings()
        ps, _ = QFileDialog.getOpenFileNames(self, tr("Aggiungi file"), s.value("lastdir", ""),
                                             tr("PDF e immagini (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp);;PDF (*.pdf);;Tutti i file (*)"))
        for p in ps:
            self.add_file(p)
        if ps:
            s.setValue("lastdir", os.path.dirname(ps[0]))
            if not self.out.text():
                self.out.setText(os.path.join(os.path.dirname(ps[0]), "unito.pdf"))

    def remove_selected(self) -> None:
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))
        self._refresh()

    def move(self, d: int) -> None:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        if not rows:
            return
        if d > 0:
            rows.reverse()
        for r in rows:
            n = r + d
            if 0 <= n < self.list.count():
                self.list.insertItem(n, self.list.takeItem(r))
                self.list.item(n).setSelected(True)
        self._refresh()

    def sort_by_name(self) -> None:
        its = [self.list.takeItem(0) for _ in range(self.list.count())]
        its.sort(key=lambda i: os.path.basename(i.data(Qt.UserRole)["path"]).lower())
        for i in its:
            self.list.addItem(i)
        self._refresh()

    def reverse(self) -> None:
        its = [self.list.takeItem(0) for _ in range(self.list.count())]
        for i in reversed(its):
            self.list.addItem(i)
        self._refresh()

    def set_pages(self, text: Optional[str] = None) -> None:
        it = self.list.currentItem()
        if it is None:
            return
        d = it.data(Qt.UserRole)
        if text is None:
            text, ok = QInputDialog.getText(self, tr("Pagine da includere"), tr("{} ha {} pagine.\nIntervalli (es. 1-3,5,8-); vuoto = tutte:").format(os.path.basename(d['path']), d['count']), QLineEdit.Normal, d["pages"])
            if not ok:
                return
        from .export import parse_pages
        try:
            parse_pages(text or "", d["count"])
        except ValueError as e:
            QMessageBox.warning(self, tr("Pagine"), str(e))
            return
        d["pages"] = (text or "").strip()
        it.setData(Qt.UserRole, d)
        self._label(it)
        self._refresh()

    def items(self) -> list:
        return [{k: v for k, v in self.list.item(i).data(Qt.UserRole).items() if k != "count"} for i in range(self.list.count())]

    def total_pages(self) -> int:
        from .export import parse_pages
        n = 0
        for i in range(self.list.count()):
            d = self.list.item(i).data(Qt.UserRole)
            try:
                n += len(parse_pages(d["pages"], d["count"]))
            except ValueError:
                pass
        return n

    def _refresh(self, *_a) -> None:
        self.summary.setText(tr("{} file, {} pagine nel PDF finale").format(self.list.count(), self.total_pages()))
        self.bb.button(QDialogButtonBox.Ok).setEnabled(self.list.count() > 0)

    def _browse(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, tr("Salva PDF unito"), self.out.text(), tr("PDF (*.pdf)"))
        if p:
            self.out.setText(p if p.lower().endswith(".pdf") else p + ".pdf")

    def _ok(self) -> None:
        if not self.out.text().strip():
            self._browse()
            if not self.out.text().strip():
                return
        out = os.path.abspath(self.out.text().strip())
        srcs = {os.path.abspath(d["path"]) for d in self.items()}
        if out in srcs:
            QMessageBox.warning(self, tr("Unisci PDF"), tr("Il PDF finale non può coincidere con uno dei file sorgente."))
            return
        if os.path.exists(out) and QMessageBox.question(self, tr("Sovrascrivere?"), tr("{}\nesiste già. Sovrascriverlo?").format(out)) != QMessageBox.Yes:
            return
        self.out_path = out
        self.accept()


# ---------------------------------------------------------------------- scansione
class _ScanThread(QThread):
    done = Signal(list, str)

    def __init__(self, scanner, params, folder) -> None:
        super().__init__()
        self.scanner, self.params, self.folder = scanner, params, folder

    def run(self) -> None:
        from . import scan
        try:
            self.done.emit(scan.scan_pages(self.scanner, self.params, self.folder), "")
        except Exception as e:
            self.done.emit([], str(e) or e.__class__.__name__)


class ScanDialog(QDialog):
    """Acquisizione da scanner (WIA / SANE) o da file immagine e creazione di un PDF."""

    def __init__(self, parent=None, default_out: str = "") -> None:
        super().__init__(parent)
        import tempfile
        from . import scan
        self._sc = scan
        self.setWindowTitle(tr("Crea PDF da scansione"))
        self.resize(860, 640)
        self.folder = tempfile.mkdtemp(prefix="pdfdesk-scan-")
        self._thread = None
        self.out_path = ""
        lay = QVBoxLayout(self)
        # --- scanner e parametri
        g = QFormLayout()
        srow = QHBoxLayout()
        self.dev = QComboBox(); self.dev.setMinimumWidth(320)
        rb = QPushButton(tr("Cerca scanner")); rb.clicked.connect(self.refresh)
        srow.addWidget(self.dev, 1); srow.addWidget(rb)
        g.addRow(tr("Scanner"), srow)
        self.hint = QLabel(); self.hint.setWordWrap(True); self.hint.setStyleSheet("color: gray")
        g.addRow(self.hint)
        prow = QHBoxLayout()
        self.source = QComboBox(); [self.source.addItem(v, k) for k, v in scan.SOURCES.items()]
        self.mode = QComboBox(); [self.mode.addItem(v, k) for k, v in scan.MODES.items()]
        self.dpi = QComboBox(); [self.dpi.addItem(tr("{} dpi").format(d), d) for d in (75, 100, 150, 200, 300, 400, 600, 1200)]
        self.dpi.setCurrentIndex(self.dpi.findData(300))
        self.paper = QComboBox(); [self.paper.addItem(v[0], k) for k, v in scan.PAPER.items()]
        self.paper.setCurrentIndex(self.paper.findData("a4"))
        for w in (self.source, self.mode, self.dpi, self.paper):
            prow.addWidget(w)
        g.addRow(tr("Origine / modo / risoluzione / formato"), prow)
        lay.addLayout(g)
        brow = QHBoxLayout()
        self.b_scan = QPushButton(tr("Scansiona")); self.b_scan.clicked.connect(self.start_scan)
        b_imp = QPushButton(tr("Importa immagini…")); b_imp.clicked.connect(self.import_dialog)
        b_del = QPushButton(tr("Elimina")); b_del.clicked.connect(self.remove_selected)
        b_rl = QPushButton(tr("⟲ Ruota")); b_rl.clicked.connect(lambda: self.rotate(-90))
        b_rr = QPushButton(tr("Ruota ⟳")); b_rr.clicked.connect(lambda: self.rotate(90))
        for b in (self.b_scan, b_imp, b_del, b_rl, b_rr):
            brow.addWidget(b)
        brow.addStretch(1)
        lay.addLayout(brow)
        self.pages = QListWidget()
        self.pages.setViewMode(QListWidget.IconMode); self.pages.setIconSize(QSize(120, 160))
        self.pages.setResizeMode(QListWidget.Adjust); self.pages.setMovement(QListWidget.Snap)
        self.pages.setDragDropMode(QAbstractItemView.InternalMove)
        self.pages.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.pages.setSpacing(8)
        lay.addWidget(self.pages, 1)
        self.status = QLabel(tr("Nessuna pagina. Scansiona o importa delle immagini.")); lay.addWidget(self.status)
        # --- uscita
        f = QFormLayout()
        orow = QHBoxLayout()
        self.out = QLineEdit(default_out)
        bo = QPushButton(tr("Sfoglia…")); bo.clicked.connect(self._browse)
        orow.addWidget(self.out, 1); orow.addWidget(bo)
        f.addRow(tr("PDF da creare"), orow)
        self.comp = QComboBox()
        for t, q in ((tr("Senza perdita (PNG, file più grande)"), 0), (tr("JPEG alta qualità (85)"), 85), (tr("JPEG media (70) — file piccolo"), 70),
                     (tr("JPEG bassa (50) — molto piccolo"), 50)):
            self.comp.addItem(t, q)
        self.comp.setCurrentIndex(1)
        f.addRow(tr("Compressione delle pagine"), self.comp)
        orow2 = QHBoxLayout()
        self.ocr = QCheckBox(tr("Rendi il testo ricercabile (OCR)"))
        self.lang = QComboBox()
        langs = scan.ocr_languages()
        for l in langs:
            self.lang.addItem(l, l)
        if "ita" in langs:
            self.lang.setCurrentIndex(self.lang.findData("ita"))
        self.ocr.setEnabled(bool(langs)); self.lang.setEnabled(bool(langs))
        self.ocr_dl = QPushButton(tr("Scarica OCR…"))
        self.ocr_dl.setVisible(False)
        self.ocr_dl.clicked.connect(self._download_ocr)
        if not langs:
            self.ocr.setToolTip(tr("Tesseract non trovato: installalo per attivare l'OCR") + "\n" + self._sc.ocr_hint())
            self.ocr.setText(tr("Rendi il testo ricercabile (OCR) — richiede Tesseract, non trovato"))
            self.ocr_dl.setVisible(sys.platform == "win32")
        orow2.addWidget(self.ocr); orow2.addWidget(self.lang); orow2.addWidget(self.ocr_dl); orow2.addStretch(1)
        f.addRow(orow2)
        self.open_after = QCheckBox(tr("Apri il PDF dopo averlo creato")); self.open_after.setChecked(True)
        f.addRow(self.open_after)
        lay.addLayout(f)
        self.bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.bb.button(QDialogButtonBox.Ok).setText(tr("Crea PDF"))
        self.bb.accepted.connect(self._create); self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)
        self.scanners = []
        self._update_enabled()

    # --- scanner
    def refresh(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.scanners = self._sc.list_scanners()
        finally:
            QApplication.restoreOverrideCursor()
        self.dev.clear()
        for s in self.scanners:
            self.dev.addItem(s.label, s)
        be = self._sc.available_backends()
        if self.scanners:
            self.hint.setText(tr("{} scanner trovati.").format(len(self.scanners)))
        elif not be:
            self.hint.setText(tr("Nessun driver di scansione disponibile. Su Windows serve WIA (incluso in Windows); su Linux e macOS installa "
                              "SANE (pacchetto «sane-utils» / «sane-backends», comando scanimage). Puoi comunque importare immagini già acquisite."))
        else:
            self.hint.setText(tr("Nessuno scanner trovato: controlla collegamento e accensione, poi premi «Cerca scanner»."))
        self._update_enabled()

    def _update_enabled(self) -> None:
        busy = self._thread is not None and self._thread.isRunning()
        self.b_scan.setEnabled(bool(self.dev.count()) and not busy)
        self.bb.button(QDialogButtonBox.Ok).setEnabled(self.pages.count() > 0 and not busy)

    def params(self):
        return self._sc.ScanParams(self.mode.currentData(), self.dpi.currentData(), self.source.currentData(), self.paper.currentData())

    def start_scan(self) -> None:
        sc = self.dev.currentData()
        if sc is None:
            return
        self.status.setText(tr("Scansione in corso…"))
        QApplication.setOverrideCursor(Qt.BusyCursor)
        self._thread = _ScanThread(sc, self.params(), self.folder)
        self._thread.done.connect(self._scanned)
        self._thread.start()
        self._update_enabled()

    def _scanned(self, files: list, err: str) -> None:
        QApplication.restoreOverrideCursor()
        self._thread = None
        have = {self.pages.item(i).data(Qt.UserRole) for i in range(self.pages.count())}
        new = [f for f in files if f not in have]
        for f in new:
            self._add_page(f, self.dpi.currentData())
        if err:
            QMessageBox.warning(self, tr("Scansione"), err)
        self.status.setText(tr("{} pagine acquisite.").format(len(new)) if new else tr("Nessuna pagina acquisita."))
        self._update_enabled()

    # --- pagine
    def _add_page(self, path: str, dpi: int) -> None:
        pm = QPixmap(path)
        it = QListWidgetItem(QIcon(pm.scaled(240, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)) if not pm.isNull() else QIcon(), "")
        it.setData(Qt.UserRole, path)
        it.setData(Qt.UserRole + 1, dpi)
        it.setToolTip(os.path.basename(path))
        self.pages.addItem(it)
        self._renumber()

    def _renumber(self) -> None:
        for i in range(self.pages.count()):
            self.pages.item(i).setText(tr("Pagina {}").format(i + 1))
        self.status.setText(tr("{} pagine").format(self.pages.count()) if self.pages.count() else tr("Nessuna pagina."))
        self._update_enabled()

    def import_dialog(self) -> None:
        import shutil
        s = settings()
        ps, _ = QFileDialog.getOpenFileNames(self, tr("Importa immagini"), s.value("lastdir", ""),
                                             tr("Immagini (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.gif *.webp)"))
        self.import_files(ps)
        if ps:
            s.setValue("lastdir", os.path.dirname(ps[0]))

    def import_files(self, ps: list) -> int:
        import shutil
        n = 0
        for p in ps:
            dst = os.path.join(self.folder, f"imp{self.pages.count() + n + 1:04d}{os.path.splitext(p)[1].lower()}")
            try:
                shutil.copy(p, dst)
            except OSError as e:
                QMessageBox.warning(self, tr("Importa"), f"{p}: {e}")
                continue
            self._add_page(dst, self.dpi.currentData()); n += 1
        return n

    def remove_selected(self) -> None:
        for it in self.pages.selectedItems():
            self.pages.takeItem(self.pages.row(it))
        self._renumber()

    def rotate(self, deg: int, items: Optional[list] = None) -> None:
        from PIL import Image
        for it in (items or self.pages.selectedItems()):
            path = it.data(Qt.UserRole)
            try:
                im = Image.open(path); dpi = im.info.get("dpi")
                r = im.rotate(-deg, expand=True)
                im.close()
                r.save(path, **({"dpi": dpi} if dpi else {}))
            except Exception as e:
                QMessageBox.warning(self, tr("Ruota"), str(e)); continue
            pm = QPixmap(path)
            it.setIcon(QIcon(pm.scaled(240, 320, Qt.KeepAspectRatio, Qt.SmoothTransformation)))

    def files(self) -> list:
        return [self.pages.item(i).data(Qt.UserRole) for i in range(self.pages.count())]

    def _browse(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, tr("Salva PDF"), self.out.text(), tr("PDF (*.pdf)"))
        if p:
            self.out.setText(p if p.lower().endswith(".pdf") else p + ".pdf")

    def _download_ocr(self) -> None:
        """Windows: scarica e installa Tesseract (e la lingua italiana) da internet, poi attiva l'OCR."""
        if QMessageBox.question(self, tr("Scarica OCR"), tr("Verrà scaricato Tesseract {v} da internet (circa 50 MB) e installato per PDFDesk. Continuare?")
                                .format(v=self._sc.TESSERACT_VERSION)) != QMessageBox.Yes:
            return
        prog = QProgressDialog(tr("Scaricamento dell'OCR…"), tr("Annulla"), 0, 100, self)
        prog.setWindowModality(Qt.WindowModal); prog.setMinimumDuration(0)

        def cb(what, got, total):
            prog.setLabelText(tr("Scaricamento: {w}").format(w=what)); prog.setValue(int(100 * got / total) if total else 0)
            QApplication.processEvents()
            return not prog.wasCanceled()
        try:
            self._sc.install_tesseract(progress=cb)
        except Exception as e:
            prog.close()
            QMessageBox.critical(self, tr("Scarica OCR"), tr("Installazione dell'OCR non riuscita:\n{}").format(e))
            return
        prog.close()
        langs = self._sc.ocr_languages()
        self.lang.clear()
        for l in langs:
            self.lang.addItem(l, l)
        if "ita" in langs:
            self.lang.setCurrentIndex(self.lang.findData("ita"))
        self.ocr.setEnabled(bool(langs)); self.lang.setEnabled(bool(langs)); self.ocr.setChecked(bool(langs))
        self.ocr.setText(tr("Rendi il testo ricercabile (OCR)")); self.ocr.setToolTip("")
        self.ocr_dl.setVisible(not langs)

    def _create(self) -> None:
        if not self.out.text().strip():
            self._browse()
            if not self.out.text().strip():
                return
        out = os.path.abspath(self.out.text().strip())
        if os.path.exists(out) and QMessageBox.question(self, tr("Sovrascrivere?"), tr("{}\nesiste già. Sovrascriverlo?").format(out)) != QMessageBox.Yes:
            return
        prog = QProgressDialog(tr("Creazione del PDF…"), tr("Annulla"), 0, self.pages.count(), self)
        prog.setWindowModality(Qt.WindowModal); prog.setMinimumDuration(300)

        def cb(i, n):
            prog.setMaximum(max(1, n)); prog.setValue(i); QApplication.processEvents()
            return not prog.wasCanceled()
        try:
            self._sc.images_to_pdf(self.files(), out, self.dpi.currentData(), self.comp.currentData(),
                                   self.lang.currentData() if self.ocr.isChecked() else "", cb)
        except Exception as e:
            prog.close()
            QMessageBox.critical(self, tr("Crea PDF"), tr("Creazione non riuscita:\n{}").format(e))
            return
        prog.close()
        self.out_path = out
        self.accept()

    def done(self, r: int) -> None:
        import shutil
        if self._thread is not None and self._thread.isRunning():
            self._thread.wait(2000)
        shutil.rmtree(self.folder, ignore_errors=True)
        super().done(r)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if not self.scanners and not self.dev.count():
            QTimer.singleShot(50, self.refresh)
