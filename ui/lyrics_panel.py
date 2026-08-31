"""Lyrics display panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRect,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.lrc import Lyrics

from .i18n import tr
from .theme import Theme

LYRIC_VISUAL_LEAD_MS = 240
LYRIC_ANIMATE_MAX_LINE_JUMP = 2
LYRIC_TEXT_CLIP_PAD = 3


class _LyricsCanvas(QWidget):
    """Canvas for lyric rendering."""

    line_clicked = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lyrics: Optional[Lyrics] = None
        self._current_index: int = -1
        self._synced: bool = False
        self._scroll: float = 0.0
        self._anim = QPropertyAnimation(self, b"scroll")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._font = QFont()
        self._font.setPointSize(13)
        self._font_active = QFont()
        self._font_active.setPointSize(17)
        self._font_active.setBold(True)
        self._row_gap = 14
        self._text_margin = 24

        self._heights: list[float] = []
        self._offsets: list[float] = []
        self._total_height: float = 0.0
        self._height_cache_key: tuple = (None, -1, -1)

        self._drag_start_y: Optional[float] = None
        self._drag_start_scroll: float = 0.0

        self.setMinimumHeight(200)

    def _get_scroll(self) -> float:
        return self._scroll

    def _set_scroll(self, value: float) -> None:
        self._scroll = float(value)
        self.update()

    scroll = pyqtProperty(float, fget=_get_scroll, fset=_set_scroll)

    def set_lyrics(self, lyrics: Optional[Lyrics]) -> None:
        self._lyrics = lyrics
        self._current_index = -1
        self._scroll = 0.0
        self._height_cache_key = (None, -1, -1)
        self._heights = []
        self._offsets = []
        self._total_height = 0.0
        self._anim.stop()
        self._synced = bool(lyrics and lyrics.is_synced())
        if self._synced:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._lyrics and len(self._lyrics) > 0:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def set_current_index(self, index: int, animate: bool = True) -> None:
        if not self._synced:
            return
        if index == self._current_index:
            return
        old_index = self._current_index
        self._current_index = index
        if self._lyrics and 0 <= index < len(self._lyrics):
            target = self._block_top(index) + self._block_height(index) / 2
        else:
            target = 0.0
        if (
            animate
            and old_index >= 0
            and abs(index - old_index) <= LYRIC_ANIMATE_MAX_LINE_JUMP
        ):
            self._anim.stop()
            self._anim.setStartValue(self._scroll)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_scroll(target)
        self.update()

    def _font_for(self, index: int) -> QFont:
        return (
            self._font_active
            if (self._synced and index == self._current_index)
            else self._font
        )

    def _ensure_heights(self) -> None:
        """Refresh cached lyric layout when inputs change."""
        key = (
            id(self._lyrics) if self._lyrics else None,
            self._current_index,
            self.width(),
        )
        if key == self._height_cache_key:
            return
        self._height_cache_key = key
        self._heights = []
        self._offsets = []
        if self._lyrics is None:
            self._total_height = 0.0
            return

        max_w = max(50, self.width() - 2 * self._text_margin)
        flags = int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignHCenter)
        fm_normal = QFontMetrics(self._font)
        fm_active = QFontMetrics(self._font_active)

        acc = 0.0
        for i, line in enumerate(self._lyrics.lines):
            self._offsets.append(acc)
            text = line.text
            if not text:
                self._heights.append(0.0)
                continue
            fm = fm_active if (self._synced and i == self._current_index) else fm_normal
            rect = fm.boundingRect(QRect(0, 0, int(max_w), 10000), flags, text)
            h = float(rect.height() + self._row_gap)
            self._heights.append(h)
            acc += h
        self._total_height = acc

    def _block_height(self, index: int) -> float:
        self._ensure_heights()
        if 0 <= index < len(self._heights):
            return self._heights[index]
        return 0.0

    def _block_top(self, index: int) -> float:
        self._ensure_heights()
        if 0 <= index < len(self._offsets):
            return self._offsets[index]
        return 0.0

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = self.width()
        h = self.height()
        center_y = h / 2

        if self._lyrics is None or len(self._lyrics) == 0:
            p.setPen(Theme.TEXT_DIM)
            p.setFont(self._font)
            msg = tr("lyrics_missing_help")
            rect = self.rect().adjusted(self._text_margin, 0, -self._text_margin, 0)
            flags = int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignCenter)
            p.drawText(rect, flags, msg)
            p.end()
            return

        if self._synced:
            origin_y = center_y
        else:
            origin_y = 30.0

        max_w = max(50, w - 2 * self._text_margin)
        flags = int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignHCenter)

        y_top = origin_y - self._scroll
        for i, line in enumerate(self._lyrics.lines):
            block_h = self._block_height(i)
            text = line.text
            if not text:
                y_top += block_h
                continue

            if y_top + block_h < 0:
                y_top += block_h
                continue
            if y_top > h:
                break

            is_current = self._synced and (i == self._current_index)
            if is_current:
                p.setFont(self._font_active)
                p.setPen(QColor("#FFFFFF"))
            else:
                p.setFont(self._font)
                if self._synced and self._current_index >= 0:
                    distance = abs(i - self._current_index)
                    alpha = max(60, 200 - distance * 35)
                else:
                    alpha = 200
                p.setPen(QColor(255, 255, 255, alpha))

            text_h = block_h - self._row_gap
            rect = QRect(
                self._text_margin,
                int(y_top + self._row_gap / 2 - LYRIC_TEXT_CLIP_PAD),
                int(max_w),
                int(text_h + LYRIC_TEXT_CLIP_PAD * 2),
            )
            p.drawText(rect, flags, text)

            y_top += block_h
        p.end()

    def mousePressEvent(self, e):  # noqa: N802
        if self._lyrics is None:
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._synced:
            return
        self._drag_start_y = e.position().y()
        self._drag_start_scroll = self._scroll
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag_start_y is not None:
            dy = e.position().y() - self._drag_start_y
            self._set_scroll(self._drag_start_scroll - dy)
            self._clamp_scroll()

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._lyrics is None:
            return
        if self._drag_start_y is not None:
            moved = abs(e.position().y() - self._drag_start_y) > 4
            self._drag_start_y = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if moved:
                return
            return
        if self._synced:
            origin_y = self.height() / 2
            clicked_y = e.position().y() - origin_y + self._scroll
            y_acc = 0.0
            for i in range(len(self._lyrics)):
                bh = self._block_height(i)
                if y_acc <= clicked_y < y_acc + bh:
                    self.line_clicked.emit(i)
                    return
                y_acc += bh

    def wheelEvent(self, e):  # noqa: N802
        if self._synced or self._lyrics is None:
            super().wheelEvent(e)
            return
        delta = e.angleDelta().y()
        self._set_scroll(self._scroll - delta * 0.5)
        self._clamp_scroll()
        e.accept()

    def _clamp_scroll(self) -> None:
        if self._lyrics is None or len(self._lyrics) == 0:
            self._scroll = 0.0
            return
        self._ensure_heights()
        max_scroll = max(0.0, self._total_height - self.height() + 60)
        if self._scroll < 0:
            self._scroll = 0.0
        elif self._scroll > max_scroll:
            self._scroll = max_scroll
        self.update()


class LyricsPanel(QWidget):
    """Lyrics panel."""

    seek_to_ms = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lyrics: Optional[Lyrics] = None
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel(tr("lyrics"))
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        self.title_label.setFont(f)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #9E9E9E;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.info_label)
        outer.addLayout(header)

        self.canvas = _LyricsCanvas()
        self.canvas.line_clicked.connect(self._on_line_clicked)
        outer.addWidget(self.canvas, 1)

    def set_lyrics(self, lyrics: Optional[Lyrics], track_label: str = "") -> None:
        self._lyrics = lyrics
        self._track_label = track_label
        self.canvas.set_lyrics(lyrics)
        if lyrics is None or len(lyrics) == 0:
            self.info_label.setText(tr("no_lrc"))
        elif lyrics.is_synced():
            self.info_label.setText(f"{track_label}")
        else:
            self.info_label.setText(f"{track_label} - {tr('plain_text')}")

    def update_position(self, position_ms: int) -> None:
        if self._lyrics is None or len(self._lyrics) == 0:
            return
        if not self._lyrics.is_synced():
            return
        idx = self._lyrics.index_at(position_ms + LYRIC_VISUAL_LEAD_MS)
        self.canvas.set_current_index(idx)

    def has_lyrics(self) -> bool:
        return self._lyrics is not None and len(self._lyrics) > 0

    def _on_line_clicked(self, idx: int) -> None:
        if self._lyrics and 0 <= idx < len(self._lyrics):
            line = self._lyrics.lines[idx]
            self.seek_to_ms.emit(
                max(0, line.time_ms + self._lyrics.offset_ms - LYRIC_VISUAL_LEAD_MS)
            )

    def retranslate(self) -> None:
        self.title_label.setText(tr("lyrics"))
        self.set_lyrics(self._lyrics, getattr(self, "_track_label", ""))
