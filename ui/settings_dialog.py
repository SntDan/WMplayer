"""
设置对话框
==========
- 曲库:默认目录(只读、置顶) + 用户自定义文件夹
- 歌单:默认目录(只读、置顶) + 用户自定义文件夹/单独 .m3u8 文件
- 通用: 音量、自动恢复、恢复出厂
"""

from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import Qt
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.config import (
    Config, DEFAULT_CONFIG,
    LIBRARY_CACHE_PATH, QUEUE_CACHE_PATH, QUEUE_ORIGINAL_CACHE_PATH,
    default_library_dir, default_playlists_dir,
)
from core.thumbnails import THUMB_DIR
from ui.i18n import language, set_language, tr
from ui.theme import BTN_QSS as _BTN_QSS, PRIMARY_BTN_QSS as _PRIMARY_BTN_QSS


_LOCKED_DEFAULT_QSS = (
    "QLabel{background:#0a0a0a; border:1px solid #222; border-radius:3px;"
    "padding:6px 10px; color:#777;}"
)


def _make_default_label(prefix: str, path: str) -> QLabel:
    """构造一个灰色、不可改的"默认目录"提示行。"""
    lbl = QLabel(f"{prefix} {path}")
    lbl.setStyleSheet(_LOCKED_DEFAULT_QSS)
    lbl.setToolTip(tr("default_dir_tooltip"))
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lbl


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        set_language(str(self._config.get("language", language())))
        self.setWindowTitle(tr("settings"))
        self.setMinimumSize(620, 500)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_library_tab(), tr("library"))
        tabs.addTab(self._build_playlists_tab(), tr("playlists"))
        tabs.addTab(self._build_general_tab(), tr("general"))
        layout.addWidget(tabs, 1)

        # 关于
        about = QLabel(
            tr("about")
        )
        about.setWordWrap(True)
        layout.addWidget(about)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        # 把 OK / Cancel 做成跟右侧页"返回"按钮一致的红色主操作按钮形状
        for b in btns.buttons():
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_PRIMARY_BTN_QSS)
        layout.addWidget(btns)

    # ------------------------------------------------------------------
    # 曲库 tab
    # ------------------------------------------------------------------
    def _build_library_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)

        # 默认目录(置顶、灰色、不可改)
        v.addWidget(_make_default_label(tr("default_dir"), default_library_dir()))

        v.addWidget(QLabel(tr("other_library_dirs")))
        self.lst_folders = QListWidget()
        self.lst_folders.setStyleSheet(
            "QListWidget{border:1px solid #333; background:#0a0a0a;}"
        )
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
        # 默认目录已经隐式包含了
        if os.path.abspath(folder) == os.path.abspath(default_library_dir()):
            return
        self.lst_folders.addItem(folder)

    # ------------------------------------------------------------------
    # 歌单 tab
    # ------------------------------------------------------------------
    def _build_playlists_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(8)

        v.addWidget(_make_default_label(tr("default_dir"), default_playlists_dir()))

        v.addWidget(QLabel(tr("other_playlist_sources")))
        self.lst_playlist_locs = QListWidget()
        self.lst_playlist_locs.setStyleSheet(
            "QListWidget{border:1px solid #333; background:#0a0a0a;}"
        )
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

        hint = QLabel(
            tr("playlist_hint")
        )
        hint.setWordWrap(True)
        v.addWidget(hint)
        return w

    def _add_playlist_location_item(self, loc: str) -> None:
        if not loc:
            return
        ap = os.path.abspath(loc)
        if ap == os.path.abspath(default_playlists_dir()):
            return  # 默认目录隐式包含
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

    # ------------------------------------------------------------------
    # 通用 tab
    # ------------------------------------------------------------------
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
        self.slider_vol.setValue(int(self._config.get("volume", 80)))
        self.lbl_vol = QLabel(f"{self.slider_vol.value()}%")
        self.slider_vol.valueChanged.connect(
            lambda val: self.lbl_vol.setText(f"{val}%")
        )
        wrap = QWidget()
        h = QHBoxLayout(wrap); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.slider_vol, 1); h.addWidget(self.lbl_vol)
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
            self, tr("factory_reset_title"),
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

        # 清空整个缩略图目录
        try:
            if os.path.isdir(THUMB_DIR):
                import shutil
                shutil.rmtree(THUMB_DIR, ignore_errors=True)
        except Exception:
            pass

        for key, value in DEFAULT_CONFIG.items():
            self._config.set(key, value)
        self._config.save()

        # 告知 closeEvent 跳过状态保存，避免队列文件被重新写入
        self._config.mark_factory_reset()
        QApplication.instance().quit()

    # ------------------------------------------------------------------
    # 通用列表辅助
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 收尾
    # ------------------------------------------------------------------
    def collected_library_folders(self) -> List[str]:
        return [self.lst_folders.item(i).text() for i in range(self.lst_folders.count())]

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
