"""
自定义控件
==========
- IconButton:  红色图标按钮(线性图标,可切换激活状态)
- CircleButton: 白色环形按钮,用于播放/上下首
- AlbumCover:  方形封面显示
- ProgressBar: 自绘进度条(可拖动)
- ScrollingLabel: 长文本时滚动显示

图标全部以 Lucide 风格的 24x24 SVG path 描述,通过 QPainter 渲染,
保持统一的描边粗细 / 圆角端点 / 视觉重量。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    QPointF,
    QRectF,
    QSize,
    Qt,
    QTimer,
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


# ----------------------------------------------------------------------
# 图标系统
# ----------------------------------------------------------------------
# Lucide (https://lucide.dev) ISC 协议,使用 24x24 viewBox,统一 stroke-width=2
# round linecap/linejoin。我们直接把 path 数据嵌入代码,不引入外部资源。
#
# 渲染时:
#   - IconButton (红色描边) → 用 stroke 而非 fill,粗细随按钮大小自适应
#   - CircleButton 内部图标 (实心三角/竖条) → 用 fill,搭配白色圆环
#
# 所有 path 取自 lucide-static@latest,本身已经经过细致设计。

# 线条类图标 (描边): 由 IconButton 渲染
LUCIDE_STROKE: dict[str, str] = {
    # 曲库 - book-open
    "library": (
        "M12 7v14 "
        "M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"
    ),
    # 随机 - shuffle
    "shuffle": (
        "M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22 "
        "M18 2l4 4-4 4 "
        "M2 6h1.9c1.5 0 2.9.9 3.6 2.2 "
        "M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8 "
        "M18 14l4 4-4 4"
    ),
    # 列表循环 - repeat (两个箭头形成的循环框)
    "repeat": (
        "M17 2 L21 6 L17 10 "          # 右上箭头
        "M21 6 L7 6 A4 4 0 0 0 3 10 L3 11 "  # 上半线 + 左下圆角
        "M7 22 L3 18 L7 14 "           # 左下箭头
        "M3 18 L17 18 A4 4 0 0 0 21 14 L21 13"  # 下半线 + 右上圆角
    ),
    # 单曲循环 - repeat-1 (在 repeat 中间画一个 1)
    "repeat_one": (
        "M17 2 L21 6 L17 10 "
        "M21 6 L7 6 A4 4 0 0 0 3 10 L3 11 "
        "M7 22 L3 18 L7 14 "
        "M3 18 L17 18 A4 4 0 0 0 21 14 L21 13 "
        "M11 9 L13 9 L13 15 "
        "M11.5 15 L14.5 15"
    ),
    # 返回 - undo-2 (左下弯箭头)
    "back": (
        "M9 14 4 9l5-5 "
        "M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5 5.5 5.5 0 0 1-5.5 5.5H11"
    ),
    # 文件夹 - folder
    "folder": (
        "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
    ),
    # 设置 - settings (齿轮)
    "settings": (
        "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z "
        "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"
    ),
}

# 实心图标(填充): 由 CircleButton 内部使用 + 暂停 / 播放
LUCIDE_FILL: dict[str, str] = {
    # 播放 - 实心三角
    "play": "M8 5v14l11-7z",
    # 暂停 - 两条粗竖条
    "pause": "M6 5h4v14H6zM14 5h4v14h-4z",
    # 上一首 - 左竖条 + 左指三角
    "prev": (
        "M5 5 L5 19 L7 19 L7 5 Z "      # 左竖条
        "M19 5 L19 19 L8 12 Z"           # 左指三角
    ),
    # 下一首 - 右指三角 + 右竖条
    "next": (
        "M5 5 L5 19 L16 12 Z "           # 右指三角
        "M17 5 L17 19 L19 19 L19 5 Z"   # 右竖条
    ),
}


def _draw_lucide_stroke(
    painter: QPainter,
    rect: QRectF,
    path_data: str,
    color: QColor,
    stroke_ratio: float = 2.0 / 24.0,
    text_overlay: Optional[str] = None,
) -> None:
    """把 24x24 视口的 stroke path 绘制到给定矩形里。"""
    if not _HAS_QTSVG:
        return
    side = min(rect.width(), rect.height())
    if side <= 0:
        return

    painter.save()
    # 用 SVG renderer:把整个 path 包装成完整 svg,让 Qt 处理 path parsing
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color.name()}" '
        f'stroke-width="{stroke_ratio * 24:.2f}" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{path_data}"/>'
        '</svg>'
    )
    renderer = QSvgRenderer(svg.encode("utf-8"))
    # 居中 + 保持宽高比
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
    """渲染填充 path(用于播放 / 暂停 / 上下首图标里的实心部分)。"""
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
        '</svg>'
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


# ----------------------------------------------------------------------
# 红色矢量图标按钮 (用于草图中红色的所有功能键)
# ----------------------------------------------------------------------
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
        self._disabled_color = QColor("#555555")  # "功能不可用"时的灰
        self._active = active
        self._enabled_visual = True
        self._size = size
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
        """视觉禁用(变灰),不影响实际可点击。"""
        if self._enabled_visual != enabled:
            self._enabled_visual = enabled
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        # 激活态加一个淡灰底圈
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
        path = LUCIDE_STROKE.get(self._icon_name)
        if path:
            _draw_lucide_stroke(p, icon_rect, path, col, stroke_ratio=2.2 / 24.0)
        p.end()


# ----------------------------------------------------------------------
# 圆形按钮 (用于播放/上下首三大键 - 白色边框,内嵌图标)
# ----------------------------------------------------------------------
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
        # 圆环
        pen = QPen(col)
        pen.setWidthF(max(1.6, self.width() * 0.030))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)
        # 内部图标:占圆直径的约 42%
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


# ----------------------------------------------------------------------
# 封面显示
# ----------------------------------------------------------------------
class AlbumCover(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self.setMinimumSize(180, 180)
        # 让 widget 真正按 1:1 缩放:宽度可弹性,高度跟随宽度
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
        # 始终保持正方形 - 居中，尺寸稍微缩小一些(打九折)以防过挤
        base_side = min(rect.width(), rect.height())
        side = int(base_side * 0.97)
        x = (rect.width() - side) // 2
        y = (rect.height() - side) // 2
        target = QRectF(x, y, side, side)
        # 封面或占位
        if self._pixmap and not self._pixmap.isNull():
            # 有封面:撑满,不画边框
            scaled = self._pixmap.scaled(
                int(side), int(side),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            sx = x + (side - scaled.width()) // 2
            sy = y + (side - scaled.height()) // 2
            p.drawPixmap(sx, sy, scaled)
        else:
            # 无封面占位:画淡灰边框 + cover 字样
            pen = QPen(QColor(80, 80, 80))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(target.adjusted(0.5, 0.5, -0.5, -0.5))
            f = QFont()
            f.setPointSize(max(14, side // 12))
            p.setFont(f)
            p.setPen(Theme.TEXT_DIM)
            p.drawText(target, Qt.AlignmentFlag.AlignCenter, "cover")
        p.end()


# ----------------------------------------------------------------------
# 进度条
# ----------------------------------------------------------------------
class ProgressBar(QWidget):
    """带可拖动滑块的水平进度条。"""

    seek_requested = pyqtSignal(int)  # 用户拖到的毫秒位置

    _DOT_R = 6           # 圆点半径
    _PAD = 7             # 两侧内边距(略大于半径,防止抗锯齿被裁)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._position = 0
        self._duration = 0
        self._dragging = False
        # 高度需要 ≥ 圆点直径,留点余量
        self.setFixedHeight(self._DOT_R * 2 + 6)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_position(self, ms: int) -> None:
        if not self._dragging:
            self._position = max(0, min(ms, self._duration))
            self.update()

    def set_duration(self, ms: int) -> None:
        self._duration = max(0, ms)
        self.update()

    # ---------- 鼠标 ----------
    def _bar_range(self) -> tuple[int, int]:
        """实际进度条的左/右像素位置(扣除两侧 padding)。"""
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

        # 背景轨道
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(Theme.PROGRESS_BG))
        p.drawRoundedRect(QRectF(left, y, bar_w, h), 2, 2)

        # 已播放
        if self._duration > 0 and bar_w > 0:
            ratio = max(0.0, min(1.0, self._position / self._duration))
            played_w = bar_w * ratio
            p.setBrush(QBrush(Theme.PROGRESS_FG))
            p.drawRoundedRect(QRectF(left, y, played_w, h), 2, 2)

            # 圆点中心:始终在 [left, right] 之间,两端不再被裁
            cx = left + played_w
            cy = self.height() / 2
            p.drawEllipse(QPointF(cx, cy), self._DOT_R, self._DOT_R)

        p.end()


# ----------------------------------------------------------------------
# 滚动文本(供长歌名用)
# ----------------------------------------------------------------------
class ScrollingLabel(QLabel):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._direction = 1
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 关键: 水平方向 Ignored, 这样无论文字多长都不会向父布局请求更多宽度,
        # 防止切歌时父级 PlayerPanel 的 sizeHint 跟着变,从而抖动 splitter
        sp = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setSizePolicy(sp)

    def sizeHint(self) -> QSize:  # noqa: N802
        # 高度跟随字体,宽度返回 0(由父布局决定实际显示宽度)
        fm = self.fontMetrics()
        return QSize(0, fm.height() + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def setText(self, text: str) -> None:  # noqa: N802
        super().setText(text)
        self._offset = 0
        self._maybe_start_timer()

    def _maybe_start_timer(self) -> None:
        # 仅当 widget 可见且文本超出宽度才启用滚动定时器
        if not self.isVisible():
            self._timer.stop()
            return
        fm = self.fontMetrics()
        if fm.horizontalAdvance(self.text()) > self.width():
            if not self._timer.isActive():
                self._timer.start(30)
        else:
            self._timer.stop()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._maybe_start_timer()

    def hideEvent(self, e):  # noqa: N802
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self) -> None:
        self._offset += self._direction
        fm = self.fontMetrics()
        max_off = fm.horizontalAdvance(self.text()) - self.width() + 20
        if self._offset >= max_off:
            self._direction = -1
        elif self._offset <= 0:
            self._direction = 1
        self.update()

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
    """高解析度音频徽章。

    visible=True 时画一个金色描边 + "HR" 文字的小圆角矩形;
    visible=False 时整个 widget 完全透明(全黑)。
    """

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
