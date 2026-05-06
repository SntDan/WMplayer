"""
歌单视图
========
显示 playlists/ 目录下所有 .m3u8 歌单。
- 双击 → 加载到播放队列(并播放第一首)
- 右键: 重命名 / 删除
- 顶部"新建空歌单"按钮
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.playlist_store import PlaylistStore


class PlaylistsPanel(QWidget):

    open_playlist = pyqtSignal(str)         # 双击某个歌单 → 加载并播放
    new_empty_playlist = pyqtSignal(str)    # 新建空歌单
    rename_playlist = pyqtSignal(str, str)  # (old, new)
    delete_playlist = pyqtSignal(str)

    def __init__(self, store: PlaylistStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._build_ui()
        self._wire()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        # 标题
        header = QHBoxLayout()
        title = QLabel("歌单")
        f = QFont(); f.setPointSize(15); f.setBold(True); title.setFont(f)
        self.count_label = QLabel("0 个")
        self.count_label.setStyleSheet("color: #9E9E9E;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        outer.addLayout(header)

        # 路径提示
        self.path_label = QLabel()
        self.path_label.setStyleSheet("color: #666; font-size: 11px;")
        self.path_label.setWordWrap(True)
        outer.addWidget(self.path_label)

        # 操作行
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.btn_new = QPushButton("+ 新建空歌单")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setStyleSheet(_BTN_QSS)
        action_row.addWidget(self.btn_new)
        action_row.addStretch(1)
        outer.addLayout(action_row)

        # 列表
        self.list = QListWidget()
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setUniformItemSizes(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._store.changed.connect(self.refresh)
        self.btn_new.clicked.connect(self._on_new)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

    def refresh(self) -> None:
        self.path_label.setText(f"目录:{self._store.directory}")
        self.list.clear()
        names = self._store.list_names()
        for name in names:
            it = QListWidgetItem(name)
            it.setData(Qt.ItemDataRole.UserRole, name)
            self.list.addItem(it)
        self.count_label.setText(f"{len(names)} 个")

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "新建空歌单", "歌单名称:")
        if ok and name.strip():
            self.new_empty_playlist.emit(name.strip())

    def _on_double_click(self, item: QListWidgetItem) -> None:
        name = item.data(Qt.ItemDataRole.UserRole)
        if name:
            self.open_playlist.emit(name)

    def _on_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        a_open = menu.addAction("加载并播放")
        a_rename = menu.addAction("重命名…")
        a_del = menu.addAction("删除")
        act = menu.exec(self.list.mapToGlobal(pos))
        if act == a_open:
            self.open_playlist.emit(name)
        elif act == a_rename:
            new, ok = QInputDialog.getText(self, "重命名", "新名称:", text=name)
            if ok and new.strip() and new.strip() != name:
                self.rename_playlist.emit(name, new.strip())
        elif act == a_del:
            ans = QMessageBox.question(
                self, "删除歌单", f"确定要删除歌单 “{name}” 吗?\n(原始音乐文件不会被删除)"
            )
            if ans == QMessageBox.StandardButton.Yes:
                self.delete_playlist.emit(name)


_BTN_QSS = (
    "QPushButton{background:#1a1a1a; border:1px solid #333; "
    "padding:4px 10px; border-radius:4px; color:#FFF;}"
    "QPushButton:hover{background:#2a2a2a; border-color:#E63946;}"
)
