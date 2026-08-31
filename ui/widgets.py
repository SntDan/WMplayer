"""Custom Qt widgets."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QPointF,
    QRectF,
    QSize,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)

try:
    from PyQt6.QtSvg import QSvgRenderer

    _HAS_QTSVG = True
except ImportError:  # pragma: no cover
    QSvgRenderer = None  # type: ignore[assignment]
    _HAS_QTSVG = False
from PyQt6.QtWidgets import QLabel, QPushButton, QSizePolicy, QWidget

from .theme import Theme

LUCIDE_STROKE: dict[str, str] = {
    "library": (
        "M12 7v14 "
        "M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"
    ),
    "shuffle": (
        "M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22 "
        "M18 2l4 4-4 4 "
        "M2 6h1.9c1.5 0 2.9.9 3.6 2.2 "
        "M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8 "
        "M18 14l4 4-4 4"
    ),
    "repeat": (
        "M17 2 L21 6 L17 10 "
        "M21 6 L7 6 A4 4 0 0 0 3 10 L3 11 "
        "M7 22 L3 18 L7 14 "
        "M3 18 L17 18 A4 4 0 0 0 21 14 L21 13"
    ),
    "repeat_one": (
        "M17 2 L21 6 L17 10 "
        "M21 6 L7 6 A4 4 0 0 0 3 10 L3 11 "
        "M7 22 L3 18 L7 14 "
        "M3 18 L17 18 A4 4 0 0 0 21 14 L21 13 "
        "M11 9 L13 9 L13 15 "
        "M11.5 15 L14.5 15"
    ),
    "back": ("M9 14 4 9l5-5 M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5 5.5 5.5 0 0 1-5.5 5.5H11"),
    "folder": (
        "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
    ),
    "settings": (
        "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z "
        "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
    ),
}

LUCIDE_FILL: dict[str, str] = {
    "play": "M8 5v14l11-7z",
    "pause": "M6 5h4v14H6zM14 5h4v14h-4z",
    "prev": ("M5 5 L5 19 L7 19 L7 5 Z M19 5 L19 19 L8 12 Z"),
    "next": ("M5 5 L5 19 L16 12 Z M17 5 L17 19 L19 19 L19 5 Z"),
}


def _draw_lucide_stroke(
    painter: QPainter,
    rect: QRectF,
    path_data: str,
    color: QColor,
    stroke_ratio: float = 2.0 / 24.0,
) -> None:
    """Draw a Lucide stroke icon."""
    if not _HAS_QTSVG:
        return
    side = min(rect.width(), rect.height())
    if side <= 0:
        return

    painter.save()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color.name()}" '
        f'stroke-width="{stroke_ratio * 24:.2f}" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{path_data}"/>'
        "</svg>"
    )
    renderer = QSvgRenderer(svg.encode("utf-8"))
    target = QRectF(
        rect.center().x() - side / 2,
        rect.center().y() - side / 2,
        side,
        side,
    )
    renderer.render(painter, target)
    painter.restore()


def _draw_lucide_fill(
    painter: QPainter,
    rect: QRectF,
    path_data: str,
    color: QColor,
) -> None:
    """Draw a filled transport icon."""
    if not _HAS_QTSVG:
        return
    side = min(rect.width(), rect.height())
    if side <= 0:
        return
    painter.save()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{color.name()}" stroke="none">'
        f'<path d="{path_data}"/>'
        "</svg>"
    )
    renderer = QSvgRenderer(svg.encode("utf-8"))
    target = QRectF(
        rect.center().x() - side / 2,
        rect.center().y() - side / 2,
        side,
        side,
    )
    renderer.render(painter, target)
    painter.restore()


class IconButton(QPushButton):
    def __init__(
        self,
        icon_name: str,
        size: int = 36,
        color: QColor = Theme.TEXT,
        active: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._color = color
        self._hover_color = QColor("#FFFFFF")
        self._disabled_color = QColor("#555555")
        self._active = active
        self._enabled_visual = True
        self._size = size
        self._icon_y_offset = 0
        self.setFixedSize(QSize(size, size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon(self, icon_name: str) -> None:
        self._icon_name = icon_name
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def is_active(self) -> bool:
        return self._active

    def set_enabled_visual(self, enabled: bool) -> None:
        """Change visual availability without disabling clicks."""
        if self._enabled_visual != enabled:
            self._enabled_visual = enabled
            self.update()

    def set_icon_y_offset(self, offset: int) -> None:
        """Move icon drawing without changing layout."""
        if self._icon_y_offset != offset:
            self._icon_y_offset = offset
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        if self._active and self._enabled_visual:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 28))
            p.drawEllipse(rect.adjusted(2, 2, -2, -2))
        if not self._enabled_visual:
            col = self._disabled_color
        elif self.underMouse():
            col = self._hover_color
        else:
            col = self._color
        inset = max(2.0, self.width() * 0.10)
        icon_rect = rect.adjusted(inset, inset, -inset, -inset)
        if self._icon_y_offset:
            icon_rect.translate(0, self._icon_y_offset)
        path = LUCIDE_STROKE.get(self._icon_name)
        if path:
            _draw_lucide_stroke(p, icon_rect, path, col, stroke_ratio=2.2 / 24.0)
        p.end()


class CircleButton(QPushButton):
    def __init__(
        self,
        icon_name: str,
        size: int = 64,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._size = size
        self.setFixedSize(QSize(size, size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon(self, icon_name: str) -> None:
        self._icon_name = icon_name
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        col = QColor("#CCCCCC") if self.underMouse() else Theme.TEXT
        pen = QPen(col)
        pen.setWidthF(max(1.6, self.width() * 0.030))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)
        icon_side = self.width() * 0.42
        icon_rect = QRectF(
            rect.center().x() - icon_side / 2,
            rect.center().y() - icon_side / 2,
            icon_side,
            icon_side,
        )
        path = LUCIDE_FILL.get(self._icon_name)
        if path:
            _draw_lucide_fill(p, icon_rect, path, col)
        p.end()


class AlbumCover(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self.setMinimumSize(180, 180)
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

    def set_cover(self, data: Optional[bytes]) -> None:
        if data:
            img = QImage()
            if img.loadFromData(data):
                self._pixmap = QPixmap.fromImage(img)
                self.update()
                return
        self._pixmap = None
        self.update()

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return w

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        base_side = min(rect.width(), rect.height())
        side = int(base_side * 0.97)
        x = (rect.width() - side) // 2
        y = x if rect.height() >= rect.width() else (rect.height() - side) // 2
        target = QRectF(x, y, side, side)
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                int(side),
                int(side),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            sx = x + (side - scaled.width()) // 2
            sy = y + (side - scaled.height()) // 2
            p.drawPixmap(sx, sy, scaled)
        else:
            p.fillRect(target, QColor("#000000"))
        p.end()


class ProgressBar(QWidget):
    """Draggable progress bar."""

    seek_requested = pyqtSignal(int)  # Target position in milliseconds.

    _DOT_R = 5  # Thumb radius.
    _PAD = 7  # Padding prevents clipped antialiasing.

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._position = 0
        self._duration = 0
        self._dragging = False
        self.setFixedHeight(self._DOT_R * 2 + 2)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_position(self, ms: int) -> None:
        if not self._dragging:
            self._position = max(0, min(ms, self._duration))
            self.update()

    def set_duration(self, ms: int) -> None:
        self._duration = max(0, ms)
        self.update()

    def _bar_range(self) -> tuple[int, int]:
        """Return the visible progress bar range."""
        return self._PAD, max(self._PAD, self.width() - self._PAD)

    def _ms_at(self, x: int) -> int:
        if self._duration <= 0:
            return 0
        left, right = self._bar_range()
        bar_w = right - left
        if bar_w <= 0:
            return 0
        ratio = max(0.0, min(1.0, (x - left) / bar_w))
        return int(ratio * self._duration)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self._duration > 0:
            self._dragging = True
            self._position = self._ms_at(int(e.position().x()))
            self.update()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._dragging:
            self._position = self._ms_at(int(e.position().x()))
            self.update()

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._dragging and e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.seek_requested.emit(self._position)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        h = 4
        y = (self.height() - h) // 2
        left, right = self._bar_range()
        bar_w = right - left

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(Theme.PROGRESS_BG))
        p.drawRoundedRect(QRectF(left, y, bar_w, h), 2, 2)

        if self._duration > 0 and bar_w > 0:
            ratio = max(0.0, min(1.0, self._position / self._duration))
            played_w = bar_w * ratio
            p.setBrush(QBrush(Theme.PROGRESS_FG))
            p.drawRoundedRect(QRectF(left, y, played_w, h), 2, 2)

            cx = left + played_w
            cy = self.height() / 2
            p.drawEllipse(QPointF(cx, cy), self._DOT_R, self._DOT_R)

        p.end()


class ScrollingLabel(QLabel):
    """Label with external marquee control."""

    double_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._offset = 0
        self._direction = 1
        self._pause_ticks = 0
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sp = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setSizePolicy(sp)

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(0, fm.height() + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self._offset = 0
        self._direction = 1
        self._pause_ticks = 0
        self.update()

    def needs_scroll(self) -> bool:
        """Return whether the text overflows."""
        return self.scroll_limit() > 0

    def scroll_limit(self) -> int:
        text_w = self.fontMetrics().horizontalAdvance(self.text())
        return max(0, text_w - self.width() + 20)

    def set_scroll_offset(self, offset: int) -> None:
        new_offset = max(0, min(int(offset), self.scroll_limit()))
        if self._offset != new_offset:
            self._offset = new_offset
            self.update()

    def reset_scroll(self) -> None:
        self._offset = 0
        self._direction = 1
        self._pause_ticks = 0
        self.update()

    def tick(self) -> None:
        """Advance one marquee frame."""
        if not self.needs_scroll() or not self.isVisible():
            return
        if self._pause_ticks > 0:
            self._pause_ticks -= 1
            return

        self._offset += self._direction
        max_off = self.scroll_limit()
        if max_off <= 0:
            self._offset = 0
            self._direction = 1
            self._pause_ticks = 8
        elif self._offset >= max_off:
            self._offset = max_off
            self._direction = -1
            self._pause_ticks = 8
        elif self._offset <= 0:
            self._offset = 0
            self._direction = 1
            self._pause_ticks = 8
        self.update()

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        super().mouseDoubleClickEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def paintEvent(self, e) -> None:  # noqa: N802
        fm = self.fontMetrics()
        if fm.horizontalAdvance(self.text()) <= self.width():
            super().paintEvent(e)
            return
        p = QPainter(self)
        p.setPen(self.palette().color(self.foregroundRole()))
        p.setFont(self.font())
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        p.drawText(-self._offset, y, self.text())
        p.end()


class HRBadge(QWidget):
    """High-resolution audio badge."""

    GOLD = QColor("#D4AF37")

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._visible = False
        self.setFixedSize(QSize(32, 18))

    def set_visible_hr(self, visible: bool) -> None:
        if self._visible != visible:
            self._visible = visible
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        if not self._visible:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        bw, bh = 26.0, 16.0
        cx, cy = self.width() / 2, self.height() / 2
        rect = QRectF(cx - bw / 2, cy - bh / 2, bw, bh)
        pen = QPen(self.GOLD)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 3, 3)
        f = QFont()
        f.setPointSize(9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(self.GOLD)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "HR")
        p.end()
