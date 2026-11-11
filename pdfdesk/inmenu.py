# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# inmenu.py: menu a tendina disegnati DENTRO la finestra. Sotto Wayland i menu «popup» di Qt sono finestre separate
# che il compositor può collocare in modo errato (staccati dalla barra dei menu): qui le tendine sono widget figli
# della finestra, posizionati con precisione sotto la voce cliccata, identici su ogni sistema.
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QPainter, QPalette, QPolygon
from PySide6.QtWidgets import QApplication, QFrame, QMenu, QMenuBar, QVBoxLayout, QWidget


def wayland_session() -> bool:
    return sys.platform.startswith("linux") and (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
                                                 or bool(os.environ.get("WAYLAND_DISPLAY")))


class _Row(QWidget):
    def __init__(self, panel: "MenuPanel", act) -> None:
        super().__init__(panel)
        self.panel, self.act = panel, act
        self.hover = False
        self.setMouseTracking(True)
        fm = self.fontMetrics()
        self.sc = "" if act.menu() else act.shortcut().toString(QKeySequence.NativeText)
        self.label = act.text().replace("&&", "\0").replace("&", "").replace("\0", "&").split("\t")[0]
        self.wanted = 32 + fm.horizontalAdvance(self.label) + (34 + fm.horizontalAdvance(self.sc) if self.sc else 0) + 24
        self.setFixedHeight(max(24, fm.height() + 8))
        # niente tooltip: sotto Wayland è una finestra a parte che può «mangiare» il clic; il suggerimento va nella barra di stato
        self.tip = act.toolTip() if act.toolTip() and act.toolTip() != self.label else ""

    def sizeHint(self) -> QSize:
        return QSize(self.wanted, self.height())

    def enterEvent(self, e) -> None:
        self.panel.row_hover(self)
        try:
            sb = self.panel.mgr.window.statusBar()
            sb.showMessage(self.tip.split("\n")[0] if self.tip else "", 4000)
        except Exception:
            pass

    def leaveEvent(self, e) -> None:
        if not self.act.menu():
            self.hover = False
            self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()                                    # senza questo il clic risale alla finestra e chiuderebbe la tendina
        self.panel.row_hover(self)                    # il clic vale anche se l'entrata del mouse non è stata recapitata
        if e.button() == Qt.LeftButton:               # la voce scatta alla PRESSIONE: non dipende dal rilascio (clic veloce)
            self.panel.row_clicked(self)

    def mouseReleaseEvent(self, e) -> None:
        e.accept()

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        pal = self.palette()
        on = self.act.isEnabled()
        if self.hover and on:
            p.fillRect(self.rect(), pal.color(QPalette.Highlight))
            fg = pal.color(QPalette.HighlightedText)
        else:
            fg = pal.color(QPalette.Normal if on else QPalette.Disabled, QPalette.WindowText)
        h = self.height()
        icon_r = QRect(7, (h - 16) // 2, 16, 16)
        ic = self.act.icon()
        if self.act.isCheckable() and self.act.isChecked():
            p.setPen(fg)
            if ic.isNull():
                p.drawText(icon_r, Qt.AlignCenter, "✓")
            else:
                p.fillRect(icon_r.adjusted(-3, -3, 3, 3), pal.color(QPalette.Mid))
        if not ic.isNull():
            ic.paint(p, icon_r, Qt.AlignCenter, QIcon_mode(on))
        p.setPen(fg)
        p.drawText(QRect(32, 0, self.width() - 40, h), Qt.AlignVCenter | Qt.AlignLeft, self.label)
        if self.act.menu():
            x, y = self.width() - 12, h // 2
            p.setBrush(fg)
            p.drawPolygon(QPolygon([QPoint(x, y - 4), QPoint(x + 5, y), QPoint(x, y + 4)]))
        elif self.sc:
            p.drawText(QRect(32, 0, self.width() - 44, h), Qt.AlignVCenter | Qt.AlignRight, self.sc)


def QIcon_mode(enabled: bool):
    from PySide6.QtGui import QIcon
    return QIcon.Normal if enabled else QIcon.Disabled


class MenuPanel(QFrame):
    def __init__(self, mgr: "MenuManager", menu: QMenu, level: int) -> None:
        super().__init__(mgr.window)
        self.mgr, self.menu, self.level = mgr, menu, level
        self.setObjectName("inMenuPanel")
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 3, 2, 3)
        lay.setSpacing(0)
        menu.aboutToShow.emit()
        self.rows: list[_Row] = []
        wmax = 0
        for a in menu.actions():
            if not a.isVisible():
                continue
            if a.isSeparator():
                f = QFrame()
                f.setFrameShape(QFrame.HLine)
                f.setFrameShadow(QFrame.Sunken)
                lay.addWidget(f)
                continue
            r = _Row(self, a)
            self.rows.append(r)
            lay.addWidget(r)
            wmax = max(wmax, r.wanted)
        self.setMinimumWidth(wmax + 6)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._open_pending)
        self._pending: _Row | None = None
        self.child_row: _Row | None = None
        self.adjustSize()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def row_hover(self, row: _Row) -> None:
        for r in self.rows:
            r.hover = r is row
            r.update()
        if row is not self.child_row:
            self.mgr.close_deeper(self.level)
            self.child_row = None
        if row.act.menu() and row.act.isEnabled() and row is not self.child_row:
            self._pending = row
            self._timer.start()

    def _open_pending(self) -> None:
        if self._pending is not None:
            self.mgr.open_child(self, self._pending)

    def row_clicked(self, row: _Row) -> None:
        if row.act.menu():
            if row.act.isEnabled():
                self.mgr.open_child(self, row)
            return
        if not row.act.isEnabled():
            return
        self.mgr.close_all()
        QTimer.singleShot(0, row.act.trigger)


