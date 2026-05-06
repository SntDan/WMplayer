"""
播放器面板(左半)
================
包含封面 / 进度条 / 标题艺术家专辑 / 三大键 / 模式键 / 底栏。
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from core.metadata import TrackMetadata
from core.playlist import PlayMode, RepeatMode
from .theme import Theme
from .widgets import (
    AlbumCover,
    CircleButton,
    HRBadge,
    IconButton,
    ProgressBar,
    ScrollingLabel,
)


def _format_ms(ms: int) -> str:
    if ms <= 0:
        return "00:00"
    s = ms // 1000
    return f"{s // 60:02d}:{s % 60:02d}"


class ClickableLabel(QLabel):
    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, e):
        super().mouseDoubleClickEvent(e)
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

class PlayerPanel(QWidget):
    # 与外部交互的信号
    play_pause_clicked = pyqtSignal()
    prev_clicked = pyqtSignal()
    next_clicked = pyqtSignal()
    seek_requested = pyqtSignal(int)
    shuffle_toggle_requested = pyqtSignal(bool)        # 用户希望切到的随机状态
    repeat_change_requested = pyqtSignal(RepeatMode)   # 用户希望切到的循环模式
    back_clicked = pyqtSignal()
    open_files_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    library_clicked = pyqtSignal()
    artist_double_clicked = pyqtSignal()
    album_double_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._is_playing = False
        self._shuffled: bool = False
        self._repeat: RepeatMode = RepeatMode.NONE
        self._refresh_mode_buttons()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # 外层垂直: 封面占 stretch=1, 下方所有控件塞进 _below 容器(高度由内容决定)
        self._margin = 24
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self._margin, self._margin, self._margin, self._margin)
        outer.setSpacing(0)

        # ---- 1. 封面 (paint 时按 1:1 居中绘制) ----
        self.cover = AlbumCover(self)
        outer.addWidget(self.cover, 1)

        # ---- 下方区域: 一个独立 QWidget,容易测它的 sizeHint().height() ----
        self._below = QWidget(self)
        below = QVBoxLayout(self._below)
        below.setContentsMargins(0, 0, 0, 0)
        below.setSpacing(8)
        outer.addWidget(self._below, 0)

        # ---- 2. 时间标签行: 与封面左/中/右对齐 ----
        labels_row = QHBoxLayout()
        labels_row.setContentsMargins(0, 4, 0, 0)
        self.lbl_pos = QLabel("00:00", self)
        self.lbl_index = QLabel("0/0", self)
        self.lbl_dur = QLabel("00:00", self)
        f = QFont(); f.setPointSize(11)
        for lbl in (self.lbl_pos, self.lbl_index, self.lbl_dur):
            lbl.setFont(f)
            lbl.setStyleSheet("color: #FFFFFF;")
        self.lbl_pos.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_index.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_dur.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        labels_row.addWidget(self.lbl_pos, 1)
        labels_row.addWidget(self.lbl_index, 1)
        labels_row.addWidget(self.lbl_dur, 1)
        below.addLayout(labels_row)

        # ---- 3. 进度条 ----
        self.progress = ProgressBar(self)
        self.progress.seek_requested.connect(self.seek_requested.emit)
        below.addWidget(self.progress)

        below.addSpacerItem(QSpacerItem(0, 6))

        # ---- 4. 歌曲信息 Song / Artist / Album (全部居中) ----
        # 三个标签都用水平 Ignored 的 size policy: 切歌时无论文字多长
        # 都不会向父布局请求更多宽度,从而避免 splitter 分界线抖动
        info_sp = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        self.lbl_title = ScrollingLabel(self)
        f = QFont(); f.setPointSize(23); f.setBold(True)
        self.lbl_title.setFont(f)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setText("Song")

        self.lbl_artist = ClickableLabel("Artist", self)
        f = QFont(); f.setPointSize(16)
        self.lbl_artist.setFont(f)
        self.lbl_artist.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_artist.setSizePolicy(info_sp)
        self.lbl_artist.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_artist.double_clicked.connect(self.artist_double_clicked.emit)

        self.lbl_album = ClickableLabel("Album", self)
        self.lbl_album.setFont(f)
        self.lbl_album.setStyleSheet("color: #9E9E9E;")
        self.lbl_album.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_album.setSizePolicy(info_sp)
        self.lbl_album.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_album.double_clicked.connect(self.album_double_clicked.emit)

        below.addWidget(self.lbl_title)
        below.addWidget(self.lbl_artist)
        below.addWidget(self.lbl_album)

        below.addSpacerItem(QSpacerItem(0, 6))

        # ---- 5. 库图标单独成行,左对齐;右侧放 HR 徽章 ----
        lib_row = QHBoxLayout()
        lib_row.setContentsMargins(0, 0, 0, 0)
        self.btn_library = IconButton("library", size=32)
        self.btn_library.setToolTip("歌词")
        self.btn_library.set_enabled_visual(False)  # 还没加载歌曲,默认灰
        self.btn_library.clicked.connect(self.library_clicked.emit)
        lib_row.addWidget(self.btn_library)
        lib_row.addStretch(1)
        self.hr_badge = HRBadge(self)
        lib_row.addWidget(self.hr_badge)
        below.addLayout(lib_row)

        # ---- 6. 主控制行: shuffle 最左 | prev | PLAY | next | repeat 最右 ----
        ctrl_row = QHBoxLayout()
        ctrl_row.setContentsMargins(0, 4, 0, 0)
        ctrl_row.setSpacing(0)

        self.btn_shuffle = IconButton("shuffle", size=32)
        self.btn_shuffle.setToolTip("顺序 / 随机")
        self.btn_shuffle.clicked.connect(self._on_shuffle_clicked)

        self.btn_prev = CircleButton("prev", size=52)
        self.btn_prev.clicked.connect(self.prev_clicked.emit)

        self.btn_play = CircleButton("play", size=68)
        self.btn_play.clicked.connect(self.play_pause_clicked.emit)

        self.btn_next = CircleButton("next", size=52)
        self.btn_next.clicked.connect(self.next_clicked.emit)

        self.btn_repeat = IconButton("repeat", size=32)
        self.btn_repeat.setToolTip("循环模式")
        self.btn_repeat.clicked.connect(self._on_repeat_clicked)

        # shuffle 紧贴左边,repeat 紧贴右边,中间三大键自动居中
        ctrl_row.addWidget(self.btn_shuffle, 0, Qt.AlignmentFlag.AlignVCenter)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.btn_prev, 0, Qt.AlignmentFlag.AlignVCenter)
        ctrl_row.addSpacing(10)
        ctrl_row.addWidget(self.btn_play, 0, Qt.AlignmentFlag.AlignVCenter)
        ctrl_row.addSpacing(10)
        ctrl_row.addWidget(self.btn_next, 0, Qt.AlignmentFlag.AlignVCenter)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.btn_repeat, 0, Qt.AlignmentFlag.AlignVCenter)
        below.addLayout(ctrl_row)

        below.addSpacerItem(QSpacerItem(0, 10))

        # ---- 7. 底栏: 返回 / 文件 / 设置, 三等分 ----
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(0)
        self.btn_back = IconButton("back", size=32)
        self.btn_back.setToolTip("返回播放队列")
        self.btn_back.clicked.connect(self.back_clicked.emit)
        self.btn_files = IconButton("folder", size=32)
        self.btn_files.setToolTip("曲库")
        self.btn_files.clicked.connect(self.open_files_clicked.emit)
        self.btn_settings = IconButton("settings", size=32)
        self.btn_settings.setToolTip("设置")
        self.btn_settings.clicked.connect(self.settings_clicked.emit)
        # 三个按钮均匀分布: 左 / 中 / 右
        bottom_row.addWidget(self.btn_back, 0, Qt.AlignmentFlag.AlignLeft)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.btn_files, 0, Qt.AlignmentFlag.AlignCenter)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.btn_settings, 0, Qt.AlignmentFlag.AlignRight)
        below.addLayout(bottom_row)

    # ------------------------------------------------------------------
    # 公开方法 - 由 MainWindow 调用更新视图
    # ------------------------------------------------------------------
    def set_track(self, track: Optional[TrackMetadata], index: int, total: int) -> None:
        if track is None:
            self.lbl_title.setText("Song")
            self.lbl_artist.setText("Artist")
            self.lbl_album.setText("Album")
            self.lbl_index.setText(f"0/{total}")
            self.cover.set_cover(None)
            self.lbl_dur.setText("00:00")
            self.lbl_pos.setText("00:00")
            self.progress.set_position(0)
            self.progress.set_duration(0)
            self.hr_badge.set_visible_hr(False)
            return
        self.lbl_title.setText(track.title)
        self.lbl_artist.setText(track.artist)
        self.lbl_album.setText(track.album)
        self.lbl_index.setText(f"{index + 1}/{total}")
        self.cover.set_cover(track.cover)
        self.lbl_dur.setText(_format_ms(track.duration_ms))
        self.lbl_pos.setText("00:00")
        self.progress.set_position(0)
        self.progress.set_duration(track.duration_ms)
        self.hr_badge.set_visible_hr(track.is_high_res())

    def set_position(self, ms: int) -> None:
        self.progress.set_position(ms)
        self.lbl_pos.setText(_format_ms(ms))

    def set_duration(self, ms: int) -> None:
        self.progress.set_duration(ms)
        self.lbl_dur.setText(_format_ms(ms))

    def set_playing(self, playing: bool) -> None:
        self._is_playing = playing
        self.btn_play.set_icon("pause" if playing else "play")

    def set_shuffled(self, shuffled: bool) -> None:
        self._shuffled = shuffled
        self._refresh_mode_buttons()

    def set_repeat(self, repeat: RepeatMode) -> None:
        self._repeat = repeat
        self._refresh_mode_buttons()

    def set_lyrics_available(self, available: bool) -> None:
        """没有歌词时,左上角的歌词图标变灰。"""
        self.btn_library.set_enabled_visual(available)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _on_shuffle_clicked(self) -> None:
        self.shuffle_toggle_requested.emit(not self._shuffled)

    def _on_repeat_clicked(self) -> None:
        # NONE → ALL → ONE → NONE 循环切换
        order = [RepeatMode.NONE, RepeatMode.ALL, RepeatMode.ONE]
        i = order.index(self._repeat) if self._repeat in order else 0
        new_repeat = order[(i + 1) % len(order)]
        self.repeat_change_requested.emit(new_repeat)

    def _refresh_mode_buttons(self) -> None:
        # active = 启用时的小圆底圈;enabled_visual = 启用白色 / 关闭灰色
        repeat_on = self._repeat in (RepeatMode.ALL, RepeatMode.ONE)
        self.btn_shuffle.set_active(self._shuffled)
        self.btn_shuffle.set_enabled_visual(self._shuffled)
        self.btn_repeat.set_active(repeat_on)
        self.btn_repeat.set_enabled_visual(repeat_on)
        self.btn_repeat.set_icon("repeat_one" if self._repeat == RepeatMode.ONE else "repeat")

    # ------------------------------------------------------------------
    # 几何锁定
    # ------------------------------------------------------------------
    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._lock_width_to_height()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._lock_width_to_height()

    def _lock_width_to_height(self) -> None:
        """根据当前高度反推面板理想宽度,使封面四边到面板边距相等。

        几何关系(M = self._margin):
            封面宽 = 封面高
            封面宽 = 面板宽 - 2M
            封面高 = 面板高 - 2M - 下方控件高
        所以  面板宽 = 面板高 - 下方控件高
        """
        h = self.height()
        if h <= 0:
            return
        below_h = self._below.sizeHint().height()
        # 面板理想宽 = 高 - 下方控件高(不含上下边距,边距已经在两侧对称分布)
        ideal_w = h - below_h

        # 防挤压限制：如果主窗体被手动调窄，为了避免面板内容被截断或者右侧视图被挤消失，需强制退让。
        win = self.window()
        if win and win.width() > 0:
            max_w = win.width() - 360
            if max_w > 0:
                ideal_w = min(ideal_w, max_w)

        # 给个最小宽度防止极端窗口
        ideal_w = max(280, ideal_w)
        if self.maximumWidth() != ideal_w or self.minimumWidth() != ideal_w:
            self.setFixedWidth(ideal_w)
