"""
播放队列视图
============
显示当前正在播的曲目集合,支持双击播放、右键移除、Delete 删除。
顶部有"另存为歌单"按钮,把当前队列保存成 .m3u8。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import BTN_QSS as _BTN_QSS

from core.playlist import Playlist
from core.thumbnails import thumb_path_for
from ui.i18n import tr
from ui.list_delegates import (
    CoverRowDelegate,
    ROLE_IS_HR,
    ROLE_IS_PLAYING,
    ROLE_SUBTITLE,
    ROLE_THUMB_PATH,
)


class QueuePanel(QWidget):
    """当前播放队列。"""

    track_double_clicked = pyqtSignal(int)
    remove_requested = pyqtSignal(int)
    clear_requested = pyqtSignal()
    save_as_playlist_requested = pyqtSignal(str)   # 用户输入的歌单名

    def __init__(self, playlist: Playlist, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._playlist = playlist
        self._index_items = {}
        self._current_item = None
        self._build_ui()
        self._wire()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        # 标题行
        header = QHBoxLayout()
        self.title_label = QLabel(tr("queue"))
        f = QFont(); f.setPointSize(15); f.setBold(True); self.title_label.setFont(f)
        self.count_label = QLabel(tr("tracks_count", n=0))
        self.count_label.setStyleSheet("color: #9E9E9E;")
        header.addWidget(self.title_label)
        header.addStretch(1)
        header.addWidget(self.count_label)
        outer.addLayout(header)

        # 操作行
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_queue"))
        self.search.setClearButtonEnabled(True)
        action_row.addWidget(self.search, 1)

        self.btn_save = QPushButton(tr("save_as_playlist"))
        self.btn_clear = QPushButton(tr("clear"))
        for b in (self.btn_save, self.btn_clear):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_BTN_QSS)
            action_row.addWidget(b)
        outer.addLayout(action_row)

        # 列表
        self.list = QListWidget()
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setUniformItemSizes(True)
        self.list.setMouseTracking(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._row_delegate = CoverRowDelegate(self.list)
        self.list.setItemDelegate(self._row_delegate)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._playlist.changed.connect(self.refresh)
        self._playlist.current_changed.connect(self._on_current_changed)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_clear.clicked.connect(self.clear_requested.emit)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(90)
        self._search_timer.timeout.connect(lambda: self._apply_filter(self.search.text()))
        self.search.textChanged.connect(lambda _text: self._search_timer.start())

        sc = QShortcut(QKeySequence("Delete"), self.list)
        sc.activated.connect(self._delete_selected)

    # ------------------------------------------------------------------
    # 数据更新
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self.list.setUpdatesEnabled(False)
        try:
            self.list.clear()
            self._index_items = {}
            self._current_item = None
            for i, t in enumerate(self._playlist.tracks):
                it = QListWidgetItem(t.title or "")
                it.setData(Qt.ItemDataRole.UserRole, i)
                it.setData(ROLE_THUMB_PATH, thumb_path_for(t.path))
                it.setData(ROLE_SUBTITLE, t.artist or "")
                it.setData(ROLE_IS_HR, t.is_high_res())
                self.list.addItem(it)
                self._index_items[i] = it
        finally:
            self.list.setUpdatesEnabled(True)
        self.count_label.setText(tr("tracks_count", n=len(self._playlist)))
        self._highlight_current()
        self._apply_filter(self.search.text())
        self._scroll_to_current()

    def _highlight_current(self) -> None:
        current = self._playlist.current_index
        if self._current_item is not None:
            self._current_item.setData(ROLE_IS_PLAYING, False)
        item = self._index_items.get(current)
        if item is not None:
            item.setData(ROLE_IS_PLAYING, True)
        self._current_item = item

    def _on_current_changed(self, _index: int) -> None:
        self._highlight_current()
        self._scroll_to_current()

    def _scroll_to_current(self) -> None:
        current = self._playlist.current_index
        if current < 0:
            return
        item = self._index_items.get(current)
        if item is not None:
            self.list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _on_double_click(self, item: QListWidgetItem) -> None:
        idx = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(idx, int):
            self.track_double_clicked.emit(idx)

    def _on_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        a_play = menu.addAction(tr("play"))
        a_remove = menu.addAction(tr("remove_from_queue"))
        act = menu.exec(self.list.mapToGlobal(pos))
        idx = item.data(Qt.ItemDataRole.UserRole)
        if act == a_play:
            self.track_double_clicked.emit(idx)
        elif act == a_remove:
            self.remove_requested.emit(idx)

    def _delete_selected(self) -> None:
        items = self.list.selectedItems()
        idxs = sorted(
            [idx for idx in (it.data(Qt.ItemDataRole.UserRole) for it in items) if isinstance(idx, int)],
            reverse=True,
        )
        for i in idxs:
            self.remove_requested.emit(i)

    def _on_save(self) -> None:
        if len(self._playlist) == 0:
            return
        name, ok = QInputDialog.getText(self, tr("save_as_playlist"), tr("playlist_name"))
        if ok and name.strip():
            self.save_as_playlist_requested.emit(name.strip())

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not text:
                item.setHidden(False)
                continue
            idx = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(idx, int):
                item.setHidden(True)
                continue
            t = self._playlist.get(idx)
            if t is None:
                item.setHidden(True)
                continue
            hay = f"{t.title} {t.artist} {t.album} {t.filename}".lower()
            item.setHidden(text not in hay)

    def retranslate(self) -> None:
        self.title_label.setText(tr("queue"))
        self.search.setPlaceholderText(tr("search_queue"))
        self.btn_save.setText(tr("save_as_playlist"))
        self.btn_clear.setText(tr("clear"))
        self.count_label.setText(tr("tracks_count", n=len(self._playlist)))
