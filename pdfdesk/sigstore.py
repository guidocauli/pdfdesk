# PDFDesk — Guido Cauli <guido.cauli@gmail.com>
# sigstore.py: libreria locale delle firme olografiche (PNG trasparenti) e utilità per ricavarle da immagini.
from __future__ import annotations

import os
import time

from PySide6.QtCore import QBuffer, QIODevice, QStandardPaths, Qt
from PySide6.QtGui import QImage


def data_dir() -> str:
    from . import paths
    return paths.data_dir("firme")


def list_signatures() -> list[str]:
    d = data_dir()
    return sorted((os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".png")),
                  key=os.path.getmtime, reverse=True)


def add_signature(img: QImage) -> str:
    path = os.path.join(data_dir(), f"firma-{int(time.time() * 1000)}.png")
    img.save(path, "PNG")
    return path


def delete_signature(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def crop_to_content(img: QImage, margin: int = 6) -> QImage:
    """Ritaglia la zona non trasparente di un'immagine ARGB."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    data = bytes(ptr)
    stride = img.bytesPerLine()
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = data[y * stride + 3: y * stride + w * 4: 4]
        if any(row):
            nz = [i for i, a in enumerate(row) if a]
            x0, x1 = min(x0, nz[0]), max(x1, nz[-1])
            y0, y1 = min(y0, y), max(y1, y)
    if x1 < 0:
        return img
    x0, y0 = max(x0 - margin, 0), max(y0 - margin, 0)
    x1, y1 = min(x1 + margin, w - 1), min(y1 + margin, h - 1)
    return img.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def remove_background(img: QImage, level: int = 200, max_width: int = 900) -> QImage:
    """Rende trasparente lo sfondo chiaro (foto/scansione di una firma su carta bianca)."""
    if img.width() > max_width:
        img = img.scaledToWidth(max_width, Qt.SmoothTransformation)
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h, stride = img.width(), img.height(), img.bytesPerLine()
    buf = bytearray(bytes(img.constBits()))
    span = max(level - 60, 1)
    for y in range(h):
        base = y * stride
        for x in range(w):
            i = base + x * 4
            lum = min(buf[i], buf[i + 1], buf[i + 2])        # B, G, R in memoria (little endian)
            if lum >= level:
                buf[i + 3] = 0
            else:
                a = 255 if lum <= 60 else int((level - lum) * 255 / span)
                buf[i + 3] = a
                # colore d'inchiostro: scurisce per mantenere il contrasto
                buf[i] = buf[i] * 3 // 4; buf[i + 1] = buf[i + 1] * 3 // 4; buf[i + 2] = buf[i + 2] * 3 // 4
    out = QImage(bytes(buf), w, h, stride, QImage.Format_ARGB32).copy()
    return crop_to_content(out)


def limit_size(img: QImage, longest: int = 2400) -> QImage:
    if max(img.width(), img.height()) > longest:
        return img.scaled(longest, longest, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return img
