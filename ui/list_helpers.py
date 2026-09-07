"""Shared helpers for searchable list panels."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.metadata import TrackMetadata
from core.thumbnails import thumb_path_for
from ui.list_delegates import (
    ROLE_IS_HR,
    ROLE_SUBTITLE,
    ROLE_THUMB_PATH,
    CoverRowDelegate,
)


def add_list_header(
    layout: QVBoxLayout, title: str, count: str
) -> tuple[QLabel, QLabel]:
    """Add the common list title and right-aligned count."""
    row = QHBoxLayout()
    title_label, count_label = QLabel(title), QLabel(count)
    font = QFont()
    font.setPointSize(15)
    font.setBold(True)
    title_label.setFont(font)
    count_label.setStyleSheet("color: #9E9E9E;")
    row.addWidget(title_label)
    row.addStretch(1)
    row.addWidget(count_label)
    layout.addLayout(row)
    return title_label, count_label


def cover_list(*, uniform_sizes: bool = True) -> QListWidget:
    """Build the shared cover list without imposing panel-specific selection."""
    widget = QListWidget()
    widget.setTextElideMode(Qt.TextElideMode.ElideRight)
    widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    widget.setUniformItemSizes(uniform_sizes)
    widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
    widget.setMouseTracking(True)
    widget.setItemDelegate(CoverRowDelegate(widget))
    return widget


def track_item(track: TrackMetadata, data: object) -> QListWidgetItem:
    """Build a track row; panels choose whether its identity is a path or index."""
    item = QListWidgetItem(track.title or "")
    item.setData(Qt.ItemDataRole.UserRole, data)
    item.setData(ROLE_THUMB_PATH, thumb_path_for(track.path))
    item.setData(ROLE_SUBTITLE, track.artist or "")
    item.setData(ROLE_IS_HR, track.is_high_res())
    return item


def connect_debounced_filter(
    parent: QObject,
    editor: QLineEdit,
    callback: Callable[[str], None],
    interval_ms: int = 90,
) -> QTimer:
    """Call a text filter after typing has paused for a short interval."""
    timer = QTimer(parent)
    timer.setSingleShot(True)
    timer.setInterval(interval_ms)
    timer.timeout.connect(lambda: callback(editor.text()))
    editor.textChanged.connect(lambda _text: timer.start())
    return timer


def filter_items_by_text(
    widget: QListWidget,
    text: str,
    role: int = Qt.ItemDataRole.UserRole,
) -> None:
    """Show list items whose string data contains the requested text."""
    query = (text or "").strip().lower()
    for index in range(widget.count()):
        item = widget.item(index)
        value = item.data(role)
        item.setHidden(bool(query) and query not in str(value or "").lower())


@contextmanager
def suspended_updates(widget: QWidget) -> Iterator[None]:
    """Temporarily pause repainting while rebuilding a widget."""
    enabled = widget.updatesEnabled()
    widget.setUpdatesEnabled(False)
    try:
        yield
    finally:
        widget.setUpdatesEnabled(enabled)
