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

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap, QPixmapCache
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem


# 调大全局 QPixmapCache 上限,大型曲库滚动时不至于反复换出
QPixmapCache.setCacheLimit(60 * 1024)  # 60 MB


# 自定义角色,与 DisplayRole/UserRole 错开
ROLE_THUMB_PATH = Qt.ItemDataRole.UserRole + 1
ROLE_SUBTITLE = Qt.ItemDataRole.UserRole + 2


class CoverRowDelegate(QStyledItemDelegate):
    """带封面缩略图 + 上下两行文字的列表项绘制器。"""

    THUMB_PX = 44
    PAD = 10
    ROW_H = 60

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width() if option.rect.width() > 0 else 200, self.ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = option.rect

        # 背景: 选中 / 悬停
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor("#3a1010"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor("#1a1a1a"))

        # 缩略图
        thumb_x = rect.left() + self.PAD
        thumb_y = rect.top() + (rect.height() - self.THUMB_PX) // 2
        thumb_rect = QRect(thumb_x, thumb_y, self.THUMB_PX, self.THUMB_PX)

        thumb_path = index.data(ROLE_THUMB_PATH)
        pix = self._load_pixmap(thumb_path)
        if pix is not None and not pix.isNull():
            painter.drawPixmap(thumb_rect, pix)
        else:
            painter.fillRect(thumb_rect, QColor("#222"))
            painter.setPen(QColor("#555"))
            f = QFont(option.font)
            self._set_font_size(f, self._base_pt(option.font) + 4)
            painter.setFont(f)
            painter.drawText(thumb_rect, Qt.AlignmentFlag.AlignCenter, "♪")

        # 文字区
        text_x = thumb_rect.right() + self.PAD
        text_w = rect.right() - text_x - self.PAD
        if text_w < 30:
            painter.restore()
            return

        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        subtitle = index.data(ROLE_SUBTITLE) or ""

        base_pt = self._base_pt(option.font)

        # 标题
        title_font = QFont(option.font)
        self._set_font_size(title_font, base_pt + 1)
        painter.setFont(title_font)
        painter.setPen(QColor("#FFFFFF"))
        title_fm = QFontMetrics(title_font)
        title_h = title_fm.height()

        # 副标题
        sub_font = QFont(option.font)
        self._set_font_size(sub_font, max(8, base_pt - 1))
        sub_fm = QFontMetrics(sub_font)
        sub_h = sub_fm.height()

        # 垂直居中两行
        block_h = title_h + 2 + sub_h
        block_top = rect.top() + (rect.height() - block_h) // 2

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

        painter.restore()

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
