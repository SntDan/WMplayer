"""
曲库视图
========
显示扫描到的所有曲目。可以搜索、双击播放(替换队列)、右键加入队列/加入歌单。
顶部有"扫描曲库"按钮和扫描进度条。
"""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.library import Library
from core.thumbnails import thumb_path_for
from ui.list_delegates import CoverRowDelegate, ROLE_SUBTITLE, ROLE_THUMB_PATH


class LibraryPanel(QWidget):

    # 用户操作信号 (path 或 path 列表)
    play_paths_now = pyqtSignal(list, int)           # 立即替换队列并播放第 N 首
    enqueue_paths = pyqtSignal(list)               # 追加到队列尾
    add_paths_to_playlist = pyqtSignal(list)       # 弹出选择对话框 → 加入某个歌单
    rescan_requested = pyqtSignal()

    def __init__(self, library: Library, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._library = library
        self._build_ui()
        self._wire()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        # 标题 + 计数
        header = QHBoxLayout()
        title = QLabel("曲库")
        f = QFont(); f.setPointSize(15); f.setBold(True); title.setFont(f)
        self.count_label = QLabel("0 首")
        self.count_label.setStyleSheet("color: #9E9E9E;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        outer.addLayout(header)

        # 操作行: 搜索 + 扫描
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索 (歌名/艺术家/专辑)")
        self.search.setClearButtonEnabled(True)
        action_row.addWidget(self.search, 1)

        self.btn_scan = QPushButton("扫描曲库")
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet(_BTN_QSS)
        action_row.addWidget(self.btn_scan)
        outer.addLayout(action_row)

        # 扫描进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet(
            "QProgressBar{border:1px solid #333; border-radius:3px; "
            "background:#1a1a1a; height:14px; text-align:center;}"
            "QProgressBar::chunk{background:#E63946; border-radius:2px;}"
        )
        outer.addWidget(self.progress)

        # 列表
        self.list = QListWidget()
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.setMouseTracking(True)
        self._row_delegate = CoverRowDelegate(self.list)
        self.list.setItemDelegate(self._row_delegate)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._library.tracks_changed.connect(self.refresh)
        self._library.scan_started.connect(self._on_scan_started)
        self._library.scan_progress.connect(self._on_scan_progress)
        self._library.scan_finished.connect(self._on_scan_finished)
        self.btn_scan.clicked.connect(self.rescan_requested.emit)
        self.search.textChanged.connect(self._apply_filter)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.list.clear()
        tracks = self._library.tracks
        for t in tracks:
            it = QListWidgetItem(t.title or "")
            it.setData(Qt.ItemDataRole.UserRole, t.path)
            it.setData(ROLE_THUMB_PATH, thumb_path_for(t.path))
            it.setData(ROLE_SUBTITLE, t.artist or "")
            self.list.addItem(it)
        self.count_label.setText(f"{len(tracks)} 首")
        self._apply_filter(self.search.text())

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def _on_scan_started(self) -> None:
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("正在扫描…")
        self.btn_scan.setEnabled(False)

    def _on_scan_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress.setFormat(f"扫描中 {done}/{total}")

    def _on_scan_finished(self) -> None:
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _selected_paths(self) -> List[str]:
        items = self.list.selectedItems() or ([self.list.currentItem()] if self.list.currentItem() else [])
        return [it.data(Qt.ItemDataRole.UserRole) for it in items if it]

    def _on_double_click(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
        
        # 收集所有当前在视图中可见的歌曲
        visible_paths = []
        start_index = 0
        for i in range(self.list.count()):
            it = self.list.item(i)
            if not it.isHidden():
                p = it.data(Qt.ItemDataRole.UserRole)
                if p:
                    if p == path:
                        start_index = len(visible_paths)
                    visible_paths.append(p)
        
        if visible_paths:
            self.play_paths_now.emit(visible_paths, start_index)
        else:
            self.play_paths_now.emit([path], 0)

    def _on_context_menu(self, pos) -> None:
        if self.list.itemAt(pos) is None:
            return
        menu = QMenu(self)
        a_play = menu.addAction("立即播放(替换队列)")
        a_enq = menu.addAction("加入播放队列")
        a_add = menu.addAction("加入歌单…")
        act = menu.exec(self.list.mapToGlobal(pos))
        paths = self._selected_paths()
        if not paths:
            return
        if act == a_play:
            self.play_paths_now.emit(paths, 0)
        elif act == a_enq:
            self.enqueue_paths.emit(paths)
        elif act == a_add:
            self.add_paths_to_playlist.emit(paths)

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not text:
                item.setHidden(False)
                continue
            path = item.data(Qt.ItemDataRole.UserRole)
            t = self._library.find_by_path(path) if path else None
            if t is None:
                continue
            hay = f"{t.title} {t.artist} {t.album}".lower()
            item.setHidden(text not in hay)


_BTN_QSS = (
    "QPushButton{background:#1a1a1a; border:1px solid #333; "
    "padding:4px 10px; border-radius:4px; color:#FFF;}"
    "QPushButton:hover{background:#2a2a2a; border-color:#E63946;}"
    "QPushButton:disabled{color:#555;}"
)
