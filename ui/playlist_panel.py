"""
播放列表面板(右半)
==================
显示当前播放列表,支持双击播放、删除、清空、搜索过滤。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.metadata import TrackMetadata
from core.playlist import Playlist
from .theme import Theme


class PlaylistPanel(QWidget):
    """右侧播放列表区。"""

    track_double_clicked = pyqtSignal(int)        # 用户双击索引
    remove_requested = pyqtSignal(int)            # 删除索引
    clear_requested = pyqtSignal()                # 清空
    add_files_requested = pyqtSignal()
    add_folder_requested = pyqtSignal()

    def __init__(self, playlist: Playlist, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._playlist = playlist
        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        # 顶部标题 + 计数
        header = QHBoxLayout()
        title = QLabel("播放列表")
        f = QFont(); f.setPointSize(15); f.setBold(True)
        title.setFont(f)
        self.count_label = QLabel("0 首")
        self.count_label.setStyleSheet("color: #9E9E9E;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        outer.addLayout(header)

        # 搜索框 + 添加按钮
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索 (歌名/艺术家/专辑)")
        self.search.setClearButtonEnabled(True)
        action_row.addWidget(self.search, 1)

        self.btn_add_files = QPushButton("+ 文件")
        self.btn_add_folder = QPushButton("+ 文件夹")
        self.btn_clear = QPushButton("清空")
        for b in (self.btn_add_files, self.btn_add_folder, self.btn_clear):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                "QPushButton{background:#1a1a1a; border:1px solid #333; "
                "padding:4px 10px; border-radius:4px; color:#FFF;}"
                "QPushButton:hover{background:#2a2a2a; border-color:#E63946;}"
            )
            action_row.addWidget(b)
        outer.addLayout(action_row)

        # 列表
        self.list = QListWidget()
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setUniformItemSizes(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._playlist.changed.connect(self.refresh)
        self._playlist.current_changed.connect(self._on_current_changed)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self.btn_add_files.clicked.connect(self.add_files_requested.emit)
        self.btn_add_folder.clicked.connect(self.add_folder_requested.emit)
        self.btn_clear.clicked.connect(self.clear_requested.emit)
        self.search.textChanged.connect(self._apply_filter)

        # Delete 键删除
        sc = QShortcut(QKeySequence("Delete"), self.list)
        sc.activated.connect(self._delete_selected)

    # ------------------------------------------------------------------
    # 数据更新
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        # 用 takeItem 而不是 clear() 以避免微小内存抖动
        self.list.clear()
        for i, t in enumerate(self._playlist.tracks):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setText(self._format_text(i, t))
            self.list.addItem(item)
        self._update_count()
        self._highlight_current()
        self._apply_filter(self.search.text())

    def _format_text(self, index: int, t: TrackMetadata) -> str:
        # 单行紧凑显示,长文本由 QListWidget 自动 elide
        return f"{index + 1:>3}.  {t.title}  —  {t.artist}"

    def _update_count(self) -> None:
        n = len(self._playlist)
        self.count_label.setText(f"{n} 首")

    def _highlight_current(self) -> None:
        current = self._playlist.current_index
        for i in range(self.list.count()):
            item = self.list.item(i)
            idx = item.data(Qt.ItemDataRole.UserRole)
            if idx == current:
                f = item.font(); f.setBold(True); item.setFont(f)
                item.setForeground(Theme.LIST_PLAYING)
            else:
                f = item.font(); f.setBold(False); item.setFont(f)
                item.setForeground(Theme.TEXT)

    def _on_current_changed(self, _index: int) -> None:
        self._highlight_current()
        # 滚动到当前
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == self._playlist.current_index:
                self.list.scrollToItem(
                    self.list.item(i), QListWidget.ScrollHint.PositionAtCenter
                )
                break

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(idx, int):
            self.track_double_clicked.emit(idx)

    def _on_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        act_play = menu.addAction("播放")
        act_remove = menu.addAction("从列表中移除")
        act = menu.exec(self.list.mapToGlobal(pos))
        idx = item.data(Qt.ItemDataRole.UserRole)
        if act == act_play:
            self.track_double_clicked.emit(idx)
        elif act == act_remove:
            self.remove_requested.emit(idx)

    def _delete_selected(self) -> None:
        items = self.list.selectedItems()
        # 倒序删除以保持索引
        idxs = sorted(
            [it.data(Qt.ItemDataRole.UserRole) for it in items], reverse=True
        )
        for i in idxs:
            self.remove_requested.emit(i)

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not text:
                item.setHidden(False)
                continue
            idx = item.data(Qt.ItemDataRole.UserRole)
            t = self._playlist.get(idx)
            if t is None:
                continue
            hay = f"{t.title} {t.artist} {t.album} {t.filename}".lower()
            item.setHidden(text not in hay)
