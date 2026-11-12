# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# icons.py: icone disegnate via codice (nessun file esterno, funzionano in tema chiaro e scuro).
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication


def _fg() -> QColor:
    app = QApplication.instance()
    return app.palette().windowText().color() if app else QColor(40, 40, 40)


class _Engine(QIconEngine):
    """Icona vettoriale che si ridisegna con i colori della tavolozza corrente (tema chiaro/scuro al volo)."""

    def __init__(self, name: str, color: QColor | None = None) -> None:
        super().__init__()
        self.name, self.color = name, color

    def clone(self):
        return _Engine(self.name, self.color)

    def paint(self, p: QPainter, rect, mode, state) -> None:
        col = QColor(self.color) if self.color else _fg()
        if mode == QIcon.Disabled:
            col.setAlphaF(0.35)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(rect.x(), rect.y())
        s = min(rect.width(), rect.height()) / 48.0
        p.scale(s, s)
        p.setPen(QPen(col, 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        draw = _DRAW.get(self.name)
        if draw:
            draw(p, col)
        p.restore()

    def pixmap(self, size, mode, state) -> QPixmap:
        pm = QPixmap(size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm


def icon(name: str, size: int = 48, color: QColor | None = None) -> QIcon:
    return QIcon(_Engine(name, color))


def _select(p, c):
    poly = QPolygonF([QPointF(12, 8), QPointF(12, 38), QPointF(20, 31), QPointF(26, 43), QPointF(31, 41), QPointF(25, 29), QPointF(35, 29)])
    p.setBrush(c)
    p.drawPolygon(poly)


def _hand(p, c):
    path = QPainterPath(QPointF(14, 28))
    path.lineTo(14, 16); path.moveTo(20, 24); path.lineTo(20, 10); path.moveTo(26, 24); path.lineTo(26, 12)
    path.moveTo(32, 26); path.lineTo(32, 18)
    path.moveTo(14, 28); path.cubicTo(14, 40, 20, 42, 26, 42); path.cubicTo(34, 42, 36, 36, 36, 30)
    p.drawPath(path)


def _textsel(p, c):
    p.drawLine(24, 8, 24, 40); p.drawLine(18, 8, 30, 8); p.drawLine(18, 40, 30, 40)


def _pen(p, c):
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(10, 38), QPointF(14, 28), QPointF(34, 8), QPointF(40, 14), QPointF(20, 34)]))
    p.setBrush(Qt.NoBrush)
    p.drawLine(10, 40, 18, 40)


def _highlighter(p, c):
    p.setBrush(QColor(255, 220, 0, 200)); p.setPen(Qt.NoPen)
    p.drawRect(QRectF(8, 30, 32, 10))
    p.setPen(QPen(c, 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); p.setBrush(Qt.NoBrush)
    p.drawPolygon(QPolygonF([QPointF(14, 26), QPointF(28, 8), QPointF(38, 16), QPointF(26, 30)]))


def _rect(p, c): p.drawRect(QRectF(9, 13, 30, 22))
def _ellipse(p, c): p.drawEllipse(QRectF(8, 12, 32, 24))
def _line(p, c): p.drawLine(10, 38, 38, 10)


def _arrow(p, c):
    p.drawLine(10, 38, 36, 12)
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(40, 8), QPointF(28, 12), QPointF(36, 20)]))


def _text(p, c):
    p.drawLine(12, 12, 36, 12); p.drawLine(24, 12, 24, 38); p.drawLine(18, 38, 30, 38)


def _image(p, c):
    p.drawRect(QRectF(8, 10, 32, 28))
    p.drawEllipse(QRectF(14, 15, 6, 6))
    path = QPainterPath(QPointF(8, 36)); path.lineTo(20, 24); path.lineTo(28, 31); path.lineTo(34, 25); path.lineTo(40, 32)
    p.drawPath(path)


def _sign(p, c):
    path = QPainterPath(QPointF(6, 30))
    path.cubicTo(12, 12, 16, 12, 16, 26); path.cubicTo(16, 36, 22, 30, 24, 22)
    path.cubicTo(26, 14, 30, 34, 36, 24); path.lineTo(42, 22)
    p.drawPath(path); p.drawLine(6, 40, 42, 40)


def _hl(p, c):
    p.setPen(Qt.NoPen); p.setBrush(QColor(255, 220, 0, 200)); p.drawRect(QRectF(7, 18, 34, 14))
    p.setPen(QPen(c, 3.4)); p.drawLine(12, 28, 12, 22); p.drawLine(12, 25, 18, 25); p.drawLine(18, 28, 18, 22)


def _ul(p, c):
    p.drawLine(12, 10, 12, 28); p.drawLine(12, 28, 12, 28); p.drawLine(24, 10, 24, 28); p.drawLine(12, 19, 24, 19)
    p.drawLine(8, 38, 40, 38)


