"""Shared helpers for searchable list panels."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from PyQt6.QtCore import QObject, Qt, QTimer
from PyQt6.QtWidgets import QLineEdit, QListWidget, QWidget


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
    widget.setUpdatesEnabled(False)
    try:
        yield
    finally:
        widget.setUpdatesEnabled(True)
