"""Consistent hover timing and wrapped tooltips across the application."""

from math import ceil

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QPersistentModelIndex, QRect, Qt, QTimer
from PyQt6.QtGui import (
    QAbstractTextDocumentLayout, QColor, QCursor, QFontMetrics, QPainter, QPalette,
    QTextDocument, QTextOption,
)
from PyQt6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QApplication, QCheckBox, QLabel, QStyle,
    QStyleOptionButton, QStyleOptionViewItem, QWidget,
)

from .list_delegates import CoverRowDelegate, ROLE_SUBTITLE


def _text_rect(widget, rect, text, alignment, font=None):
    metrics = QFontMetrics(font or widget.font())
    visible = metrics.elidedText(str(text), Qt.TextElideMode.ElideRight, rect.width())
    return widget.style().itemTextRect(metrics, rect, int(alignment), True, visible)


def _widget_text_rect(widget):
    rect = widget.contentsRect()
    alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    if isinstance(widget, QCheckBox):
        option = QStyleOptionButton()
        widget.initStyleOption(option)
        rect = widget.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, widget)
        text = widget.text()
    elif isinstance(widget, QLabel):
        margin = widget.margin()
        rect.adjust(margin, margin, -margin, -margin)
        alignment = widget.alignment()
        text = widget.text()
    elif isinstance(widget, QAbstractButton) and widget.text():
        text = widget.text()
        alignment = Qt.AlignmentFlag.AlignCenter
    else:
        return rect
    return _text_rect(widget, rect, text, alignment)


class _ToolTip(QWidget):
    def __init__(self, width: int) -> None:
        super().__init__(None, Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(width)
        self._document = QTextDocument(self)
        self._document.setDocumentMargin(0)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._document.setDefaultTextOption(option)

    def text(self) -> str:
        return self._document.toPlainText()

    def setText(self, text: str) -> None:  # noqa: N802
        font = self.font()
        font.setPixelSize(13)
        self._document.setDefaultFont(font)
        self._document.setPlainText(text)
        self._document.setTextWidth(self.width() - 18)
        self.setFixedHeight(ceil(self._document.size().height()) + 14)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1F1F1F"))
        painter.setPen(QColor("#333333"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.translate(9, 7)
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.ColorRole.Text, QColor("#FFFFFF"))
        self._document.documentLayout().draw(painter, context)


class HoverToolTips(QObject):
    SHOW_DELAY_MS = 200
    HIDE_DELAY_MS = 200
    WIDTH = 300

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._source = None
        self._index = None
        self._position = QPoint()
        self._popup = _ToolTip(self.WIDTH)
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(self.SHOW_DELAY_MS)
        self._show_timer.timeout.connect(self._show)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(self.HIDE_DELAY_MS)
        self._hide_timer.timeout.connect(self._hide)
        app.installEventFilter(self)
        app.aboutToQuit.connect(self._popup.close)
        self.destroyed.connect(self._popup.deleteLater)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if not isinstance(watched, QWidget) or watched is self._popup:
            return False
        kind = event.type()
        if kind == QEvent.Type.ToolTip:
            # Native tooltips must not start a second timing/positioning path.
            return True
        if kind in (QEvent.Type.Enter, QEvent.Type.MouseMove):
            self._hover(watched, QCursor.pos())
        if kind == QEvent.Type.Leave and watched is self._source:
            self._leave()
        elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel,
                      QEvent.Type.KeyPress, QEvent.Type.WindowDeactivate):
            self._hide()
        elif kind == QEvent.Type.Hide and self._source is not None:
            if watched is self._source or watched.isAncestorOf(self._source):
                self._hide()
        return False

    def _hover(self, widget: QWidget, position: QPoint) -> None:
        # Mouse moves also reach ancestors; resolve the widget under the pointer.
        widget = QApplication.widgetAt(position) or widget
        source, index, text, rects = self._target(widget, position)
        local_pos = source.mapFromGlobal(position) if source is not None else QPoint()
        rect = next((r for r in rects if r.adjusted(-4, -3, 4, 3).contains(local_pos)), QRect())
        if not text or rect.isEmpty():
            if source is not None and (source is not self._source or index != self._index):
                self._hide()
            else:
                self._leave()
            return
        anchor = source.mapToGlobal(rect.bottomRight())
        if source is self._source and index == self._index:
            self._hide_timer.stop()
            if anchor != self._position:
                self._position = anchor
                if self._popup.isVisible():
                    self._show()
            if not self._popup.isVisible() and not self._show_timer.isActive():
                self._show_timer.start()
            return
        self._hide()
        self._source, self._index = source, index
        self._position = anchor
        self._popup.setFont(source.font())
        self._popup.setText(str(text))
        self._show_timer.start()

    @staticmethod
    def _target(widget: QWidget, position: QPoint):
        while widget is not None:
            view = widget.parentWidget()
            if isinstance(view, QAbstractItemView) and widget is view.viewport():
                widget.setMouseTracking(True)
                index = view.indexAt(widget.mapFromGlobal(position))
                if not index.isValid():
                    return None, None, "", ()
                text = index.data(Qt.ItemDataRole.ToolTipRole)
                if not text:
                    text = index.data(Qt.ItemDataRole.DisplayRole) or ""
                    subtitle = index.data(ROLE_SUBTITLE)
                    if subtitle:
                        text = f"{text}\n{subtitle}"
                option = QStyleOptionViewItem()
                option.initFrom(view)
                delegate = view.itemDelegateForIndex(index)
                delegate.initStyleOption(option, index)
                option.rect = view.visualRect(index)
                option.rect.setWidth(widget.width())
                if isinstance(delegate, CoverRowDelegate):
                    rects = [
                        _text_rect(widget, rect, value, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, font)
                        for rect, font, value in delegate.text_rows(option, index) if value
                    ]
                else:
                    rect = view.style().subElementRect(QStyle.SubElement.SE_ItemViewItemText, option, view)
                    rects = [_text_rect(widget, rect, option.text, option.displayAlignment, option.font)]
                return widget, QPersistentModelIndex(index), text, rects
            if widget.toolTip():
                widget.setMouseTracking(True)
                return widget, None, widget.toolTip(), (_widget_text_rect(widget),)
            widget = widget.parentWidget()
        return None, None, "", ()

    def _leave(self) -> None:
        self._show_timer.stop()
        if self._popup.isVisible() and not self._hide_timer.isActive():
            self._hide_timer.start()

    def _show(self) -> None:
        if (self._source is None or sip.isdeleted(self._source)
                or not self._source.isVisible()
                or (self._index is not None and not self._index.isValid())):
            self._hide()
            return
        position = self._position + QPoint(4, 4)
        screen = QApplication.screenAt(self._position)
        if screen is not None:
            bounds = screen.availableGeometry()
            rightmost = bounds.right() - self._popup.width() + 1
            position.setX(max(bounds.left(), min(position.x(), rightmost)))
            if position.y() + self._popup.height() > bounds.bottom() + 1:
                position.setY(self._position.y() - self._popup.height() - 8)
            position.setY(max(bounds.top(), position.y()))
        self._popup.move(position)
        self._popup.show()

    def _hide(self) -> None:
        self._show_timer.stop()
        self._hide_timer.stop()
        self._popup.hide()
        self._source = self._index = None
