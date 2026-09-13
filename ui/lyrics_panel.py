"""Lyrics display panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

from core.lrc import Lyrics

from .i18n import tr
from .theme import Theme

LYRIC_VISUAL_LEAD_MS = 240
LYRIC_ANIMATE_MAX_LINE_JUMP = 2
LYRIC_TEXT_CLIP_PAD = 3
LYRIC_SCROLL_DURATION_MS = 300
LYRIC_LIGHT_DURATION_MS = 180
LYRIC_INTRO_FADE_MS = 180
LYRIC_VERTICAL_MARGIN = 10
LYRIC_SCROLLBAR_HIDE_MS = 1000
LYRIC_FOLLOW_RESUME_MS = 5000


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
        self._anim.setDuration(LYRIC_SCROLL_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._spotlight_index = -1
        self._light_weights: dict[int, float] = {}
        self._light_start: dict[int, float] = {}
        self._light_progress = 1.0
        self._light_anim = QPropertyAnimation(self, b"light_progress")
        self._light_anim.setEasingCurve(QEasingCurve.Type.InOutQuint)
        self._font = QFont()
        self._font.setPointSize(17)
        self._font.setBold(True)
        self._row_gap = 16
        self._text_margin = 24

        self._heights: list[float] = []
        self._offsets: list[float] = []
        self._total_height: float = 0.0
        self._height_cache_key: tuple = (None, -1, -1)

        self._drag_start_y: Optional[float] = None
        self._drag_start_scroll: float = 0.0

        self._manual_scroll = False
        self._scrollbar = QScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar.setStyleSheet("""
            QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 100); min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        self._scrollbar.hide()
        self._scrollbar.installEventFilter(self)
        self._scrollbar.valueChanged.connect(self._scrollbar_moved)
        self._scrollbar.sliderPressed.connect(self._begin_manual_scroll)
        self._scrollbar.sliderReleased.connect(self._begin_manual_scroll)
        self._scrollbar_hide_timer = QTimer(self)
        self._scrollbar_hide_timer.setSingleShot(True)
        self._scrollbar_hide_timer.setInterval(LYRIC_SCROLLBAR_HIDE_MS)
        self._scrollbar_hide_timer.timeout.connect(self._scrollbar.hide)
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.setInterval(LYRIC_FOLLOW_RESUME_MS)
        self._follow_timer.timeout.connect(self._resume_follow)

        self.setMinimumHeight(200)

    def _get_scroll(self) -> float:
        return self._scroll

    def _set_scroll(self, value: float) -> None:
        self._scroll = float(value)
        self._sync_scrollbar()
        self.update()

    scroll = pyqtProperty(float, fget=_get_scroll, fset=_set_scroll)

    def _sync_scrollbar(self) -> None:
        self._scrollbar.blockSignals(True)
        self._scrollbar.setRange(0, round(self._max_scroll()))
        self._scrollbar.setPageStep(self.height())
        self._scrollbar.setValue(round(self._scroll))
        self._scrollbar.blockSignals(False)
        if self._scrollbar.maximum() == 0:
            self._scrollbar.hide()

    def _begin_manual_scroll(self) -> None:
        self._anim.stop()
        self._manual_scroll = True
        self._sync_scrollbar()
        self._scrollbar.setVisible(self._scrollbar.maximum() > 0)
        if self._scrollbar.isSliderDown():
            self._scrollbar_hide_timer.stop()
            self._follow_timer.stop()
        else:
            self._scrollbar_hide_timer.start()
            if self._synced:
                self._follow_timer.start()

    def _scrollbar_moved(self, value: int) -> None:
        self._set_scroll(float(value))
        self._begin_manual_scroll()

    def _resume_follow(self) -> None:
        self._manual_scroll = False
        self._follow_timer.stop()
        if self._synced:
            self._anim.stop()
            self._anim.setStartValue(self._scroll)
            self._anim.setEndValue(self._target_scroll())
            self._anim.start()

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self._scrollbar and event.type() == QEvent.Type.Wheel:
            self.wheelEvent(event)
            return event.isAccepted()
        return super().eventFilter(watched, event)

    def _get_light_progress(self) -> float:
        return self._light_progress

    def _set_light_progress(self, value: float) -> None:
        self._light_progress = float(value)
        self._light_weights = {
            index: weight * (1.0 - value)
            for index, weight in self._light_start.items()
            if weight * (1.0 - value) > 0.0001
        }
        if self._spotlight_index >= 0:
            index = self._spotlight_index
            self._light_weights[index] = self._light_weights.get(index, 0.0) + value
        self.update()

    light_progress = pyqtProperty(
        float, fget=_get_light_progress, fset=_set_light_progress
    )

    def _set_spotlight(
        self, index: int, animate: bool = True,
        duration: int = LYRIC_LIGHT_DURATION_MS,
    ) -> None:
        if index == self._spotlight_index and animate:
            return
        self._light_anim.stop()
        # Retarget from the displayed light, even if the last fade is unfinished.
        self._light_start = self._light_weights.copy()
        self._spotlight_index = index
        if animate:
            self._light_anim.setDuration(max(1, duration))
            self._light_anim.setStartValue(0.0)
            self._light_anim.setEndValue(1.0)
            self._light_anim.start()
        else:
            self._set_light_progress(1.0)

    def set_lyrics(self, lyrics: Optional[Lyrics]) -> None:
        self._follow_timer.stop()
        self._scrollbar_hide_timer.stop()
        self._scrollbar.hide()
        self._manual_scroll = False
        self._drag_start_y = None
        self._lyrics = lyrics
        self._current_index = -1
        self._scroll = 0.0
        self._height_cache_key = (None, -1, -1)
        self._heights = []
        self._offsets = []
        self._total_height = 0.0
        self._anim.stop()
        self._set_spotlight(-1, animate=False)
        self._synced = bool(lyrics and lyrics.is_synced())
        self._sync_scrollbar()
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
        self._set_spotlight(
            index,
            animate=animate and abs(index - old_index) <= LYRIC_ANIMATE_MAX_LINE_JUMP,
        )
        if self._manual_scroll:
            return
        target = self._target_scroll()
        # A seek must also cancel any unfinished animation to the previous line.
        self._anim.stop()
        if (
            animate
            and old_index >= 0
            and abs(index - old_index) <= LYRIC_ANIMATE_MAX_LINE_JUMP
            and abs(target - self._scroll) > 0.5
        ):
            self._anim.setStartValue(self._scroll)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_scroll(target)
        self.update()

    def _max_scroll(self) -> float:
        self._ensure_heights()
        return max(0.0, self._total_height + 2 * LYRIC_VERTICAL_MARGIN - self.height())

    def _target_scroll(self) -> float:
        """Start at the top; follow the active row only after it reaches mid-view."""
        if not self._lyrics or not 0 <= self._current_index < len(self._lyrics):
            return 0.0
        target = (
            LYRIC_VERTICAL_MARGIN
            + self._block_top(self._current_index)
            + self._block_height(self._current_index) / 2
            - self.height() / 2
        )
        return max(0.0, min(target, self._max_scroll()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._scrollbar.setGeometry(self.width() - 12, 4, 8, max(0, self.height() - 8))
        self._anim.stop()
        if self._synced and not self._manual_scroll:
            self._set_scroll(self._target_scroll())
        else:
            self._clamp_scroll()

    def _alpha_for(self, index: int) -> int:
        if not self._synced:
            return 200
        alpha = 60.0
        for active, weight in self._light_weights.items():
            distance = abs(index - active)
            target = 255 if distance == 0 else (110 if distance == 1 else 60)
            alpha += (target - 60) * weight
        return round(alpha)

    def _ensure_heights(self) -> None:
        """Refresh cached lyric layout when inputs change."""
        key = (
            id(self._lyrics) if self._lyrics else None,
            self._synced,
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

        acc = 0.0
        for line in self._lyrics.lines:
            self._offsets.append(acc)
            text = line.text
            if not text:
                self._heights.append(0.0)
                continue
            bounds = QRect(0, 0, int(max_w), 10000)
            text_h = fm_normal.boundingRect(bounds, flags, text).height()
            h = float(text_h + self._row_gap)
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

        if self._lyrics is None or len(self._lyrics) == 0:
            p.setPen(Theme.TEXT_DIM)
            p.setFont(self._font)
            msg = tr("lyrics_missing_help")
            rect = self.rect().adjusted(self._text_margin, 0, -self._text_margin, 0)
            flags = int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignCenter)
            p.drawText(rect, flags, msg)
            p.end()
            return

        max_w = max(50, w - 2 * self._text_margin)
        flags = (
            int(Qt.TextFlag.TextWordWrap)
            | int(Qt.AlignmentFlag.AlignHCenter)
            | int(Qt.AlignmentFlag.AlignVCenter)
        )

        y_top = LYRIC_VERTICAL_MARGIN - self._scroll
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

            p.setFont(self._font)
            p.setPen(QColor(255, 255, 255, self._alpha_for(i)))

            text_h = block_h - self._row_gap
            rect = QRectF(
                self._text_margin,
                y_top + self._row_gap / 2 - LYRIC_TEXT_CLIP_PAD,
                max_w,
                text_h + LYRIC_TEXT_CLIP_PAD * 2,
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
            if self._manual_scroll:
                self._follow_timer.start()
            return
        self._drag_start_y = e.position().y()
        self._drag_start_scroll = self._scroll
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._drag_start_y is not None:
            dy = e.position().y() - self._drag_start_y
            self._set_scroll(self._drag_start_scroll - dy)
            self._clamp_scroll()
            self._begin_manual_scroll()

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
            if self._manual_scroll:
                self._follow_timer.start()
            clicked_y = e.position().y() - LYRIC_VERTICAL_MARGIN + self._scroll
            y_acc = 0.0
            for i in range(len(self._lyrics)):
                bh = self._block_height(i)
                if y_acc <= clicked_y < y_acc + bh:
                    self.line_clicked.emit(i)
                    return
                y_acc += bh

    def wheelEvent(self, e):  # noqa: N802
        if not self._lyrics:
            super().wheelEvent(e)
            return
        delta = e.pixelDelta().y() or e.angleDelta().y() * 0.5
        if delta:
            self._begin_manual_scroll()
            self._set_scroll(max(0.0, min(self._scroll - delta, self._max_scroll())))
        e.accept()

    def _clamp_scroll(self) -> None:
        if self._lyrics is None or len(self._lyrics) == 0:
            self._scroll = 0.0
            return
        max_scroll = self._max_scroll()
        if self._scroll < 0:
            self._scroll = 0.0
        elif self._scroll > max_scroll:
            self._scroll = max_scroll
        self._sync_scrollbar()
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
        if idx < 0:
            until_first = (
                self._lyrics.lines[0].time_ms + self._lyrics.offset_ms
                - position_ms - LYRIC_VISUAL_LEAD_MS
            )
            if until_first <= LYRIC_INTRO_FADE_MS:
                self.canvas._set_spotlight(0, duration=until_first)
            else:
                self.canvas._set_spotlight(-1, animate=False)

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
