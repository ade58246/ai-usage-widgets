from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin = size * 0.08
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#172033"))
    painter.drawRoundedRect(
        QRectF(margin, margin, size - margin * 2, size - margin * 2), size * 0.22, size * 0.22
    )

    gauge_rect = QRectF(size * 0.2, size * 0.22, size * 0.6, size * 0.6)
    pen = QPen(
        QColor("#6B778C"), max(2.0, size * 0.075), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap
    )
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(gauge_rect, 210 * 16, -240 * 16)

    pen.setColor(QColor("#69A9FF"))
    painter.setPen(pen)
    painter.drawArc(gauge_rect, 210 * 16, -150 * 16)

    painter.setPen(
        QPen(
            QColor("#F8FAFC"),
            max(1.5, size * 0.045),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    center = size * 0.5
    painter.drawLine(int(center), int(center), int(size * 0.68), int(size * 0.39))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#F8FAFC"))
    painter.drawEllipse(
        QRectF(center - size * 0.055, center - size * 0.055, size * 0.11, size * 0.11)
    )
    painter.end()
    return image


def create_meter_icon() -> QIcon:
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
    parser = argparse.ArgumentParser(description="Generate the Codex Usage Widget icon")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    write_ico(args.output)
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
