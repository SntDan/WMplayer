"""Settings dialog."""

from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QStyle,
    QStyleOptionTabWidgetFrame,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import (
    DEFAULT_CONFIG,
    DEFAULT_VOLUME,
    LIBRARY_CACHE_PATH,
    QUEUE_CACHE_PATH,
    QUEUE_ORIGINAL_CACHE_PATH,
    Config,
    default_library_dir,
    default_playlists_dir,
)
from core.thumbnails import THUMB_DIR
from ui.i18n import language, set_language, tr
from ui.theme import BTN_QSS as _BTN_QSS
from ui.theme import PRIMARY_BTN_QSS as _PRIMARY_BTN_QSS

_CORNER_RADIUS = 4
_TAB_GAP = 2

_SETTINGS_QSS = f"""
QTabWidget, QTabBar, QLabel#settingsAbout {{
    background: transparent;
}}
QTabWidget::pane {{
    background: transparent;
    border: none;
    padding: 5px;
}}
QTabBar::tab {{
    background: transparent;
    border: none;
    padding: 5px 11px;
    margin-right: {_TAB_GAP}px;
    margin-bottom: {_TAB_GAP}px;
}}
QLabel[defaultPath="true"] {{
    background: #0a0a0a;
    border: 1px solid #222;
    border-radius: {_CORNER_RADIUS}px;
    padding: 6px 10px;
    color: #777;
}}
QListWidget {{
    background: #0a0a0a;
}}
QListWidget, QComboBox, QComboBox QAbstractItemView {{
    border: 1px solid #333;
    border-radius: {_CORNER_RADIUS}px;
}}
QCheckBox::indicator {{
    border-radius: {_CORNER_RADIUS}px;
}}
"""


class _SettingsTabs(QTabWidget):
    """Draw the selected tab and pane as one outline with curved joins."""

    def __init__(self) -> None:
        super().__init__()
        self.currentChanged.connect(lambda _index: self.update())

    def paintEvent(self, event) -> None:  # noqa: N802
        if self.currentIndex() < 0:
            return
        option = QStyleOptionTabWidgetFrame()
        self.initStyleOption(option)
        pane = QRectF(self.style().subElementRect(
            QStyle.SubElement.SE_TabWidgetTabPane, option, self
        )).adjusted(0.5, 0.5, -0.5, -0.5)
        bar = self.tabBar()
        tab = QRectF(bar.tabRect(self.currentIndex()))
        tab.translate(bar.x(), bar.y())
        # Keep the stroke inside the widget and exclude the QSS tab spacing.
        tab.adjust(0.5, 0.5, -_TAB_GAP - 0.5, -_TAB_GAP - 0.5)
        radius = float(_CORNER_RADIUS)
        path = QPainterPath()
        path.moveTo(tab.left() + radius, tab.top())
        path.lineTo(tab.right() - radius, tab.top())
        path.quadTo(tab.right(), tab.top(), tab.right(), tab.top() + radius)
        path.lineTo(tab.right(), pane.top() - radius)
        path.quadTo(tab.right(), pane.top(), tab.right() + radius, pane.top())
        path.lineTo(pane.right() - radius, pane.top())
        path.quadTo(pane.right(), pane.top(), pane.right(), pane.top() + radius)
        path.lineTo(pane.right(), pane.bottom() - radius)
        path.quadTo(pane.right(), pane.bottom(), pane.right() - radius, pane.bottom())
        path.lineTo(pane.left() + radius, pane.bottom())
        path.quadTo(pane.left(), pane.bottom(), pane.left(), pane.bottom() - radius)
        if tab.left() > pane.left() + 2 * radius:
            path.lineTo(pane.left(), pane.top() + radius)
            path.quadTo(pane.left(), pane.top(), pane.left() + radius, pane.top())
            path.lineTo(tab.left() - radius, pane.top())
            path.quadTo(tab.left(), pane.top(), tab.left(), pane.top() - radius)
        path.lineTo(tab.left(), tab.top() + radius)
        path.quadTo(tab.left(), tab.top(), tab.left() + radius, tab.top())
        path.closeSubpath()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#333"), 1.0))
        painter.setBrush(QColor("#000"))
        painter.drawPath(path)


