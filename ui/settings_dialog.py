"""
设置对话框
==========
- 曲库文件夹列表(增/删)
- 是否包含程序内置 library/ 子目录
- 歌单存储目录
- 音量、自动恢复
"""

from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
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
from ui.theme import BTN_QSS as _BTN_QSS


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("设置")
        self.setMinimumSize(560, 460)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_library_tab(), "曲库")
        tabs.addTab(self._build_playlists_tab(), "歌单")
        tabs.addTab(self._build_general_tab(), "通用")
        layout.addWidget(tabs, 1)

        # 关于
        about = QLabel(
            "<div style='color:#9E9E9E;font-size:11px;'>"
            "音频内核: libVLC &nbsp;·&nbsp; UI: PyQt6<br>"
            "支持: MP3 / FLAC / WAV / ALAC / APE / OGG / Opus / DSD …"
            "</div>"
        )
        about.setWordWrap(True)
        layout.addWidget(about)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # ------------------------------------------------------------------
    # 曲库 tab
    # ------------------------------------------------------------------
    def _build_library_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        v.addWidget(QLabel("曲库根目录(扫描以下文件夹下的所有音频):"))

        self.lst_folders = QListWidget()
        self.lst_folders.setStyleSheet(
            "QListWidget{border:1px solid #333; background:#0a0a0a;}"
        )
        for f in self._config.get("library_folders", []) or []:
            self.lst_folders.addItem(f)
        v.addWidget(self.lst_folders, 1)

        row = QHBoxLayout()
        b_add = QPushButton("+ 添加文件夹")
        b_remove = QPushButton("移除选中")
        for b in (b_add, b_remove):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_BTN_QSS)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        b_add.clicked.connect(self._add_folder)
        b_remove.clicked.connect(self._remove_folder)

        self.chk_default_lib = QCheckBox(
            f"同时扫描程序自带目录 ({default_library_dir()})"
        )
        self.chk_default_lib.setChecked(
            bool(self._config.get("include_default_library", True))
        )
        v.addWidget(self.chk_default_lib)

        return w

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择曲库根目录")
        if folder:
            # 去重
            for i in range(self.lst_folders.count()):
                if self.lst_folders.item(i).text() == folder:
                    return
            self.lst_folders.addItem(folder)

    def _remove_folder(self) -> None:
        for it in self.lst_folders.selectedItems():
            self.lst_folders.takeItem(self.lst_folders.row(it))

    # ------------------------------------------------------------------
    # 歌单 tab
    # ------------------------------------------------------------------
    def _build_playlists_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        v.addWidget(QLabel("歌单(.m3u8)存储目录:"))
        row = QHBoxLayout()
        self.edt_playlists = QLineEdit(
            self._config.get("playlists_dir", default_playlists_dir())
        )
        b_browse = QPushButton("浏览…")
        b_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        b_browse.setStyleSheet(_BTN_QSS)
        b_browse.clicked.connect(self._browse_playlists_dir)
        row.addWidget(self.edt_playlists, 1)
        row.addWidget(b_browse)
        v.addLayout(row)

        hint = QLabel(
            "<div style='color:#888;font-size:11px;'>"
            "默认为程序根目录下的 <code>playlists/</code> 子文件夹。<br>"
            "歌单格式: 标准 M3U8 (UTF-8),首行 #EXTM3U,可直接和其他播放器互通。"
            "</div>"
        )
        hint.setWordWrap(True)
        v.addWidget(hint)
        v.addStretch(1)
        return w

    def _browse_playlists_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择歌单存储目录", self.edt_playlists.text()
        )
        if folder:
            self.edt_playlists.setText(folder)

    # ------------------------------------------------------------------
    # 通用 tab
    # ------------------------------------------------------------------
    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setSpacing(10)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

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
        form.addRow("音量", wrap)

        self.chk_resume = QCheckBox("启动时恢复上次播放进度")
        self.chk_resume.setChecked(bool(self._config.get("auto_resume", True)))
        form.addRow("", self.chk_resume)

        v.addLayout(form)
        v.addStretch(1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #333;")
        v.addWidget(line)

        btn_reset = QPushButton("恢复出厂设置…")
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
            self, "恢复出厂设置",
            "将清除所有缓存(曲库索引、播放队列)并恢复默认设置，然后自动关闭程序。\n此操作不可撤销，是否继续？",
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
    # 收尾
    # ------------------------------------------------------------------
    def collected_library_folders(self) -> List[str]:
        return [self.lst_folders.item(i).text() for i in range(self.lst_folders.count())]

    def apply_to_config(self) -> None:
        self._config.set("library_folders", self.collected_library_folders())
        self._config.set("include_default_library", self.chk_default_lib.isChecked())
        self._config.set("playlists_dir",
                         self.edt_playlists.text().strip() or default_playlists_dir())
        self._config.set("volume", self.slider_vol.value())
        self._config.set("auto_resume", self.chk_resume.isChecked())
        self._config.save()