class MenuManager(QObject):
    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.window = window
        self.panels: list[MenuPanel] = []
        self.key = None
        self.enabled = False
        QApplication.instance().installEventFilter(self)

    # ------------------------------------------------------------------
    def _place(self, pan: MenuPanel, pos: QPoint, alt_x: int | None = None) -> None:
        pan.adjustSize()
        w, h = self.window.width(), self.window.height()
        x = pos.x()
        if x + pan.width() > w:
            x = (alt_x - pan.width()) if alt_x is not None else w - pan.width()
        y = pos.y()
        if y + pan.height() > h:
            y = max(0, h - pan.height())
        pan.move(max(0, x), max(0, y))
        pan.show()
        pan.raise_()

    def open(self, menu: QMenu, anchor: QWidget, rect: QRect, key=None) -> None:
        self.close_all()
        self.key = key
        pan = MenuPanel(self, menu, 0)
        self.panels = [pan]
        self._place(pan, anchor.mapTo(self.window, rect.bottomLeft()))
        bar = self.window.menuBar()
        if hasattr(key, "menu"):
            bar.setActiveAction(key)

    def open_child(self, parent: MenuPanel, row: _Row) -> None:
        self.close_deeper(parent.level)
        parent.child_row = row
        child = MenuPanel(self, row.act.menu(), parent.level + 1)
        self.panels.append(child)
        top_right = parent.mapTo(self.window, QPoint(parent.width() - 3, row.y() + 2))
        self._place(child, top_right, alt_x=parent.mapTo(self.window, QPoint(3, 0)).x())

    def close_deeper(self, level: int) -> None:
        while len(self.panels) > level + 1:
            p = self.panels.pop()
            p.hide()
            p.close()

    def close_all(self) -> None:
        for p in self.panels:
            p.hide()
            p.close()
        self.panels = []
        self.key = None
        try:
            self.window.menuBar().setActiveAction(None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def eventFilter(self, obj, ev) -> bool:
        if not self.panels:
            return False
        t = ev.type()
        if not isinstance(obj, QWidget):          # gli eventi passano prima dalla QWindow: si guardano solo quelli dei widget
            return False
        if t == QEvent.MouseButtonPress:
            w = obj
            if any(p is w or p.isAncestorOf(w) for p in self.panels):
                return False
            bar = self.window.menuBar()
            if obj is bar:
                act = bar.actionAt(ev.position().toPoint())
                if act is not None and act is self.key:      # secondo clic sulla stessa voce: chiude
                    self.close_all()
                    return True
                self.close_all()
                return False                                  # altra voce del menu: la gestisce la barra
            if obj is self.key:                               # secondo clic sul pulsante che ha aperto la tendina
                self.close_all()
                return True
            self.close_all()
            return True                                       # come i popup di Qt: il clic di chiusura non passa oltre
        if t == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
            self.close_all()
            return True
        if obj is self.window and t in (QEvent.Resize, QEvent.WindowDeactivate, QEvent.Move):
            self.close_all()
        return False


class InMenuBar(QMenuBar):
    """Barra dei menu che apre le tendine come pannelli interni alla finestra (se abilitato)."""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self.mgr = MenuManager(window)
        self.setMouseTracking(True)

    def mousePressEvent(self, e) -> None:
        act = self.actionAt(e.position().toPoint())
        if self.mgr.enabled and e.button() == Qt.LeftButton and act is not None and act.menu() is not None:
            self.mgr.open(act.menu(), self, self.actionGeometry(act), key=act)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        # stile «premi, trascina, rilascia»: la barra ha il grab del mouse, quindi il rilascio su una voce arriva qui
        if self.mgr.enabled and self.mgr.panels and e.button() == Qt.LeftButton:
            g = e.globalPosition().toPoint()
            for pan in reversed(self.mgr.panels):
                for r in pan.rows:
                    if r.rect().contains(r.mapFromGlobal(g)) and r.isVisible():
                        if not r.act.menu():
                            pan.row_clicked(r)
                        e.accept()
                        return
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self.mgr.enabled and self.mgr.panels:
            act = self.actionAt(e.position().toPoint())
            if act is not None and act.menu() is not None and act is not self.mgr.key:
                self.mgr.open(act.menu(), self, self.actionGeometry(act), key=act)
            e.accept()
            return
        super().mouseMoveEvent(e)
