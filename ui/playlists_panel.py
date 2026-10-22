"""Playlist browser panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.playlist_store import PlaylistStore
from core.thumbnails import thumb_path_for
from ui.i18n import tr
from ui.list_delegates import ROLE_SUBTITLE, ROLE_THUMB_PATHS
from ui.list_helpers import add_list_header, cover_list, suspended_updates


class _DirectoryLabel(QLabel):
    """Elide the directory within a single search-box-height row."""

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("color: #666;")

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = self.fontMetrics()
        # Match QLineEdit: inner margins (2), theme padding (8), border (2).
        return QSize(0, max(metrics.height(), 14) + 12)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, rect.width()
        )
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text
        )


class PlaylistsPanel(QWidget):
    open_playlist = pyqtSignal(str)
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
        outer.setContentsMargins(20, 6, 20, 16)
        outer.setSpacing(10)

        header = QVBoxLayout()
        header.setSpacing(6)
        outer.addLayout(header)
        self.title_label, self.count_label = add_list_header(
            header, tr("playlists"), tr("playlists_count", n=0)
        )

        self.path_label = _DirectoryLabel()
        header.addWidget(self.path_label)

        self.list = cover_list()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._store.changed.connect(self.refresh)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

    def refresh(self) -> None:
        self.path_label.setText(
            tr("default_playlist_dir", path=self._store.default_dir)
        )
        self.path_label.setToolTip(self.path_label.text())
        with suspended_updates(self.list):
            self.list.clear()
            for name, paths in self._store.iter_playlists():
                it = QListWidgetItem(name)
                it.setData(Qt.ItemDataRole.UserRole, name)
                it.setData(ROLE_SUBTITLE, tr("tracks_count", n=len(paths)))
                it.setData(ROLE_THUMB_PATHS, [thumb_path_for(p) for p in paths[:4]])
                self.list.addItem(it)
        self.count_label.setText(tr("playlists_count", n=self.list.count()))

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
        a_open = menu.addAction(tr("load_and_play"))
        a_rename = menu.addAction(tr("rename"))
        a_del = menu.addAction(tr("delete"))
        act = menu.exec(self.list.mapToGlobal(pos))
        if act == a_open:
            self.open_playlist.emit(name)
        elif act == a_rename:
            new, ok = QInputDialog.getText(
                self, tr("rename"), tr("new_name"), text=name
            )
            if ok and new.strip() and new.strip() != name:
                self.rename_playlist.emit(name, new.strip())
        elif act == a_del:
            ans = QMessageBox.question(
                self, tr("delete_playlist"), tr("delete_playlist_confirm", name=name)
            )
            if ans == QMessageBox.StandardButton.Yes:
                self.delete_playlist.emit(name)

    def retranslate(self) -> None:
        self.title_label.setText(tr("playlists"))
        self.refresh()