def _st(p, c):
    p.drawLine(12, 10, 12, 36); p.drawLine(24, 10, 24, 36); p.drawLine(12, 22, 24, 22)
    p.drawLine(6, 23, 42, 23)


def _redact(p, c):
    p.setBrush(c); p.drawRect(QRectF(7, 17, 34, 14))


def _group(p, c):
    p.drawRect(QRectF(6, 8, 18, 14)); p.drawRect(QRectF(24, 26, 18, 14))
    pen = QPen(p.pen()); pen.setStyle(Qt.DashLine); pen.setWidthF(2.0); p.setPen(pen); p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(3, 5, 42, 38))


def _ungroup(p, c):
    p.drawRect(QRectF(5, 7, 18, 14)); p.drawRect(QRectF(27, 27, 16, 14))
    pen = QPen(p.pen()); pen.setStyle(Qt.DashLine); pen.setWidthF(2.0); p.setPen(pen)
    p.drawLine(24, 24, 28, 24)


def _applyred(p, c):
    p.setBrush(c); p.drawRect(QRectF(5, 9, 30, 11))
    p.setBrush(Qt.NoBrush)
    pen = QPen(p.pen()); pen.setWidthF(max(pen.widthF(), 3.2)); p.setPen(pen)
    p.drawPolyline(QPolygonF([QPointF(14, 31), QPointF(21, 39), QPointF(41, 22)]))


def _edittext(p, c):
    p.drawRect(QRectF(7, 10, 34, 28)); p.drawLine(14, 20, 34, 20); p.drawLine(14, 28, 26, 28)


def _eraser(p, c):
    p.setBrush(QColor(c.red(), c.green(), c.blue(), 60))
    p.drawPolygon(QPolygonF([QPointF(8, 30), QPointF(26, 10), QPointF(40, 22), QPointF(24, 40), QPointF(14, 40)]))
    p.drawLine(16, 22, 32, 36)


def _comment(p, c):
    path = QPainterPath(QPointF(8, 10))
    path.lineTo(40, 10); path.lineTo(40, 30); path.lineTo(26, 30); path.lineTo(16, 40); path.lineTo(17, 30); path.lineTo(8, 30); path.closeSubpath()
    p.drawPath(path)
    p.drawLine(15, 17, 33, 17); p.drawLine(15, 23, 28, 23)


def _app(p, c):
    p.setPen(Qt.NoPen); p.setBrush(QColor(200, 40, 40)); p.drawRoundedRect(QRectF(6, 4, 36, 40), 5, 5)
    p.setPen(QPen(Qt.white, 3.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)); p.setBrush(Qt.NoBrush)
    p.drawLine(15, 14, 15, 34); p.drawLine(15, 14, 22, 14); p.drawArc(QRectF(11, 14, 14, 10), 90 * 16, -180 * 16)
    p.drawLine(30, 34, 36, 34); p.drawLine(30, 28, 36, 28)



def _page(p, c, fold=True):
    p.drawPolygon(QPolygonF([QPointF(11, 6), QPointF(30, 6), QPointF(38, 14), QPointF(38, 42), QPointF(11, 42)]))
    if fold:
        p.drawLine(30, 6, 30, 14); p.drawLine(30, 14, 38, 14)


def _open(p, c):
    p.drawPolygon(QPolygonF([QPointF(6, 12), QPointF(19, 12), QPointF(23, 17), QPointF(38, 17), QPointF(38, 22), QPointF(12, 22), QPointF(6, 40)]))
    p.drawPolygon(QPolygonF([QPointF(12, 22), QPointF(43, 22), QPointF(37, 40), QPointF(6, 40)]))


def _save(p, c):
    p.drawPolygon(QPolygonF([QPointF(8, 8), QPointF(35, 8), QPointF(40, 13), QPointF(40, 40), QPointF(8, 40)]))
    p.drawRect(QRectF(15, 8, 16, 10)); p.drawRect(QRectF(14, 27, 20, 13))


def _saveas(p, c):
    _save(p, c)
    p.setBrush(QColor(220, 60, 60)); p.setPen(Qt.NoPen); p.drawEllipse(QRectF(30, 30, 16, 16))
    p.setPen(QPen(Qt.white, 3, Qt.SolidLine, Qt.RoundCap)); p.drawLine(38, 33, 38, 43); p.drawLine(33, 38, 43, 38)


def _new(p, c):
    _page(p, c); p.drawLine(24, 20, 24, 34); p.drawLine(17, 27, 31, 27)


def _undo(p, c):
    path = QPainterPath(QPointF(14, 18)); path.lineTo(32, 18); path.cubicTo(42, 18, 42, 36, 32, 36); path.lineTo(18, 36)
    p.drawPath(path)
    p.setBrush(c); p.drawPolygon(QPolygonF([QPointF(6, 18), QPointF(17, 10), QPointF(17, 26)]))


