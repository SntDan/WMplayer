"""Shared high-resolution badge geometry and painting."""

from functools import lru_cache

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QTransform,
)


HR_BADGE_WIDTH = 24
HR_BADGE_HEIGHT = 18
HR_BADGE_GOLD = QColor("#D4AF37")


@lru_cache(maxsize=1)
def _letter_path() -> QPainterPath:
    font = QFont("Bahnschrift")
    font.setPixelSize(100)
    font.setBold(True)
    path = QPainterPath()
    path.addText(0, 0, font, "HR")
    # Bahnschrift's R has overlapping stem/bowl contours. Merge them before
    # antialiasing so their shared top edge does not leave a raised seam.
    path = path.simplified()
    bounds = path.boundingRect()
    transform = QTransform()
    transform.scale(16.4 / bounds.width(), 11.2 / bounds.height())
    transform.translate(-bounds.x(), -bounds.y())
    path = transform.map(path)
    # Thicken in badge coordinates for equal horizontal and vertical weight.
    stroker = QPainterPathStroker()
    stroker.setWidth(0.38)
    stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return path.united(stroker.createStroke(path)).simplified()


def paint_hr_badge(painter: QPainter, rect: QRectF) -> None:
    """Paint the compact B badge with its 0.65 px optical centering offset."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    pen = QPen(HR_BADGE_GOLD)
    pen.setWidthF(1.4)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, 2.7, 2.7)

    path = _letter_path()
    bounds = path.boundingRect()
    painter.translate(
        rect.center().x() - bounds.center().x() + 0.65,
        rect.center().y() - bounds.center().y(),
    )
    painter.fillPath(path, HR_BADGE_GOLD)
    painter.restore()
