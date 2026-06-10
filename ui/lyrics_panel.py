"""
歌词视图
========
两种模式:
- 同步歌词(LRC 带时间戳): 自动滚动到当前行,高亮当前行,点击跳转
- 纯文本歌词或无时间戳:    手动滚动(滚轮 / 拖动),不高亮、不跳转
"""

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
from .theme import Theme


LYRIC_VISUAL_LEAD_MS = 240
LYRIC_TEXT_CLIP_PAD = 3


class _LyricsCanvas(QWidget):
    """实际绘制歌词的画布。"""

    line_clicked = pyqtSignal(int)  # 仅同步歌词:用户点击某行 -> 跳转

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lyrics: Optional[Lyrics] = None
        self._current_index: int = -1
        self._synced: bool = False
        # 滚动偏移(像素)。同步模式由动画控制,手动模式由用户操作控制
        self._scroll: float = 0.0
        # 缓动动画(只在同步模式用)
        self._anim = QPropertyAnimation(self, b"scroll")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # 字号
        self._font = QFont()
        self._font.setPointSize(13)
        self._font_active = QFont()
        self._font_active.setPointSize(17)
        self._font_active.setBold(True)
        # 每个逻辑行之间的额外间距(单行情况下基础间距,多行情况下行间额外加这么多)
        self._row_gap = 14
        # 文字两侧内边距(避免顶到面板边缘)
        self._text_margin = 24

        # 高度缓存:_block_height/_block_top 是 hot path,200+ 行歌词逐帧计算
        # 累加是 O(n²),用累计偏移表把 _block_top 降到 O(1)。
        # _heights[i] = 第 i 行的高度;_offsets[i] = 第 0..i-1 行高度的累计和。
        # _height_cache_key 记录 (lyrics 引用, 当前行 idx, 画布宽度) 三元组,
        # 任一项变化时整张表重建。
        self._heights: list[float] = []
        self._offsets: list[float] = []
        self._total_height: float = 0.0
        self._height_cache_key: tuple = (None, -1, -1)

        # 拖动状态
        self._drag_start_y: Optional[float] = None
        self._drag_start_scroll: float = 0.0

        self.setMinimumHeight(200)

    # ------------------------------------------------------------------
    # Qt property: scroll  (用于动画)
    # ------------------------------------------------------------------
    def _get_scroll(self) -> float:
        return self._scroll

    def _set_scroll(self, value: float) -> None:
        self._scroll = float(value)
        self.update()

    scroll = pyqtProperty(float, fget=_get_scroll, fset=_set_scroll)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def set_lyrics(self, lyrics: Optional[Lyrics]) -> None:
        self._lyrics = lyrics
        self._current_index = -1
        self._scroll = 0.0
        self._anim.stop()
        self._synced = bool(lyrics and lyrics.is_synced())
        # 同步模式 → 手指针,提示可点击;非同步 → 拖动手势,提示可拖
        if self._synced:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._lyrics and len(self._lyrics) > 0:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.update()

    def set_current_index(self, index: int, animate: bool = True) -> None:
        # 仅同步模式响应位置更新
        if not self._synced:
            return
        if index == self._current_index:
            return
        self._current_index = index
        if self._lyrics and 0 <= index < len(self._lyrics):
            target = self._block_top(index) + self._block_height(index) / 2
        else:
            target = 0.0
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._scroll)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_scroll(target)
        self.update()

    # ------------------------------------------------------------------
    # 几何计算 (按当前画布宽度自动换行)
    # ------------------------------------------------------------------
    def _font_for(self, index: int) -> QFont:
        return self._font_active if (self._synced and index == self._current_index) else self._font

    def _ensure_heights(self) -> None:
        """按需重建累计高度表;只在 (lyrics, current_index, width) 三者改变时执行。"""
        key = (id(self._lyrics) if self._lyrics else None, self._current_index, self.width())
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

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------
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
            msg = (
                "未找到歌词\n\n"
                "把同名 .lrc 文件放在歌曲同一目录下\n"
                "(例如 song.flac → song.lrc)"
            )
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)
            p.end()
            return

        # 同步模式:把当前行的中点定位到画布中心
        # 手动模式:从顶部 30px 处开始铺
        if self._synced:
            origin_y = center_y
        else:
            origin_y = 30.0

        max_w = max(50, w - 2 * self._text_margin)
        flags = int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignHCenter)

        # 累加 y,只绘制视区内的行
        y_top = origin_y - self._scroll
        for i, line in enumerate(self._lyrics.lines):
            block_h = self._block_height(i)
            text = line.text
            if not text:
                # 安全防线:理论上 lrc 解析时已经丢空行
                y_top += block_h
                continue

            # 视区裁剪
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

            # 把整个 block 矩形传给 drawText,自动换行 + 居中
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

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def mousePressEvent(self, e):  # noqa: N802
        if self._lyrics is None:
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._synced:
            return  # 同步模式下,不在 press 时处理 - 等 release 判断是点击还是拖动
        # 手动模式:开始拖动
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
            # 手动模式拖动结束
            moved = abs(e.position().y() - self._drag_start_y) > 4
            self._drag_start_y = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if moved:
                return
            # 否则当作普通点击;但手动模式不响应点击跳转
            return
        # 同步模式:点击跳转
        if self._synced:
            origin_y = self.height() / 2
            clicked_y = e.position().y() - origin_y + self._scroll
            # 在每个 block 的累计 y 范围内找
            y_acc = 0.0
            for i in range(len(self._lyrics)):
                bh = self._block_height(i)
                if y_acc <= clicked_y < y_acc + bh:
                    self.line_clicked.emit(i)
                    return
                y_acc += bh

    def wheelEvent(self, e):  # noqa: N802
        # 手动模式下用滚轮滚动;同步模式让事件继续传播(用户应靠音乐进度)
        if self._synced or self._lyrics is None:
            super().wheelEvent(e)
            return
        delta = e.angleDelta().y()  # 一格通常是 120
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
    """右侧歌词视图。"""

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
        title = QLabel("歌词")
        f = QFont(); f.setPointSize(15); f.setBold(True); title.setFont(f)
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #9E9E9E;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.info_label)
        outer.addLayout(header)

        self.canvas = _LyricsCanvas()
        self.canvas.line_clicked.connect(self._on_line_clicked)
        outer.addWidget(self.canvas, 1)

    def set_lyrics(self, lyrics: Optional[Lyrics], track_label: str = "") -> None:
        self._lyrics = lyrics
        self.canvas.set_lyrics(lyrics)
        if lyrics is None or len(lyrics) == 0:
            self.info_label.setText("没有同名 .lrc 文件")
        elif lyrics.is_synced():
            self.info_label.setText(f"{track_label}")
        else:
            self.info_label.setText(f"{track_label} · 纯文本")

    def update_position(self, position_ms: int) -> None:
        if self._lyrics is None or len(self._lyrics) == 0:
            return
        if not self._lyrics.is_synced():
            return  # 纯文本不跟随
        idx = self._lyrics.index_at(position_ms + LYRIC_VISUAL_LEAD_MS)
        self.canvas.set_current_index(idx)

    def has_lyrics(self) -> bool:
        return self._lyrics is not None and len(self._lyrics) > 0

    def _on_line_clicked(self, idx: int) -> None:
        if self._lyrics and 0 <= idx < len(self._lyrics):
            line = self._lyrics.lines[idx]
            self.seek_to_ms.emit(max(0, line.time_ms + self._lyrics.offset_ms - LYRIC_VISUAL_LEAD_MS))