def _redo(p, c):
    path = QPainterPath(QPointF(34, 18)); path.lineTo(16, 18); path.cubicTo(6, 18, 6, 36, 16, 36); path.lineTo(30, 36)
    p.drawPath(path)
    p.setBrush(c); p.drawPolygon(QPolygonF([QPointF(42, 18), QPointF(31, 10), QPointF(31, 26)]))


def _mag(p, c):
    p.drawEllipse(QRectF(8, 8, 24, 24)); p.drawLine(28, 28, 41, 41)


def _zin(p, c):
    _mag(p, c); p.drawLine(14, 20, 26, 20); p.drawLine(20, 14, 20, 26)


def _zout(p, c):
    _mag(p, c); p.drawLine(14, 20, 26, 20)


def _fitw(p, c):
    p.drawLine(7, 10, 7, 38); p.drawLine(41, 10, 41, 38); p.drawLine(12, 24, 36, 24)
    p.setBrush(c); p.drawPolygon(QPolygonF([QPointF(12, 24), QPointF(19, 19), QPointF(19, 29)]))
    p.drawPolygon(QPolygonF([QPointF(36, 24), QPointF(29, 19), QPointF(29, 29)]))


def _fitp(p, c):
    p.drawRect(QRectF(14, 10, 20, 28))
    for x, y, dx, dy in ((6, 6, 1, 1), (42, 6, -1, 1), (6, 42, 1, -1), (42, 42, -1, -1)):
        p.drawLine(x, y, x + 7 * dx, y); p.drawLine(x, y, x, y + 7 * dy)


def _rot(p, c, left):
    p.drawArc(QRectF(9, 11, 30, 30), (110 if left else 70) * 16, (250 if left else -250) * 16)
    x = 14 if left else 34
    p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(x, 6), QPointF(x + (9 if left else -9), 12), QPointF(x + (0), 19)]))


def _rotl(p, c): _rot(p, c, True)
def _rotr(p, c): _rot(p, c, False)


def _badge(p, c):
    p.drawEllipse(QRectF(10, 6, 28, 28)); p.drawLine(18, 20, 23, 25); p.drawLine(23, 25, 31, 15)
    p.drawLine(16, 32, 12, 43); p.drawLine(32, 32, 36, 43)


def _shield(p, c):
    path = QPainterPath(QPointF(24, 6)); path.lineTo(39, 12); path.lineTo(39, 24); path.cubicTo(39, 34, 31, 40, 24, 43)
    path.cubicTo(17, 40, 9, 34, 9, 24); path.lineTo(9, 12); path.closeSubpath(); p.drawPath(path)
    p.drawLine(17, 24, 22, 29); p.drawLine(22, 29, 32, 18)


def _std(p, c):
    _page(p, c); p.drawLine(17, 27, 22, 32); p.drawLine(22, 32, 31, 21)


def _gear(p, c):
    import math
    p.drawEllipse(QRectF(16, 16, 16, 16))
    for i in range(8):
        a = math.radians(i * 45)
        p.drawLine(24 + 11 * math.cos(a), 24 + 11 * math.sin(a), 24 + 17 * math.cos(a), 24 + 17 * math.sin(a))
    p.drawEllipse(QRectF(21, 21, 6, 6))


def _dup(p, c):
    p.drawRect(QRectF(7, 7, 22, 28)); p.drawRect(QRectF(19, 15, 22, 28))


def _blank(p, c):
    _page(p, c, False); p.drawLine(24, 18, 24, 32); p.drawLine(17, 25, 31, 25)


def _insert(p, c):
    _page(p, c); p.drawLine(24, 18, 24, 34); p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(24, 36), QPointF(18, 28), QPointF(30, 28)]))


def _extract(p, c):
    _page(p, c); p.drawLine(24, 36, 24, 20); p.setBrush(c)
    p.drawPolygon(QPolygonF([QPointF(24, 16), QPointF(18, 24), QPointF(30, 24)]))


def _trash(p, c):
    p.drawLine(9, 12, 39, 12); p.drawLine(19, 12, 19, 7); p.drawLine(19, 7, 29, 7); p.drawLine(29, 7, 29, 12)
    p.drawPolygon(QPolygonF([QPointF(12, 12), QPointF(36, 12), QPointF(34, 42), QPointF(14, 42)]))
    p.drawLine(20, 19, 20, 35); p.drawLine(28, 19, 28, 35)


def _prev(p, c): p.drawPolyline(QPolygonF([QPointF(30, 10), QPointF(16, 24), QPointF(30, 38)]))
def _next(p, c): p.drawPolyline(QPolygonF([QPointF(18, 10), QPointF(32, 24), QPointF(18, 38)]))


def _thumbs(p, c):
    for x in (7, 27):
        for y in (7, 27):
            p.drawRect(QRectF(x, y, 14, 14))


