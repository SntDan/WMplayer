"""
列表项渲染器
============
左侧小封面 + 右侧两行文字 (上=主标题, 下=副标题)。

性能要点:
- 缩略图已离线缩到 64x64,这里只读小图,不再每帧解码大图
- 使用 QPixmapCache(LRU) 缓存解码后的 QPixmap,避免反复读盘
- 配合 QListWidget.setUniformItemSizes(True),Qt 仅绘制可见项
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap, QPixmapCache
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


# 调大全局 QPixmapCache 上限,大型曲库滚动时不至于反复换出
QPixmapCache.setCacheLimit(60 * 1024)  # 60 MB


# 自定义角色,与 DisplayRole/UserRole 错开
ROLE_THUMB_PATH = Qt.ItemDataRole.UserRole + 1
ROLE_SUBTITLE = Qt.ItemDataRole.UserRole + 2
ROLE_IS_PLAYING = Qt.ItemDataRole.UserRole + 3
ROLE_IS_HR = Qt.ItemDataRole.UserRole + 4
ROLE_THUMB_PATHS = Qt.ItemDataRole.UserRole + 5


_HR_BADGE_W = 26
_HR_BADGE_H = 16
_HR_GOLD = QColor("#D4AF37")
_SEPARATOR_COLOR = QColor("#202020")


class CoverRowDelegate(QStyledItemDelegate):
    """带封面缩略图 + 上下两行文字的列表项绘制器。"""

    THUMB_PX = 52
    PAD = 10
    ROW_H = 52                     # 等于封面尺寸, 行与行之间封面完全贴合零间隙
    HR_RESERVED_W = _HR_BADGE_W + 12   # 右侧给 HR 徽章预留的横向空间

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width() if option.rect.width() > 0 else 200, self.ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect

        # 背景: 选中 / 悬停
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor("#3a1010"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor("#1a1a1a"))

        # 缩略图: 顶对齐, 紧贴左边 (封面间无空隙, 仅由底部分隔线分开)
        thumb_x = rect.left()
        thumb_y = rect.top()
        thumb_rect = QRect(thumb_x, thumb_y, self.THUMB_PX, self.THUMB_PX)

        thumb_paths = index.data(ROLE_THUMB_PATHS)
        if isinstance(thumb_paths, (list, tuple)) and thumb_paths:
            self._paint_mosaic(painter, thumb_rect, list(thumb_paths)[:4], option.font)
        else:
            thumb_path = index.data(ROLE_THUMB_PATH)
            pix = self._load_pixmap(thumb_path)
            if pix is not None and not pix.isNull():
                painter.drawPixmap(thumb_rect, pix)
            else:
                self._paint_placeholder(painter, thumb_rect, option.font)

        # HR 徽章 (右侧固定位置, 占的位置无论是否显示都保留, 让其他歌曲对齐)
        is_hr = bool(index.data(ROLE_IS_HR))
        badge_right = rect.right() - 14
        badge_left = badge_right - _HR_BADGE_W
        if is_hr:
            badge_y = rect.top() + (self.THUMB_PX - _HR_BADGE_H) // 2
            badge_rect = QRect(badge_left, badge_y, _HR_BADGE_W, _HR_BADGE_H)
            self._paint_hr_badge(painter, badge_rect, option.font)

        # 文字区: 起点 = 封面右 + PAD, 终点 = HR 区域左 - PAD
        text_x = thumb_rect.right() + self.PAD
        text_w = badge_left - self.PAD - text_x
        if text_w < 30:
            painter.restore()
            return

        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        subtitle = index.data(ROLE_SUBTITLE) or ""
        is_playing = bool(index.data(ROLE_IS_PLAYING))

        base_pt = self._base_pt(option.font)

        # 标题
        title_font = QFont(option.font)
        self._set_font_size(title_font, base_pt + 1)
        if is_playing:
            title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#E63946") if is_playing else QColor("#FFFFFF"))
        title_fm = QFontMetrics(title_font)
        title_h = title_fm.height()

        # 副标题
        sub_font = QFont(option.font)
        self._set_font_size(sub_font, max(8, base_pt - 1))
        sub_fm = QFontMetrics(sub_font)
        sub_h = sub_fm.height()

        # 垂直居中两行 (限制在封面高度内, 底部 1px 留给分隔线)
        block_h = title_h + 2 + sub_h
        block_top = rect.top() + (self.THUMB_PX - block_h) // 2

        title_rect = QRect(text_x, block_top, text_w, title_h)
        elided_title = title_fm.elidedText(str(title), Qt.TextElideMode.ElideRight, text_w)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            elided_title,
        )

        sub_rect = QRect(text_x, title_rect.bottom() + 2, text_w, sub_h)
        painter.setFont(sub_font)
        painter.setPen(QColor("#9A9A9A"))
        elided_sub = sub_fm.elidedText(str(subtitle), Qt.TextElideMode.ElideRight, text_w)
        painter.drawText(
            sub_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            elided_sub,
        )

        # 1px 灰色分隔线: 画在行底, 与下一张封面顶边重合, 既有分割线又零间隙
        painter.setPen(_SEPARATOR_COLOR)
        y = rect.bottom()
        painter.drawLine(rect.left(), y, rect.right(), y)

        painter.restore()

    @staticmethod
    def _paint_hr_badge(painter: QPainter, rect: QRect, base_font: QFont) -> None:
        painter.save()
        pen = QPen(_HR_GOLD)
        pen.setWidthF(1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRectF(rect.x() + 0.5, rect.y() + 0.5, rect.width() - 1, rect.height() - 1), 3, 3
        )
        f = QFont(base_font)
        f.setPointSize(8)
        f.setBold(True)
        painter.setFont(f)
        painter.setPen(_HR_GOLD)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "HR")
        painter.restore()

    @classmethod
    def _paint_mosaic(cls, painter: QPainter, rect: QRect, thumb_paths: list, base_font: QFont) -> None:
        tile_w = rect.width() // 2
        tile_h = rect.height() // 2
        for i in range(4):
            col = i % 2
            row = i // 2
            tile = QRect(
                rect.left() + col * tile_w,
                rect.top() + row * tile_h,
                tile_w if col == 0 else rect.width() - tile_w,
                tile_h if row == 0 else rect.height() - tile_h,
            )
            path = thumb_paths[i] if i < len(thumb_paths) else None
            pix = cls._load_pixmap(path)
            if pix is not None and not pix.isNull():
                painter.drawPixmap(tile, pix)
            else:
                cls._paint_placeholder(painter, tile, base_font, compact=True)

    @classmethod
    def _paint_placeholder(
        cls,
        painter: QPainter,
        rect: QRect,
        base_font: QFont,
        *,
        compact: bool = False,
    ) -> None:
        painter.fillRect(rect, QColor("#222"))
        painter.setPen(QColor("#555"))
        f = QFont(base_font)
        delta = 0 if compact else 4
        cls._set_font_size(f, cls._base_pt(base_font) + delta)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "♪")

    @staticmethod
    def _base_pt(font: QFont) -> int:
        """从 option.font 取一个安全的"基准点数",兼容 setPixelSize 创建的字体。"""
        pt = font.pointSize()
        if pt > 0:
            return pt
        # 字体使用像素尺寸时,pointSize() 返回 -1, 估算回点数(1pt ≈ 1.333px)
        px = font.pixelSize()
        if px > 0:
            return max(8, int(round(px / 1.333)))
        return 10

    @staticmethod
    def _set_font_size(font: QFont, pt: int) -> None:
        font.setPointSize(max(1, int(pt)))

    @staticmethod
    def _load_pixmap(thumb_path) -> Optional[QPixmap]:
        if not thumb_path:
            return None
        key = str(thumb_path)
        cached = QPixmapCache.find(key)
        if cached is not None:
            return cached
        if not os.path.isfile(key) or os.path.getsize(key) == 0:
            return None
        pix = QPixmap(key)
        if pix.isNull():
            return None
        QPixmapCache.insert(key, pix)
        return pix
