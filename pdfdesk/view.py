# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# view.py: visualizzatore continuo delle pagine con strumenti di disegno e selezione.
from __future__ import annotations

from typing import Optional

import pymupdf as fitz

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QImage, QKeySequence, QPainter, QPainterPath, QPen, QPixmap,
                           QTransform)
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView)

from .core import AnnotInfo, PdfDocument

GAP = 14.0
MARGIN = 24.0
PT_TO_PX = 96.0 / 72.0
HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")

DRAG_RECT_TOOLS = {"rect", "ellipse", "text", "redact", "hl", "ul", "st", "textsel", "image", "sign", "sigbox", "grab"}
CLICK_TOOLS = {"edittext", "eraser", "form"}


def pix_to_qimage(pm) -> QImage:
    if pm.colorspace is None or pm.colorspace.n != 3:          # grigio, CMYK…: porta a RGB (senza alfa) prima di mostrare
        pm = fitz.Pixmap(fitz.csRGB, fitz.Pixmap(pm, 0) if pm.alpha else pm)
    fmt = QImage.Format_RGBA8888 if pm.alpha else QImage.Format_RGB888
    return QImage(pm.samples, pm.width, pm.height, pm.stride, fmt).copy()


class SelectionBox(QGraphicsItem):
    """Riquadro di selezione con maniglie (in unità pagina; le maniglie hanno dimensione fissa a schermo)."""

    def __init__(self) -> None:
        super().__init__()
        self.rect = QRectF()
        self.handle_px = 5.0
        self.show_handles = True
        self.setZValue(50)

    def boundingRect(self) -> QRectF:
        m = 20.0
        return self.rect.adjusted(-m, -m, m, m)

    def paint(self, p: QPainter, opt, widget=None) -> None:
        pen = QPen(QColor(30, 120, 230), 1.0, Qt.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect)
        if self.show_handles:
            p.setPen(QPen(QColor(30, 120, 230), 1.0))
            p.setBrush(QBrush(Qt.white))
            for pt in self.handle_points().values():
                s = self.handle_size()
                p.drawRect(QRectF(pt.x() - s, pt.y() - s, 2 * s, 2 * s))

    def handle_size(self) -> float:
        sc = self.scene().views()[0].transform().m11() if self.scene() and self.scene().views() else 1.0
        return self.handle_px / max(sc, 1e-6)

    def handle_points(self) -> dict[str, QPointF]:
        r = self.rect
        cx, cy = r.center().x(), r.center().y()
        return {"nw": r.topLeft(), "n": QPointF(cx, r.top()), "ne": r.topRight(), "e": QPointF(r.right(), cy),
                "se": r.bottomRight(), "s": QPointF(cx, r.bottom()), "sw": r.bottomLeft(), "w": QPointF(r.left(), cy)}

    def set_rect(self, r: QRectF) -> None:
        self.prepareGeometryChange()
        self.rect = QRectF(r)
        self.update()

    def hit_handle(self, pos: QPointF) -> Optional[str]:
        if not self.show_handles:
            return None
        s = self.handle_size() * 1.6
        for name, pt in self.handle_points().items():
            if abs(pos.x() - pt.x()) <= s and abs(pos.y() - pt.y()) <= s:
                return name
        return None