def _info(p, c):
    p.drawEllipse(QRectF(6, 6, 36, 36)); p.drawLine(24, 21, 24, 33); p.drawPoint(QPointF(24, 15))


def _close(p, c): p.drawLine(11, 11, 37, 37); p.drawLine(37, 11, 11, 37)


def _editobj(p, c):
    pen = QPen(c, 2.6, Qt.DashLine); p.setPen(pen); p.drawRect(QRectF(7, 7, 28, 28)); p.setPen(QPen(c, 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(c)
    for x, y in ((7, 7), (35, 7), (7, 35)):
        p.drawRect(QRectF(x - 3, y - 3, 6, 6))
    p.drawPolygon(QPolygonF([QPointF(26, 24), QPointF(26, 44), QPointF(31, 39), QPointF(35, 46), QPointF(39, 44), QPointF(35, 37), QPointF(42, 37)]))


def _form(p, c):
    p.drawRect(QRectF(8, 6, 32, 36)); p.drawRect(QRectF(13, 12, 7, 7)); p.drawLine(15, 16, 17, 18); p.drawLine(17, 18, 21, 11)
    p.drawLine(24, 15, 35, 15); p.drawRect(QRectF(13, 26, 22, 9))


def _cert(p, c):
    _page(p, c); p.drawEllipse(QRectF(18, 24, 12, 12))


def _print(p, c):
    p.drawRect(QRectF(14, 6, 20, 12)); p.drawRoundedRect(QRectF(6, 18, 36, 16), 3, 3); p.drawRect(QRectF(14, 28, 20, 14))
    p.drawLine(18, 34, 30, 34); p.drawLine(18, 38, 30, 38)


def _export(p, c):
    _page(p, c); p.drawLine(24, 36, 24, 20)
    p.setBrush(c); p.drawPolygon(QPolygonF([QPointF(24, 14), QPointF(18, 21), QPointF(30, 21)]))


def _grab(p, c):
    p.drawLine(14, 6, 14, 34); p.drawLine(6, 14, 34, 14); p.drawLine(34, 14, 34, 42); p.drawLine(14, 34, 42, 34)
    p.drawRect(QRectF(19, 19, 10, 10))


def _tabnext(p, c):
    p.drawRect(QRectF(6, 14, 36, 24)); p.drawLine(6, 22, 42, 22); p.drawLine(24, 14, 24, 22)


def _home(p, c):
    p.drawPolygon(QPolygonF([QPointF(6, 24), QPointF(24, 8), QPointF(42, 24)]))
    p.drawRect(QRectF(11, 22, 26, 18)); p.drawRect(QRectF(20, 29, 8, 11))


def _merge(p, c):
    p.drawRect(QRectF(6, 6, 18, 24)); p.drawRect(QRectF(14, 14, 18, 24))
    p.setBrush(c); p.drawPolygon(QPolygonF([QPointF(36, 24), QPointF(28, 18), QPointF(28, 30)]))


def _scan(p, c):
    p.drawRoundedRect(QRectF(5, 26, 38, 12), 3, 3); p.drawRect(QRectF(13, 6, 22, 16))
    p.drawLine(16, 11, 32, 11); p.drawLine(16, 16, 28, 16); p.drawLine(9, 32, 39, 32)


_DRAW = {"home": _home, "merge": _merge, "scan": _scan, "select": _select, "hand": _hand, "textsel": _textsel, "pen": _pen, "highlighter": _highlighter, "rect": _rect,
         "ellipse": _ellipse, "line": _line, "arrow": _arrow, "text": _text, "image": _image, "sign": _sign, "hl": _hl,
         "ul": _ul, "st": _st, "redact": _redact, "applyred": _applyred, "group": _group, "ungroup": _ungroup, "edittext": _edittext, "eraser": _eraser, "comment": _comment, "sigbox": _sign, "app": _app,
         "open": _open, "save": _save, "saveas": _saveas, "new": _new, "undo": _undo, "redo": _redo, "zoom": _mag,
         "zin": _zin, "zout": _zout, "fitw": _fitw, "fitp": _fitp, "rotl": _rotl, "rotr": _rotr, "sigdig": _badge,
         "verify": _shield, "std": _std, "prefs": _gear, "dup": _dup, "blank": _blank, "insert": _insert,
         "extract": _extract, "trash": _trash, "prev": _prev, "next": _next, "thumbs": _thumbs, "info": _info,
         "close": _close, "form": _form, "cert": _cert, "editobj": _editobj, "find": _mag, "flatten": _std, "z100": _page, "sigmanage": _sign, "print": _print, "export": _export, "tabs": _tabnext, "grab": _grab}


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 32, 48, 64, 128, 256):
        ic.addPixmap(icon("app", s).pixmap(s, s))
    return ic