def _make_default_label(prefix: str, path: str) -> QLabel:
    """Create a disabled default-path label."""
    lbl = QLabel(f"{prefix} {path}")
    lbl.setProperty("defaultPath", True)
    lbl.setToolTip(tr("default_dir_tooltip"))
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


class SettingsDialog(QDialog):
    volume_changed = pyqtSignal(int)

    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        set_language(str(self._config.get("language", language())))
        self.setWindowTitle(tr("settings"))
        self.setMinimumSize(620, 500)
        self.setStyleSheet(_SETTINGS_QSS)

        layout = QVBoxLayout(self)

        tabs = _SettingsTabs()
        tabs.addTab(self._build_library_tab(), tr("library"))
        tabs.addTab(self._build_playlists_tab(), tr("playlists"))
        tabs.addTab(self._build_general_tab(), tr("general"))
        layout.addWidget(tabs, 1)

        about = QLabel(tr("about"))
        about.setObjectName("settingsAbout")
        about.setWordWrap(True)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        for b in btns.buttons():
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_PRIMARY_BTN_QSS)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 8, 0)
        footer.addWidget(about, 1)
        footer.addWidget(btns, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(footer)

    def _build_library_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)

        v.addWidget(_make_default_label(tr("default_dir"), default_library_dir()))

        v.addWidget(QLabel(tr("other_library_dirs")))
        self.lst_folders = QListWidget()
        for f in self._config.get("library_folders", []) or []:
            self.lst_folders.addItem(f)
        v.addWidget(self.lst_folders, 1)

        row = QHBoxLayout()
        b_add = QPushButton(tr("add_folder"))
        b_remove = QPushButton(tr("remove_selected"))
        for b in (b_add, b_remove):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_BTN_QSS)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        b_add.clicked.connect(self._add_library_folder)
        b_remove.clicked.connect(lambda: self._remove_selected(self.lst_folders))
        return w

    def _add_library_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("choose_library_root"))
        if not folder:
            return
        if self._list_contains(self.lst_folders, folder):
            return
        if os.path.abspath(folder) == os.path.abspath(default_library_dir()):
            return
        self.lst_folders.addItem(folder)

    def _build_playlists_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)

        v.addWidget(_make_default_label(tr("default_dir"), default_playlists_dir()))

        v.addWidget(QLabel(tr("other_playlist_sources")))
        self.lst_playlist_locs = QListWidget()
        for loc in self._config.get("playlist_locations", []) or []:
            self._add_playlist_location_item(loc)
        v.addWidget(self.lst_playlist_locs, 1)

        row = QHBoxLayout()
        b_add_dir = QPushButton(tr("add_folder"))
        b_add_file = QPushButton(tr("add_playlist_file"))
        b_remove = QPushButton(tr("remove_selected"))
        for b in (b_add_dir, b_add_file, b_remove):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_BTN_QSS)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        b_add_dir.clicked.connect(self._add_playlist_folder)
        b_add_file.clicked.connect(self._add_playlist_file)
        b_remove.clicked.connect(lambda: self._remove_selected(self.lst_playlist_locs))

        hint = QLabel(tr("playlist_hint"))
        hint.setWordWrap(True)
        v.addWidget(hint)
        return w

    def _add_playlist_location_item(self, loc: str) -> None:
        if not loc:
            return
        ap = os.path.abspath(loc)
        if ap == os.path.abspath(default_playlists_dir()):
            return
        if self._list_contains(self.lst_playlist_locs, ap, by_data=True):
            return
        it = QListWidgetItem(f"{ap}")
        it.setData(Qt.ItemDataRole.UserRole, ap)
        self.lst_playlist_locs.addItem(it)

    def _add_playlist_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("choose_playlist_folder"))
        if folder:
            self._add_playlist_location_item(folder)

    def _add_playlist_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("choose_playlist_file"), "", "M3U Playlist (*.m3u8 *.m3u)"
        )
        if path:
            self._add_playlist_location_item(path)

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self.combo_language = QComboBox()
        self.combo_language.addItem(tr("language_en"), "en")
        self.combo_language.addItem(tr("language_zh"), "zh")
        current_lang = str(self._config.get("language", "en"))
        idx = self.combo_language.findData(current_lang)
        self.combo_language.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow(tr("language"), self.combo_language)

        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 100)
        self.slider_vol.setValue(int(self._config.get("volume", DEFAULT_VOLUME)))
        self.lbl_vol = QLabel(f"{self.slider_vol.value()}%")
        self.slider_vol.valueChanged.connect(
            lambda val: self.lbl_vol.setText(f"{val}%")
        )
        self.slider_vol.valueChanged.connect(self.volume_changed.emit)
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.slider_vol, 1)
        h.addWidget(self.lbl_vol)
        form.addRow(tr("volume"), wrap)

        self.chk_resume = QCheckBox(tr("auto_resume"))
        self.chk_resume.setChecked(bool(self._config.get("auto_resume", True)))
        form.addRow("", self.chk_resume)

        v.addLayout(form)
        v.addStretch(1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #333;")
        v.addWidget(line)

        btn_reset = QPushButton(tr("factory_reset"))
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.setStyleSheet(
            "QPushButton{background:#1a0505; border:1px solid #5a1a1a;"
            "padding:5px 12px; border-radius:4px; color:#FF6B6B;}"
            "QPushButton:hover{background:#2a0808; border-color:#E63946; color:#FFF;}"
        )
        btn_reset.clicked.connect(self._on_factory_reset)
        v.addWidget(btn_reset)

        return w

    def _on_factory_reset(self) -> None:
        reply = QMessageBox.question(
            self,
            tr("factory_reset_title"),
            tr("factory_reset_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for path in (LIBRARY_CACHE_PATH, QUEUE_CACHE_PATH, QUEUE_ORIGINAL_CACHE_PATH):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except Exception:
                pass

        try:
            if os.path.isdir(THUMB_DIR):
                import shutil

                shutil.rmtree(THUMB_DIR, ignore_errors=True)
        except Exception:
            pass

        for key, value in DEFAULT_CONFIG.items():
            self._config.set(key, value)
        self._config.save()

        self._config.mark_factory_reset()
        QApplication.instance().quit()

    @staticmethod
    def _list_contains(lst: QListWidget, value: str, by_data: bool = False) -> bool:
        target = os.path.abspath(value)
        for i in range(lst.count()):
            it = lst.item(i)
            existing = it.data(Qt.ItemDataRole.UserRole) if by_data else it.text()
            if existing and os.path.abspath(existing) == target:
                return True
        return False

    @staticmethod
    def _remove_selected(lst: QListWidget) -> None:
        for it in lst.selectedItems():
            lst.takeItem(lst.row(it))

    def collected_library_folders(self) -> List[str]:
        return [
            self.lst_folders.item(i).text() for i in range(self.lst_folders.count())
        ]

    def collected_playlist_locations(self) -> List[str]:
        return [
            self.lst_playlist_locs.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.lst_playlist_locs.count())
        ]

    def apply_to_config(self) -> None:
        self._config.set("library_folders", self.collected_library_folders())
        self._config.set("playlist_locations", self.collected_playlist_locations())
        self._config.set("volume", self.slider_vol.value())
        self._config.set("auto_resume", self.chk_resume.isChecked())
        self._config.set("language", self.combo_language.currentData() or "en")
        set_language(str(self._config.get("language", "en")))
        self._config.save()