class DocView(QGraphicsView):
    rectDrawn = Signal(str, int, QRectF)               # strumento, pagina, rettangolo (punti pagina)
    strokeDrawn = Signal(str, int, list)               # strumento, pagina, [(x, y)]
    lineDrawn = Signal(str, int, QPointF, QPointF)
    pointClicked = Signal(str, int, QPointF)
    selectionChanged = Signal(int, int)                # pagina, xref (-1 = nessuna)
    transformRequested = Signal(int, int, QRectF, bool)  # pagina, xref, nuovo rettangolo, resize
    annotDoubleClicked = Signal(int, int)
    fieldClicked = Signal(int, int)                    # pagina, xref del campo del modulo
    deleteRequested = Signal()
    contentSelected = Signal(int, object)              # pagina, oggetto del contenuto (testo/immagine/grafica)
    contentTransformRequested = Signal(int, object, QRectF)   # pagina, oggetto, nuovo rettangolo (coordinate pagina)
    contentDoubleClicked = Signal(int, object)
    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)
    contextRequested = Signal(int, QPointF, object)    # pagina, punto (coordinate pagina), posizione globale del menu

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setBackgroundBrush(QBrush(QColor(86, 90, 96)))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setFocusPolicy(Qt.StrongFocus)
        self.doc: Optional[PdfDocument] = None
        self.zoom = 1.0
        self.tool = "select"
        self.style = {"pen": (0, 0, 0), "width": 2.0}
        self.page_rects: list[QRectF] = []
        self.page_items: dict[int, tuple[QGraphicsRectItem, QGraphicsPixmapItem, float, int]] = {}
        self._cur_page = 0
        self._sel = SelectionBox()
        self.scene_.addItem(self._sel)
        self._sel.hide()
        self.sel_page = -1
        self.sel_xref = -1
        self.sel_info: Optional[AnnotInfo] = None
        self.sel_content: Optional[dict] = None
        self._ghost: Optional[QGraphicsPixmapItem] = None
        self._drag = None
        self._preview: Optional[QGraphicsItem] = None
        self._pan_last: Optional[QPointF] = None
        self._found: list[QGraphicsRectItem] = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._update_visible)
        self.verticalScrollBar().valueChanged.connect(lambda _: self._schedule())
        self.horizontalScrollBar().valueChanged.connect(lambda _: self._schedule())
        self._apply_transform()

    # ------------------------------------------------------------------ documento e layout
    def set_document(self, doc: Optional[PdfDocument]) -> None:
        self.doc = doc
        self.clear_selection()
        self.reload()
        self.verticalScrollBar().setValue(0)

    def reload(self) -> None:
        """Ricostruisce il layout (dopo operazioni sulle pagine)."""
        for it in list(self.scene_.items()):
            if it is not self._sel:
                self.scene_.removeItem(it)
        self._found.clear()
        self.page_items.clear()
        self.page_rects = []
        self._ghost = None
        self._preview = None
        if self.doc is None:
            self.scene_.setSceneRect(QRectF())
            return
        sizes = [self.doc.page_size(i) for i in range(self.doc.page_count)]
        maxw = max((w for w, _ in sizes), default=0)
        y = MARGIN
        for i, (w, h) in enumerate(sizes):
            r = QRectF(MARGIN + (maxw - w) / 2, y, w, h)
            self.page_rects.append(r)
            bg = QGraphicsRectItem(r)
            bg.setBrush(QBrush(Qt.white))
            bg.setPen(QPen(QColor(40, 40, 40), 0))
            bg.setZValue(0)
            self.scene_.addItem(bg)
            pix = QGraphicsPixmapItem()
            pix.setZValue(1)
            pix.setTransformationMode(Qt.SmoothTransformation)
            pix.setPos(r.topLeft())
            self.scene_.addItem(pix)
            self.page_items[i] = (bg, pix, 0.0, -1)
            y += h + GAP
        self.scene_.setSceneRect(QRectF(0, 0, maxw + 2 * MARGIN, y - GAP + MARGIN))
        self.scene_.addItem(self._sel) if self._sel.scene() is None else None
        self._sel.setZValue(50)
        self._field_items = []
        self._draw_fields()
        self._schedule()

    # ------------------------------------------------------------------ evidenziazione campi del modulo
    def set_show_fields(self, on: bool) -> None:
        self._show_fields = on
        self._draw_fields()

    def _draw_fields(self) -> None:
        for it in getattr(self, "_field_items", []):
            if it.scene() is not None:
                self.scene_.removeItem(it)
        self._field_items = []
        if not getattr(self, "_show_fields", False) or not self.doc or not self.doc.has_form():
            return
        for pno in range(self.doc.page_count):
            if pno >= len(self.page_rects):
                break
            o = self.page_rects[pno].topLeft()
            for f in self.doc.list_fields(pno):
                it = QGraphicsRectItem(QRectF(f.rect.x0, f.rect.y0, f.rect.width, f.rect.height).translated(o))
                col = QColor(150, 150, 150, 70) if f.readonly or f.kind == "button" else QColor(60, 140, 255, 55)
                if f.kind == "signature":
                    col = QColor(60, 200, 120, 60)
                it.setBrush(QBrush(col))
                pen = QPen(QColor(40, 100, 220, 160), 0)
                it.setPen(pen)
                it.setZValue(25)
                it.setAcceptedMouseButtons(Qt.NoButton)
                self.scene_.addItem(it)
                self._field_items.append(it)

    def refresh_page(self, pno: int) -> None:
        if pno in self.page_items:
            bg, pix, _, _ = self.page_items[pno]
            self.page_items[pno] = (bg, pix, 0.0, -1)
        self._draw_fields()
        self._schedule()

    def refresh_all(self) -> None:
        for p in list(self.page_items):
            self.refresh_page(p)

    # ------------------------------------------------------------------ rendering a richiesta
    def _render_scale(self) -> float:
        dpr = self.devicePixelRatioF()
        return min(self.zoom * PT_TO_PX * dpr, 8.0)

    def _schedule(self) -> None:
        self._timer.start()

    def _visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def _update_visible(self) -> None:
        if not self.doc or not self.page_rects:
            return
        vis = self._visible_scene_rect()
        near = vis.adjusted(0, -vis.height(), 0, vis.height())
        far = vis.adjusted(0, -vis.height() * 3, 0, vis.height() * 3)
        rs = self._render_scale()
        for i, r in enumerate(self.page_rects):
            bg, pix, cur_rs, ver = self.page_items[i]
            if r.intersects(near):
                if abs(cur_rs - rs) > 1e-6 or ver != self.doc.version:
                    try:
                        img = pix_to_qimage(self.doc.render(i, rs))
                    except Exception:
                        continue
                    pix.setPixmap(QPixmap.fromImage(img))
                    pix.setScale(1.0 / rs)
                    self.page_items[i] = (bg, pix, rs, self.doc.version)
            elif not r.intersects(far) and not pix.pixmap().isNull():
                pix.setPixmap(QPixmap())
                self.page_items[i] = (bg, pix, 0.0, -1)
        self._track_current_page()
        if self.sel_page >= 0:
            self._reload_selection_rect()

    def _track_current_page(self) -> None:
        c = self._visible_scene_rect().center()
        best, bd = self._cur_page, 1e18
        for i, r in enumerate(self.page_rects):
            if r.top() <= c.y() <= r.bottom() + GAP:
                best = i
                break
            d = abs(r.center().y() - c.y())
            if d < bd:
                bd, best = d, i
        if best != self._cur_page:
            self._cur_page = best
            self.currentPageChanged.emit(best)

    def current_page(self) -> int:
        return self._cur_page

    # ------------------------------------------------------------------ zoom e navigazione
    def _apply_transform(self) -> None:
        s = self.zoom * PT_TO_PX
        self.setTransform(QTransform.fromScale(s, s))
        self.zoomChanged.emit(self.zoom)
        self._schedule()

    def set_zoom(self, z: float) -> None:
        self.zoom = max(0.1, min(z, 6.0))
        self._apply_transform()

    def fit_width(self) -> None:
        if not self.page_rects:
            return
        w = max(r.width() for r in self.page_rects) + 2 * MARGIN
        self.set_zoom((self.viewport().width() - 4) / (w * PT_TO_PX))

    def fit_page(self) -> None:
        if not self.page_rects:
            return
        r = self.page_rects[self._cur_page]
        zw = (self.viewport().width() - 4) / ((r.width() + 2 * MARGIN) * PT_TO_PX)
        zh = (self.viewport().height() - 4) / ((r.height() + 2 * MARGIN) * PT_TO_PX)
        self.set_zoom(min(zw, zh))
        self.go_to_page(self._cur_page)

    def go_to_page(self, pno: int) -> None:
        if 0 <= pno < len(self.page_rects):
            r = self.page_rects[pno]
            self.centerOn(r.center().x(), r.top() + min(r.height() / 2, self.viewport().height() / self.transform().m11() / 2))
            self._cur_page = pno
            self.currentPageChanged.emit(pno)

    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.15 if e.angleDelta().y() > 0 else 1 / 1.15))
            e.accept()
        else:
            super().wheelEvent(e)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._schedule()

    # ------------------------------------------------------------------ strumenti
    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._cancel_drag()
        if tool == "hand":
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().setCursor(Qt.OpenHandCursor)
        else:
            self.setDragMode(QGraphicsView.NoDrag)
            cur = Qt.ArrowCursor if tool in ("select", "editobj") else (Qt.IBeamCursor if tool in ("textsel", "text") else Qt.CrossCursor)
            self.viewport().setCursor(cur)
        if tool != "select":
            self._sel.hide_handles = True
        self.clear_selection()

    def _page_at(self, sp: QPointF, nearest: bool = True) -> int:
        for i, r in enumerate(self.page_rects):
            if r.adjusted(0, 0, 0, GAP / 2).contains(sp):
                return i
        if nearest and self.page_rects:
            return min(range(len(self.page_rects)), key=lambda i: abs(self.page_rects[i].center().y() - sp.y()))
        return -1

    def _local(self, pno: int, sp: QPointF, clamp: bool = True) -> QPointF:
        r = self.page_rects[pno]
        p = sp - r.topLeft()
        if clamp:
            p = QPointF(min(max(p.x(), 0), r.width()), min(max(p.y(), 0), r.height()))
        return p

    # ------------------------------------------------------------------ selezione
    def select(self, pno: int, xref: int) -> None:
        self.sel_page, self.sel_xref = pno, xref
        self._reload_selection_rect()
        self.selectionChanged.emit(pno, xref)

    def clear_selection(self) -> None:
        had = self.sel_page >= 0
        self.sel_page, self.sel_xref, self.sel_info, self.sel_content = -1, -1, None, None
        self._sel.hide()
        self._remove_ghost()
        if had:
            self.selectionChanged.emit(-1, -1)

    def select_content(self, pno: int, obj: dict) -> None:
        """Seleziona un oggetto del contenuto della pagina (testo, immagine, grafica) con il suo riquadro."""
        self.sel_page, self.sel_xref, self.sel_info, self.sel_content = pno, -2, None, obj
        r = obj["rect"]
        o = self.page_rects[pno].topLeft()
        self._sel.set_rect(QRectF(o.x() + r.x0, o.y() + r.y0, r.width, r.height))
        self._sel.show_handles = True
        self._sel.show()
        self.contentSelected.emit(pno, obj)

    def _press_content(self, sp: QPointF, pno: int) -> None:
        if self._sel.isVisible() and self.sel_content is not None:
            h = self._sel.hit_handle(sp)
            if h:
                self._drag = {"kind": "resize", "handle": h, "start": sp, "orig": QRectF(self._sel.rect), "page": self.sel_page}
                self._make_ghost()
                return
            if self._sel.rect.contains(sp):
                self._drag = {"kind": "move", "start": sp, "orig": QRectF(self._sel.rect), "page": self.sel_page, "moved": False}
                self._make_ghost()
                return
        local = self._local(pno, sp, clamp=False)
        obj = self.doc.content_at(pno, (local.x(), local.y()))
        if obj is None:
            self.clear_selection()
            return
        self.clear_selection()
        self.select_content(pno, obj)
        self._drag = {"kind": "move", "start": sp, "orig": QRectF(self._sel.rect), "page": pno, "moved": False}
        self._make_ghost()

    def _reload_selection_rect(self) -> None:
        if self.sel_content is not None:          # dopo ogni modifica gli oggetti del contenuto vanno ricercati
            self.clear_selection()
            return
        if not self.doc or self.sel_page < 0 or self.sel_page >= len(self.page_rects):
            self._sel.hide()
            return
        info = self.doc.annot_info(self.sel_page, self.sel_xref)
        if info is None:
            self.clear_selection()
            return
        self.sel_info = info
        r = info.rect
        o = self.page_rects[self.sel_page].topLeft()
        self._sel.set_rect(QRectF(o.x() + r.x0, o.y() + r.y0, r.width, r.height))
        self._sel.show_handles = info.resizable
        self._sel.show()

    def _remove_ghost(self) -> None:
        if self._ghost is not None:
            self.scene_.removeItem(self._ghost)
            self._ghost = None

    def _make_ghost(self) -> None:
        self._remove_ghost()
        _, pix, rs, _ = self.page_items[self.sel_page]
        if pix.pixmap().isNull() or rs <= 0:
            return
        origin = self.page_rects[self.sel_page].topLeft()
        r = self._sel.rect.translated(-origin)
        crop = pix.pixmap().copy(int(r.x() * rs), int(r.y() * rs), max(int(r.width() * rs), 1), max(int(r.height() * rs), 1))
        g = QGraphicsPixmapItem(crop)
        g.setOpacity(0.7)
        g.setZValue(40)
        g.setTransformationMode(Qt.SmoothTransformation)
        self.scene_.addItem(g)
        self._ghost = g
        self._ghost_src = QRectF(0, 0, crop.width(), crop.height())
        self._place_ghost(self._sel.rect)

    def _place_ghost(self, r: QRectF) -> None:
        if self._ghost is None:
            return
        self._ghost.setPos(r.topLeft())
        sx = r.width() / max(self._ghost_src.width(), 1)
        sy = r.height() / max(self._ghost_src.height(), 1)
        self._ghost.setTransform(QTransform.fromScale(sx, sy))

    # ------------------------------------------------------------------ mouse
    def contextMenuEvent(self, e) -> None:
        """Tasto destro: seleziona l'oggetto sotto il cursore (annotazione, poi contenuto del PDF) e chiede il menu contestuale."""
        if not self.doc:
            return
        sp = self.mapToScene(e.pos())
        pno = self._page_at(sp)
        if pno < 0:
            return
        loc = self._local(pno, sp, clamp=False)
        # clic destro dentro la selezione corrente: la si mantiene
        if not (self._sel.isVisible() and self._sel.rect.contains(sp) and self.sel_page == pno):
            xref = self.doc.annot_at(pno, (loc.x(), loc.y()))
            if xref is not None:
                self.select(pno, xref)
            else:
                obj = self.doc.content_at(pno, (loc.x(), loc.y()))
                if obj is not None:
                    self.select_content(pno, obj)
                else:
                    self.clear_selection()
        self.contextRequested.emit(pno, loc, e.globalPos())
        e.accept()

    def mousePressEvent(self, e) -> None:
        if not self.doc:
            return super().mousePressEvent(e)
        if e.button() == Qt.MiddleButton:
            self._pan_last = e.position()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton or self.tool == "hand":
            return super().mousePressEvent(e)
        sp = self.mapToScene(e.position().toPoint())
        pno = self._page_at(sp)
        if pno < 0:
            return
        t = self.tool
        if t == "select":
            self._press_select(sp, pno)
        elif t == "editobj":
            self._press_content(sp, pno)
        elif t in ("pen", "highlighter"):
            path = QPainterPath(sp)
            item = QGraphicsPathItem(path)
            col = QColor.fromRgbF(*self.style["pen"])
            col.setAlphaF(self.style.get("opacity", 1.0))
            pen = QPen(col, self.style["width"], Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            item.setPen(pen)
            item.setZValue(60)
            self.scene_.addItem(item)
            self._preview = item
            self._drag = {"kind": "stroke", "page": pno, "pts": [sp], "path": path}
        elif t in ("line", "arrow"):
            item = QGraphicsPathItem()
            item.setPen(QPen(QColor.fromRgbF(*self.style["pen"]), self.style["width"]))
            item.setZValue(60)
            self.scene_.addItem(item)
            self._preview = item
            self._drag = {"kind": "line", "page": pno, "a": sp, "b": sp}
        elif t in DRAG_RECT_TOOLS:
            item = QGraphicsRectItem()
            pen = QPen(QColor(30, 120, 230), 1, Qt.DashLine)
            pen.setCosmetic(True)
            item.setPen(pen)
            if t == "redact":
                item.setBrush(QBrush(QColor(0, 0, 0, 90)))
            elif t in ("hl", "textsel"):
                item.setBrush(QBrush(QColor(255, 230, 0, 70)))
            item.setZValue(60)
            self.scene_.addItem(item)
            self._preview = item
            self._drag = {"kind": "rect", "page": pno, "a": sp, "b": sp}
        elif t == "form":
            loc = self._local(pno, sp, clamp=False)
            f = self.doc.field_at(pno, (loc.x(), loc.y()))
            if f is not None:
                self.fieldClicked.emit(pno, f.xref)
        elif t in CLICK_TOOLS:
            self.pointClicked.emit(t, pno, self._local(pno, sp))

    def _press_select(self, sp: QPointF, pno: int) -> None:
        h = self._sel.hit_handle(sp) if self._sel.isVisible() else None
        if h and self.sel_info and self.sel_info.resizable:
            self._drag = {"kind": "resize", "handle": h, "start": sp, "orig": QRectF(self._sel.rect), "page": self.sel_page}
            self._make_ghost()
            return
        if self._sel.isVisible() and self._sel.rect.contains(sp) and self.sel_info and self.sel_info.movable:
            self._drag = {"kind": "move", "start": sp, "orig": QRectF(self._sel.rect), "page": self.sel_page, "moved": False}
            self._make_ghost()
            return
        local = self._local(pno, sp, clamp=False)
        xref = self.doc.annot_at(pno, (local.x(), local.y()))
        if xref is None:
            self.clear_selection()
            return
        self.select(pno, xref)
        if self.sel_info and self.sel_info.movable:
            self._drag = {"kind": "move", "start": sp, "orig": QRectF(self._sel.rect), "page": pno, "moved": False}
            self._make_ghost()

    def mouseMoveEvent(self, e) -> None:
        if self._pan_last is not None:
            d = e.position() - self._pan_last
            self._pan_last = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        d = self._drag
        if d is None:
            if self.tool in ("select", "editobj") and self._sel.isVisible():
                sp = self.mapToScene(e.position().toPoint())
                h = self._sel.hit_handle(sp)
                cur = {"nw": Qt.SizeFDiagCursor, "se": Qt.SizeFDiagCursor, "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
                       "n": Qt.SizeVerCursor, "s": Qt.SizeVerCursor, "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor}.get(h)
                self.viewport().setCursor(cur if cur else (Qt.SizeAllCursor if self._sel.rect.contains(sp) else Qt.ArrowCursor))
            return super().mouseMoveEvent(e)
        sp = self.mapToScene(e.position().toPoint())
        k = d["kind"]
        if k == "stroke":
            sp = self._clamp(d["page"], sp)
            d["pts"].append(sp)
            d["path"].lineTo(sp)
            self._preview.setPath(d["path"])
        elif k == "line":
            d["b"] = self._clamp(d["page"], sp)
            p = QPainterPath(d["a"])
            p.lineTo(d["b"])
            self._preview.setPath(p)
        elif k == "rect":
            d["b"] = self._clamp(d["page"], sp)
            self._preview.setRect(QRectF(d["a"], d["b"]).normalized())
        elif k == "move":
            delta = sp - d["start"]
            if not d["moved"] and delta.manhattanLength() * self.transform().m11() < 3:
                return
            d["moved"] = True
            r = d["orig"].translated(delta)
            pr = self.page_rects[d["page"]]
            r.moveLeft(min(max(r.left(), pr.left() - r.width() + 10), pr.right() - 10))
            r.moveTop(min(max(r.top(), pr.top() - r.height() + 10), pr.bottom() - 10))
            self._sel.set_rect(r)
            self._place_ghost(r)
        elif k == "resize":
            r = self._resized(d["orig"], d["handle"], sp - d["start"],
                              keep_ratio=not (e.modifiers() & Qt.ShiftModifier) and (
                                  (self.sel_info is not None and self.sel_info.type == 13) or
                                  (self.sel_content is not None and self.sel_content["kind"] == "image")))
            self._sel.set_rect(r)
            self._place_ghost(r)

    def _clamp(self, pno: int, sp: QPointF) -> QPointF:
        r = self.page_rects[pno]
        return QPointF(min(max(sp.x(), r.left()), r.right()), min(max(sp.y(), r.top()), r.bottom()))

    @staticmethod
    def _resized(orig: QRectF, handle: str, d: QPointF, keep_ratio: bool = False) -> QRectF:
        x0, y0, x1, y1 = orig.left(), orig.top(), orig.right(), orig.bottom()
        if "w" in handle:
            x0 += d.x()
        if "e" in handle:
            x1 += d.x()
        if "n" in handle:
            y0 += d.y()
        if "s" in handle:
            y1 += d.y()
        r = QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized()
        if keep_ratio and orig.height() > 0 and len(handle) == 2:
            ratio = orig.width() / orig.height()
            w = r.width()
            h = w / ratio
            if "n" in handle:
                r.setTop(r.bottom() - h)
            else:
                r.setBottom(r.top() + h)
        if r.width() < 4:
            r.setWidth(4)
        if r.height() < 4:
            r.setHeight(4)
        return r

    def mouseReleaseEvent(self, e) -> None:
        if self._pan_last is not None and e.button() == Qt.MiddleButton:
            self._pan_last = None
            self.set_tool(self.tool)
            return
        d = self._drag
        if d is None or e.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(e)
        self._drag = None
        k = d["kind"]
        pno = d["page"]
        if k in ("stroke", "line", "rect"):
            self._remove_preview()
        if k == "stroke":
            pts = d["pts"]
            if len(pts) < 2:
                pts = pts + [pts[0] + QPointF(0.1, 0.1)]
            o = self.page_rects[pno].topLeft()
            self.strokeDrawn.emit(self.tool, pno, [(p.x() - o.x(), p.y() - o.y()) for p in pts])
        elif k == "line":
            a, b = self._local(pno, d["a"]), self._local(pno, d["b"])
            if (a - b).manhattanLength() > 2:
                self.lineDrawn.emit(self.tool, pno, a, b)
        elif k == "rect":
            r = QRectF(self._local(pno, d["a"]), self._local(pno, d["b"])).normalized()
            if r.width() < 3 and r.height() < 3:
                self.pointClicked.emit(self.tool, pno, r.topLeft())
            else:
                self.rectDrawn.emit(self.tool, pno, r)
        elif k in ("move", "resize"):
            self._remove_ghost()
            changed = k == "resize" or d.get("moved")
            if changed and self.sel_content is not None:
                o = self.page_rects[d["page"]].topLeft()
                self.contentTransformRequested.emit(d["page"], self.sel_content, self._sel.rect.translated(-o))
            elif changed and self.sel_info:
                o = self.page_rects[d["page"]].topLeft()
                r = self._sel.rect.translated(-o)
                self.transformRequested.emit(d["page"], self.sel_xref, r, k == "resize")
            else:
                self._sel.set_rect(d["orig"])

    def mouseDoubleClickEvent(self, e) -> None:
        if self.tool == "editobj" and self.doc and e.button() == Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint())
            pno = self._page_at(sp, nearest=False)
            if pno >= 0:
                l = self._local(pno, sp, clamp=False)
                obj = self.doc.content_at(pno, (l.x(), l.y()))
                if obj is not None and obj["kind"] == "text":
                    self.contentDoubleClicked.emit(pno, obj)
                    return
        if self.tool == "select" and self.doc and e.button() == Qt.LeftButton:
            sp = self.mapToScene(e.position().toPoint())
            pno = self._page_at(sp, nearest=False)
            if pno >= 0:
                l = self._local(pno, sp, clamp=False)
                x = self.doc.annot_at(pno, (l.x(), l.y()))
                if x is not None:
                    self.annotDoubleClicked.emit(pno, x)
                    return
        super().mouseDoubleClickEvent(e)

    def _remove_preview(self) -> None:
        if self._preview is not None:
            self.scene_.removeItem(self._preview)
            self._preview = None

    def _cancel_drag(self) -> None:
        self._drag = None
        self._remove_preview()
        self._remove_ghost()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.sel_page >= 0:
            self.deleteRequested.emit()
            return
        if e.key() == Qt.Key_Escape:
            self._cancel_drag()
            self.clear_selection()
            return
        arrows = {Qt.Key_Left: (-1, 0), Qt.Key_Right: (1, 0), Qt.Key_Up: (0, -1), Qt.Key_Down: (0, 1)}
        if e.key() in arrows and self.sel_content is not None and self.tool == "editobj":
            step = 10 if e.modifiers() & Qt.ShiftModifier else 1
            dx, dy = arrows[e.key()]
            o = self.page_rects[self.sel_page].topLeft()
            self.contentTransformRequested.emit(self.sel_page, self.sel_content,
                                                self._sel.rect.translated(-o).translated(dx * step, dy * step))
            return
        if e.key() in arrows and self.sel_page >= 0 and self.sel_info and self.sel_info.movable and self.tool == "select":
            step = 10 if e.modifiers() & Qt.ShiftModifier else 1
            dx, dy = arrows[e.key()]
            o = self.page_rects[self.sel_page].topLeft()
            r = self._sel.rect.translated(-o).translated(dx * step, dy * step)
            self.transformRequested.emit(self.sel_page, self.sel_xref, r, False)
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------------ risultati di ricerca
    def set_found(self, items: list[tuple[int, QRectF]], current: int = -1) -> None:
        for it in self._found:
            self.scene_.removeItem(it)
        self._found.clear()
        for i, (pno, r) in enumerate(items):
            o = self.page_rects[pno].topLeft()
            it = QGraphicsRectItem(r.translated(o))
            it.setPen(QPen(Qt.NoPen))
            it.setBrush(QBrush(QColor(255, 140, 0, 130) if i == current else QColor(255, 235, 0, 110)))
            it.setZValue(30)
            self.scene_.addItem(it)
            self._found.append(it)
        if 0 <= current < len(items):
            pno, r = items[current]
            o = self.page_rects[pno].topLeft()
            self.ensureVisible(r.translated(o), 120, 120)
