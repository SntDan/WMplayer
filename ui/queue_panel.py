"""Playback queue panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.playlist import Playlist
from ui.i18n import tr
from ui.list_delegates import ROLE_IS_PLAYING
from ui.list_helpers import (
    add_list_header,
    connect_debounced_filter,
    cover_list,
    suspended_updates,
    track_item,
)
from ui.theme import BTN_QSS as _BTN_QSS


class QueuePanel(QWidget):
    """Playback queue panel."""

    track_double_clicked = pyqtSignal(int)
    remove_requested = pyqtSignal(int)
    clear_requested = pyqtSignal()
    save_as_playlist_requested = pyqtSignal(str)

    def __init__(self, playlist: Playlist, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._playlist = playlist
        self._current_item = None
        self._build_ui()
        self._wire()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        self.title_label, self.count_label = add_list_header(
            outer, tr("queue"), tr("tracks_count", n=0)
        )

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

        self.list = cover_list()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._playlist.changed.connect(self.refresh)
        self._playlist.current_changed.connect(self._on_current_changed)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_clear.clicked.connect(self.clear_requested.emit)
        self._search_timer = connect_debounced_filter(
            self, self.search, self._apply_filter
        )

        sc = QShortcut(QKeySequence("Delete"), self.list)
        sc.activated.connect(self._delete_selected)

    def refresh(self) -> None:
        with suspended_updates(self.list):
            self.list.clear()
            self._current_item = None
            for i, t in enumerate(self._playlist.tracks):
                self.list.addItem(track_item(t, i))
        self.count_label.setText(tr("tracks_count", n=len(self._playlist)))
        self._highlight_current()
        self._apply_filter(self.search.text())
        self._scroll_to_current()

    def _highlight_current(self) -> None:
        current = self._playlist.current_index
        if self._current_item is not None:
            self._current_item.setData(ROLE_IS_PLAYING, False)
        item = self.list.item(current)
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
        item = self.list.item(current)
        if item is not None:
            self.list.scrollToItem(item, QListWidget.ScrollHint.PositionAtCenter)

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
            [
                idx
                for idx in (it.data(Qt.ItemDataRole.UserRole) for it in items)
                if isinstance(idx, int)
            ],
            reverse=True,
        )
        for i in idxs:
            self.remove_requested.emit(i)

    def _on_save(self) -> None:
        if len(self._playlist) == 0:
            return
        name, ok = QInputDialog.getText(
            self, tr("save_as_playlist"), tr("playlist_name")
        )
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
