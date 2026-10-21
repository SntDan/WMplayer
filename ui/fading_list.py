"""List edges that fade into the surrounding panel's existing black gaps."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, Qt
from PyQt6.QtGui import QColor, QCursor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QListWidget, QStyle, QStyleOptionViewItem, QWidget


class _ListEdge(QWidget):
    # Fade over scrolled rows without moving their initial layout positions.
    TOP_DEPTH = 36
    BOTTOM_DEPTH = 24
    TOP_OUTSIDE = 12
    BOTTOM_OUTSIDE = 12

    def __init__(self, view: FadingListWidget, *, top: bool) -> None:
        super().__init__()
        self._view = view
        self._top = top
        self._depth = self.TOP_DEPTH if top else self.BOTTOM_DEPTH
        self._outside = self.TOP_OUTSIDE if top else self.BOTTOM_OUTSIDE
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def _viewport_offset(self) -> int:
        if self._top:
            return -self._outside
        return self._view.viewport().height() - self._depth + self._outside

    def sync(self) -> None:
        view = self._view
        parent = view.parentWidget()
        if self.parentWidget() is not parent:
            self.setParent(parent)
        bar = view.verticalScrollBar()
        active = bar.value() > bar.minimum() if self._top else bar.value() < bar.maximum()
        if parent is None or not view.isVisible() or not active:
            self.hide()
            return
        viewport = view.viewport()
        origin = viewport.mapTo(parent, QPoint())
        y = origin.y() + self._viewport_offset()
        self.setGeometry(origin.x(), y, viewport.width(), self._depth)
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        view = self._view
        viewport = view.viewport()
        offset = self._viewport_offset()
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        # indexAt also resolves rows just outside the viewport. Repaint the edge
        # slivers before fading them, keeping the rest of the viewport intact.
        rows = set()
        hovered = view.indexAt(viewport.mapFromGlobal(QCursor.pos()))
        for y in range(offset, offset + self.height()):
            index = view.indexAt(QPoint(0, y))
            if not index.isValid() or index.row() in rows:
                continue
            rows.add(index.row())
            option = QStyleOptionViewItem()
            view.initViewItemOption(option)
            rect = view.visualRect(index)
            # visualRect may still include the scrollbar after initial layout
            # or a resize. Use the real paint width to keep ellipsis and badges
            # in exactly the same positions as the viewport's row rendering.
            rect.setWidth(viewport.width())
            option.rect = rect.translated(0, -offset)
            if view.selectionModel().isSelected(index):
                option.state |= QStyle.StateFlag.State_Selected
            if index == hovered:
                option.state |= QStyle.StateFlag.State_MouseOver
            view.itemDelegateForIndex(index).paint(painter, option, index)

        fade = QLinearGradient(0, 0.5, 0, self.height() - 0.5)
        opaque, clear = QColor(0, 0, 0), QColor(0, 0, 0, 0)
        fade.setColorAt(0, opaque if self._top else clear)
        fade.setColorAt(1, clear if self._top else opaque)
        painter.fillRect(self.rect(), fade)


class FadingListWidget(QListWidget):
    """Fade edges with hidden rows, preserving the initial row position."""

    def __init__(self) -> None:
        super().__init__()
        self._edges = (_ListEdge(self, top=True), _ListEdge(self, top=False))
        for edge in self._edges:
            self.destroyed.connect(edge.deleteLater)
        self.viewport().installEventFilter(self)
        self.verticalScrollBar().valueChanged.connect(self._sync_edges)
        self.verticalScrollBar().rangeChanged.connect(self._sync_edges)
        self.selectionModel().selectionChanged.connect(self._sync_edges)
        self.model().dataChanged.connect(self._sync_edges)

    def _sync_edges(self, *_args) -> None:
        for edge in self._edges:
            edge.sync()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.viewport() and event.type() in (
            QEvent.Type.Paint, QEvent.Type.Resize, QEvent.Type.Move,
            QEvent.Type.MouseMove, QEvent.Type.Enter, QEvent.Type.Leave,
        ):
            self._sync_edges()
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_edges()

    def hideEvent(self, event) -> None:  # noqa: N802
        for edge in self._edges:
            edge.hide()
        super().hideEvent(event)

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._sync_edges()
