from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin = size * 0.07
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#13231E"))
    painter.drawRoundedRect(
        QRectF(margin, margin, size - margin * 2, size - margin * 2),
        size * 0.21,
        size * 0.21,
    )

    body = QRectF(size * 0.18, size * 0.29, size * 0.58, size * 0.43)
    painter.setPen(QPen(QColor("#EAF7F1"), max(1.5, size * 0.045)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(body, size * 0.07, size * 0.07)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#EAF7F1"))
    painter.drawRoundedRect(
        QRectF(size * 0.78, size * 0.40, size * 0.08, size * 0.21),
        size * 0.025,
        size * 0.025,
    )
    painter.setBrush(QColor("#32C87A"))
    painter.drawRoundedRect(
        QRectF(size * 0.23, size * 0.35, size * 0.43, size * 0.31),
        size * 0.045,
        size * 0.045,
    )

    bolt = QPainterPath()
    bolt.moveTo(size * 0.54, size * 0.20)
    bolt.lineTo(size * 0.39, size * 0.49)
    bolt.lineTo(size * 0.51, size * 0.49)
    bolt.lineTo(size * 0.43, size * 0.79)
    bolt.lineTo(size * 0.66, size * 0.43)
    bolt.lineTo(size * 0.54, size * 0.43)
    bolt.closeSubpath()
    painter.setBrush(QColor("#FFD166"))
    painter.drawPath(bolt)
    painter.end()
    return image


def create_battery_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(_draw_icon(size)))
    return icon


def _png_bytes(size: int) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not _draw_icon(size).save(buffer, "PNG"):
        raise RuntimeError(f"無法產生 {size}px 圖示")
    return bytes(data)


def write_ico(path: Path) -> None:
    entries = [(size, _png_bytes(size)) for size in ICON_SIZES]
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = bytearray()
    payload = bytearray()
    for size, png in entries:
        dimension = 0 if size == 256 else size
        directory.extend(
            struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset)
        )
        payload.extend(png)
        offset += len(png)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + directory + payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Battery Usage Widget icon")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    write_ico(args.output)
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
