"""
主窗口
======
把音频引擎 / 曲库 / 歌单 / 播放队列 / UI 全部连起来。

右侧三视图(QStackedWidget)切换:
  0  曲库 (LibraryPanel)
  1  播放队列 (QueuePanel)
  2  歌单 (PlaylistsPanel)
顶部 segmented control 与左下三个红色图标(书 / 返回 / 文件夹)同步切换。
"""

from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import (
    QByteArray,
    QObject,
    QSize,
    QRunnable,
    Qt,
    QThreadPool,
    pyqtSignal,
)
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.audio_engine import AudioEngine
from core.config import (
    Config,
    LIBRARY_CACHE_PATH,
    QUEUE_CACHE_PATH,
    QUEUE_ORIGINAL_CACHE_PATH,
    default_playlists_dir,
)
from core.library import Library
from core.metadata import read_metadata
from core.playlist import PlayMode, Playlist, RepeatMode
from core.playlist_store import PlaylistStore
from core import m3u
from core import lrc as lrc_mod

from .albums_panel import AlbumsPanel
from .artists_panel import ArtistsPanel
from .library_panel import LibraryPanel
from .lyrics_panel import LyricsPanel
from .player_panel import PlayerPanel
from .playlists_panel import PlaylistsPanel
from .queue_panel import QueuePanel
from .settings_dialog import SettingsDialog
from .theme import GLOBAL_QSS


# ----------------------------------------------------------------------
# 后台读封面任务
# ----------------------------------------------------------------------
class _CoverSignals(QObject):
    done = pyqtSignal(str, object)  # (path, bytes_or_None)


class _CoverFetcher(QRunnable):
    def __init__(self, path: str, signals: _CoverSignals) -> None:
        super().__init__()
        self._path = path
        self._signals = signals

    def run(self) -> None:
        cover = None
        try:
            md = read_metadata(self._path, with_cover=True)
            cover = md.cover if md else None
        except Exception:
            cover = None
        try:
            self._signals.done.emit(self._path, cover)
        except Exception:
            pass


# ----------------------------------------------------------------------
# 右侧 segmented control
# ----------------------------------------------------------------------
class _Segmented(QWidget):
    """四段切换:曲库 / 队列 / 歌单 / 歌词。"""

    changed = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(20, 14, 20, 0)
        h.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        labels = ["曲库", "专辑", "歌手", "播放队列", "歌单", "歌词"]
        for i, label in enumerate(labels):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_SEG_QSS)
            self._group.addButton(b, i)
            h.addWidget(b)
        h.addStretch(1)
        self._group.idClicked.connect(self.changed.emit)
        self.set_index(3)  # 默认 队列

    def set_index(self, idx: int) -> None:
        btn = self._group.button(idx)
        if btn is not None:
            btn.setChecked(True)


_SEG_QSS = """
QPushButton {
    background: transparent;
    color: #999;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover { color: #FFF; }
QPushButton:checked {
    color: #FFF;
    border-bottom: 2px solid #E63946;
}
"""


# ----------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):

    VIEW_LIBRARY = 0
    VIEW_ALBUMS = 1
    VIEW_ARTISTS = 2
    VIEW_QUEUE = 3
    VIEW_PLAYLISTS = 4
    VIEW_LYRICS = 5

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Music Player")
        self.setMinimumSize(QSize(720, 760))
        self.resize(QSize(920, 760))
        self.setStyleSheet(GLOBAL_QSS)

        # ------- 数据模型 -------
        self._config = Config()
        self._engine = AudioEngine(self)
        self._playlist = Playlist(self)              # 当前播放队列
        self._library = Library(LIBRARY_CACHE_PATH, self)
        self._library.set_folders(self._config.library_folders_effective())
        self._store = PlaylistStore(default_playlists_dir(), self)
        self._store.set_locations(self._config.playlist_locations_effective())

        self._pool = QThreadPool.globalInstance()
        self._cover_signals = _CoverSignals(self)
        self._cover_signals.done.connect(self._on_cover_loaded)

        self._autoplay_after_load = True

        # ------- UI -------
        self._build_ui()
        self._wire()
        self._restore_state()

    # ==================================================================
    # UI 构建
    # ==================================================================
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左:播放器(宽度由它自己锁定,跟随窗口高度)
        self.player_panel = PlayerPanel()

        # 中间分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setStyleSheet("background-color: #FFFFFF; border: none;")
        sep.setFixedWidth(1)

        # 右:segmented + stacked
        right = QWidget()
        self.right_panel = right
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        self.segmented = _Segmented()
        rv.addWidget(self.segmented)

        self.stack = QStackedWidget()
        self.library_panel = LibraryPanel(self._library)
        self.albums_panel = AlbumsPanel(self._library)
        self.artists_panel = ArtistsPanel(self._library)
        self.queue_panel = QueuePanel(self._playlist)
        self.playlists_panel = PlaylistsPanel(self._store)
        self.lyrics_panel = LyricsPanel()
        self.stack.addWidget(self.library_panel)      # 0
        self.stack.addWidget(self.albums_panel)       # 1
        self.stack.addWidget(self.artists_panel)      # 2
        self.stack.addWidget(self.queue_panel)         # 3
        self.stack.addWidget(self.playlists_panel)    # 4
        self.stack.addWidget(self.lyrics_panel)        # 5
        self.stack.setCurrentIndex(self.VIEW_QUEUE)
        rv.addWidget(self.stack, 1)

        layout.addWidget(self.player_panel, 0)   # 不 stretch,宽度自锁
        layout.addWidget(sep, 0)
        layout.addWidget(right, 1)               # 最小宽度 = 左侧,多余宽度全部吃掉

    def _wire(self) -> None:
        # 顶部 segmented ↔ stack
        self.segmented.changed.connect(self._switch_view)

        # 左侧播放面板
        pp = self.player_panel
        pp.play_pause_clicked.connect(self._toggle_play)
        pp.prev_clicked.connect(self._play_prev)
        pp.next_clicked.connect(self._play_next)
        pp.seek_requested.connect(self._engine.seek)
        pp.shuffle_toggle_requested.connect(self._playlist.set_shuffled)
        pp.repeat_change_requested.connect(self._playlist.set_repeat)
        pp.back_clicked.connect(lambda: self._switch_view(self.VIEW_QUEUE))
        pp.library_clicked.connect(lambda: self._switch_view(self.VIEW_LYRICS))
        pp.open_files_clicked.connect(lambda: self._switch_view(self.VIEW_LIBRARY))
        pp.settings_clicked.connect(self._on_settings)
        pp.artist_double_clicked.connect(self._on_player_artist_double_clicked)
        pp.album_double_clicked.connect(self._on_player_album_double_clicked)
        pp.width_locked.connect(self._on_player_width_locked)

        # 引擎事件
        self._engine.position_changed.connect(self.player_panel.set_position)
        self._engine.position_changed.connect(self.lyrics_panel.update_position)
        self._engine.duration_changed.connect(self._on_duration_changed)
        self._engine.state_changed.connect(self._on_state_changed)
        self._engine.track_finished.connect(self._on_track_finished)
        self._engine.error_occurred.connect(
            lambda msg: self.statusBar().showMessage(f"⚠ {msg}", 4000)
        )

        # 队列模型
        self._playlist.current_changed.connect(self._on_current_changed)
        self._playlist.changed.connect(self._on_playlist_changed)
        self._playlist.shuffled_changed.connect(self.player_panel.set_shuffled)
        self._playlist.repeat_changed.connect(self.player_panel.set_repeat)

        # 队列视图
        self.queue_panel.track_double_clicked.connect(self._play_index)
        self.queue_panel.remove_requested.connect(self._on_remove_track)
        self.queue_panel.clear_requested.connect(self._on_clear_queue)
        self.queue_panel.save_as_playlist_requested.connect(self._on_save_queue_as_playlist)

        # 曲库视图
        self.library_panel.play_paths_now.connect(self._play_paths_now)
        self.library_panel.enqueue_paths.connect(self._enqueue_paths)
        self.library_panel.add_paths_to_playlist.connect(self._add_paths_to_some_playlist)
        self.library_panel.rescan_requested.connect(self._rescan_library)

        # 专辑视图
        self.albums_panel.play_paths_now.connect(self._play_paths_now)
        self.albums_panel.enqueue_paths.connect(self._enqueue_paths)
        self.albums_panel.add_paths_to_playlist.connect(self._add_paths_to_some_playlist)

        # 歌手视图
        self.artists_panel.play_paths_now.connect(self._play_paths_now)
        self.artists_panel.enqueue_paths.connect(self._enqueue_paths)
        self.artists_panel.add_paths_to_playlist.connect(self._add_paths_to_some_playlist)

        # 歌单视图
        self.playlists_panel.open_playlist.connect(self._on_open_playlist)
        self.playlists_panel.new_empty_playlist.connect(self._on_new_empty_playlist)
        self.playlists_panel.rename_playlist.connect(self._on_rename_playlist)
        self.playlists_panel.delete_playlist.connect(self._on_delete_playlist)

        # 歌词视图:双击行 → 跳转
        self.lyrics_panel.seek_to_ms.connect(self._engine.seek)

        # 全局快捷键
        def _sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self); s.activated.connect(fn); return s

        _sc("Space", self._toggle_play)
        _sc(Qt.Key.Key_MediaPlay, self._toggle_play)
        _sc(Qt.Key.Key_MediaNext, self._play_next)
        _sc(Qt.Key.Key_MediaPrevious, self._play_prev)
        _sc("Right", lambda: self._engine.seek(self._engine.get_position() + 5000))
        _sc("Left", lambda: self._engine.seek(self._engine.get_position() - 5000))
        _sc("Up", lambda: self._engine.set_volume(min(100, self._engine.get_volume() + 5)))
        _sc("Down", lambda: self._engine.set_volume(max(0, self._engine.get_volume() - 5)))

    def _on_player_width_locked(self, w: int) -> None:
        # 右侧最小宽度 = 左侧, 但允许更宽 (用户向右拖右边界时, 右侧吃掉所有多余空间)。
        # 同时把窗口的最小宽度锁成 (左 + 1px 分隔线 + 右), 不允许再缩。
        # 只在当前窗口比这个最小值还窄时才主动放大,
        # 用户已经拖大的尺寸保留, 避免拖动时窗口"反弹"乱闪。
        self.right_panel.setMinimumWidth(w)
        self.right_panel.setMaximumWidth(16777215)
        target = w + 1 + w
        self.setMinimumWidth(target)
        if self.width() < target:
            self.resize(target, self.height())

    def _on_player_artist_double_clicked(self) -> None:
        track = self._playlist.current
        if track and track.artist:
            self._switch_view(self.VIEW_ARTISTS)
            self.artists_panel.show_artist(track.artist)

    def _on_player_album_double_clicked(self) -> None:
        track = self._playlist.current
        if track and track.album:
            self._switch_view(self.VIEW_ALBUMS)
            self.albums_panel.show_album(track.album)

    def _switch_view(self, idx: int) -> None:
        self.segmented.set_index(idx)
        self.stack.setCurrentIndex(idx)
        
        # 返回初始页面状态
        if idx == self.VIEW_ALBUMS:
            self.albums_panel.stack.setCurrentIndex(0)
        elif idx == self.VIEW_ARTISTS:
            self.artists_panel.stack.setCurrentIndex(0)

    # ==================================================================
    # 启动 / 关闭
    # ==================================================================
    def _restore_state(self) -> None:
        # 音量、模式
        self._engine.set_volume(int(self._config.get("volume", 80)))
        # 优先用新版双字段; 缺失时从旧的 play_mode 转换
        if self._config.has("shuffled") or self._config.has("repeat"):
            try:
                self._playlist.set_repeat(RepeatMode(self._config.get("repeat", "none")))
            except Exception:
                self._playlist.set_repeat(RepeatMode.NONE)
            self._playlist.set_shuffled(bool(self._config.get("shuffled", False)))
        else:
            try:
                self._playlist.set_mode(PlayMode(self._config.get("play_mode", "sequential")))
            except Exception:
                self._playlist.set_mode(PlayMode.SEQUENTIAL)

        # 还原"上次播放队列"——保存在 queue.m3u8 和 queue_original.m3u8
        if os.path.isfile(QUEUE_CACHE_PATH):
            paths = m3u.parse_file(QUEUE_CACHE_PATH)
            original_paths: Optional[List[str]] = None
            if os.path.isfile(QUEUE_ORIGINAL_CACHE_PATH):
                original_paths = m3u.parse_file(QUEUE_ORIGINAL_CACHE_PATH)

            if paths:
                # 优先用 library 缓存命中,只对未命中的路径回退到 read_metadata
                tracks = self._tracks_from_paths(paths)
                orig_tracks = self._tracks_from_paths(original_paths) if original_paths else None
                self._playlist.restore_with_tracks(tracks, orig_tracks)
                # 还原当前曲目
                last = self._config.get("last_track_path", "")
                if last:
                    idx = self._playlist.find_index_by_path(last)
                    if idx >= 0:
                        self._autoplay_after_load = False
                        self._playlist.set_current(idx)
                        if self._config.get("auto_resume", True):
                            pos = int(self._config.get("last_position_ms", 0))
                            if pos > 0:
                                self._engine.seek(pos)

        # 启动时若曲库为空,且有可扫描根目录 → 自动扫一次
        if len(self._library) == 0 and self._library.folders:
            self._library.scan_async()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "player_panel"):
            self.player_panel._lock_width_to_height()

    def closeEvent(self, e):  # noqa: N802
        if not self._config.factory_reset_pending:
            try:
                self._config.set("volume", self._engine.get_volume())
                # 新版双字段(主)
                self._config.set("shuffled", self._playlist.shuffled)
                self._config.set("repeat", self._playlist.repeat.value)
                # 旧字段保留,这样降级也能凑合识别(可能损失 shuffled+repeat 同开的信息)
                self._config.set("play_mode", self._playlist.mode.value)
                self._config.set("last_position_ms", self._engine.get_position())
                cur = self._playlist.current
                self._config.set("last_track_path", cur.path if cur else "")
                self._config.save()
                # 保存当前队列为隐藏的 queue.m3u8
                m3u.write_file(QUEUE_CACHE_PATH, "queue", self._playlist.paths)
                # 保存由于随机播放之前的原始队列 (存在的话) 为 queue_original.m3u8
                orig_paths = self._playlist.original_paths
                if orig_paths is not None:
                    m3u.write_file(QUEUE_ORIGINAL_CACHE_PATH, "queue_original", orig_paths)
                elif os.path.isfile(QUEUE_ORIGINAL_CACHE_PATH):
                    os.remove(QUEUE_ORIGINAL_CACHE_PATH)
            except Exception:
                pass
        try:
            self._engine.release()
        except Exception:
            pass
        super().closeEvent(e)

    # ==================================================================
    # 播放控制
    # ==================================================================
    def _toggle_play(self) -> None:
        if self._playlist.current_index < 0:
            if len(self._playlist) > 0:
                self._play_index(0)
            return
        if self._engine.is_playing():
            self._engine.pause()
        else:
            self._engine.play()

    def _play_index(self, index: int) -> None:
        self._autoplay_after_load = True
        self._playlist.set_current(index)

    def _play_next(self) -> None:
        nxt = self._playlist.next_index(auto=False)
        if nxt is not None:
            self._play_index(nxt)

    def _play_prev(self) -> None:
        if self._engine.get_position() > 3000:
            self._engine.seek(0)
            return
        prv = self._playlist.prev_index()
        if prv is not None:
            self._play_index(prv)

    def _on_track_finished(self) -> None:
        nxt = self._playlist.next_index(auto=True)
        if nxt is None:
            self._engine.stop()
            self.player_panel.set_playing(False)
            return
        self._play_index(nxt)

    def _on_current_changed(self, index: int) -> None:
        track = self._playlist.get(index)
        if track is None:
            return
        self.player_panel.set_track(track, index, len(self._playlist))
        if self._engine.load(track.path) and self._autoplay_after_load:
            self._engine.play()
        self._fetch_cover_async(track.path)
        self._load_lyrics_for(track.path)

    def _on_playlist_changed(self) -> None:
        """队列结构变化(洗牌、恢复原顺序、删除其它项等)时调用。

        只刷新左侧的"编号 / 总数"显示和进度条总长,绝不重新加载播放。
        """
        cur = self._playlist.current
        idx = self._playlist.current_index
        total = len(self._playlist)
        if cur is None or idx < 0:
            # 队列空或当前无选中:不动播放器面板
            return
        # 复用 set_track,但因为播放/封面/歌词都没变,这里只更新文字和编号即可。
        # set_track 内部会重置进度条和位置 → 不能用,我们自己写最小更新。
        self.player_panel.lbl_index.setText(f"{idx + 1}/{total}")

    def _load_lyrics_for(self, audio_path: str) -> None:
        """根据音频路径找同名 .lrc,加载到歌词面板。"""
        lrc_path = lrc_mod.find_lrc_for(audio_path)
        lyr = lrc_mod.parse_file(lrc_path) if lrc_path else None
        cur = self._playlist.current
        label = ""
        if cur is not None:
            label = f"{cur.title} — {cur.artist}"
        self.lyrics_panel.set_lyrics(lyr, track_label=label)
        # 更新左上角"歌词"按钮的灰/白状态
        self.player_panel.set_lyrics_available(self.lyrics_panel.has_lyrics())

    def _on_duration_changed(self, ms: int) -> None:
        self.player_panel.set_duration(ms)
        track = self._playlist.current
        if track is not None and ms > 0:
            track.duration_ms = ms

    def _on_state_changed(self, state: str) -> None:
        self.player_panel.set_playing(state == "playing")

    # ==================================================================
    # 封面后台读取
    # ==================================================================
    def _fetch_cover_async(self, path: str) -> None:
        cur = self._playlist.current
        if cur and cur.path == path and cur.cover:
            self.player_panel.cover.set_cover(cur.cover)
            return
        self._pool.start(_CoverFetcher(path, self._cover_signals))

    def _on_cover_loaded(self, path: str, cover) -> None:
        cur = self._playlist.current
        if cur is None or cur.path != path:
            return
        if cover:
            cur.cover = cover
            self.player_panel.cover.set_cover(cover)

    # ==================================================================
    # 队列操作
    # ==================================================================
    def _on_remove_track(self, index: int) -> None:
        was_current = (index == self._playlist.current_index)
        self._playlist.remove(index)
        if was_current:
            # 队列还有曲目就自动播下一首(原 index 位置变成下一首),否则停止
            if len(self._playlist) > 0:
                next_idx = min(index, len(self._playlist) - 1)
                self._play_index(next_idx)
            else:
                self._engine.stop()
                self.player_panel.set_track(None, -1, 0)
                self.lyrics_panel.set_lyrics(None)
                self.player_panel.set_lyrics_available(False)

    def _on_clear_queue(self) -> None:
        if len(self._playlist) == 0:
            return
        ans = QMessageBox.question(self, "清空队列", "确定要清空播放队列吗?")
        if ans == QMessageBox.StandardButton.Yes:
            self._engine.stop()
            self._playlist.clear()
            self.player_panel.set_track(None, -1, 0)
            self.lyrics_panel.set_lyrics(None)
            self.player_panel.set_lyrics_available(False)

    def _on_save_queue_as_playlist(self, name: str) -> None:
        if not name:
            return
        ok = self._store.save(name, self._playlist.paths)
        if ok:
            self.statusBar().showMessage(f"已保存歌单 “{name}”", 3000)
        else:
            QMessageBox.warning(self, "保存失败", "无法写入歌单文件,请检查歌单目录权限。")

    # ==================================================================
    # 曲库操作
    # ==================================================================
    def _tracks_from_paths(self, paths):
        """优先命中曲库缓存;未命中再用 read_metadata 兜底,避免大量同步读盘。"""
        tracks = []
        for p in paths:
            if not p:
                continue
            t = self._library.find_by_path(p)
            if t:
                tracks.append(t)
            else:
                try:
                    tracks.append(read_metadata(p, with_cover=False))
                except Exception:
                    pass
        return tracks

    def _play_paths_now(self, paths: List[str], start_index: int = 0) -> None:
        if not paths:
            return
        tracks = self._tracks_from_paths(paths)
        new_start_index = self._playlist.replace_with_tracks(tracks, start_index)
        if len(self._playlist) > 0:
            self._play_index(new_start_index)

    def _enqueue_paths(self, paths: List[str]) -> None:
        if not paths:
            return
        tracks = self._tracks_from_paths(paths)
        n = self._playlist.append_tracks(tracks)
        self.statusBar().showMessage(f"已加入 {n} 首到队列", 3000)

    def _add_paths_to_some_playlist(self, paths: List[str]) -> None:
        if not paths:
            return
        names = self._store.list_names()
        if not names:
            # 没有歌单,直接新建一个
            name, ok = QInputDialog.getText(self, "新建歌单", "歌单名称:")
            if not (ok and name.strip()):
                return
            self._store.save(name.strip(), paths)
            self.statusBar().showMessage(f"已创建歌单 “{name.strip()}” 并加入 {len(paths)} 首", 3000)
            return
        # 让用户选一个现有歌单 或 新建
        names_with_new = ["<新建歌单>"] + names
        choice, ok = QInputDialog.getItem(
            self, "加入歌单", "选择目标歌单:", names_with_new, 0, False
        )
        if not ok:
            return
        if choice == "<新建歌单>":
            name, ok = QInputDialog.getText(self, "新建歌单", "歌单名称:")
            if not (ok and name.strip()):
                return
            self._store.save(name.strip(), paths)
        else:
            existing = self._store.load(choice)
            seen = set(existing)
            for p in paths:
                if p not in seen:
                    existing.append(p)
                    seen.add(p)
            self._store.save(choice, existing)
            self.statusBar().showMessage(
                f"已加入 {len(paths)} 首到歌单 “{choice}”", 3000
            )

    def _rescan_library(self) -> None:
        self._library.set_folders(self._config.library_folders_effective())
        self._library.scan_async()

    # ==================================================================
    # 歌单操作
    # ==================================================================
    def _on_open_playlist(self, name: str) -> None:
        paths = self._store.load(name)
        if not paths:
            QMessageBox.information(self, "歌单为空", f"歌单 “{name}” 是空的。")
            return
        self._playlist.replace_with_paths(paths)
        self._config.set("last_playlist_name", name)
        self._switch_view(self.VIEW_QUEUE)
        if len(self._playlist) > 0:
            self._play_index(0)

    def _on_new_empty_playlist(self, name: str) -> None:
        if self._store.save(name, []):
            self.statusBar().showMessage(f"已创建歌单 “{name}”", 3000)

    def _on_rename_playlist(self, old: str, new: str) -> None:
        if not self._store.is_writable(old):
            QMessageBox.information(
                self, "无法重命名", "该歌单来自附加源,只读。请把它复制到默认目录后再重命名。"
            )
            return
        if not self._store.rename(old, new):
            QMessageBox.warning(self, "重命名失败", "新名称可能已存在,或文件无法重命名。")

    def _on_delete_playlist(self, name: str) -> None:
        if not self._store.is_writable(name):
            QMessageBox.information(
                self, "无法删除", "该歌单来自附加源,只读。请到对应位置手动删除。"
            )
            return
        self._store.delete(name)

    # ==================================================================
    # 设置
    # ==================================================================
    def _on_settings(self) -> None:
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            dlg.apply_to_config()
            # 把变更应用到运行中的对象
            self._engine.set_volume(int(self._config.get("volume", 80)))
            self._library.set_folders(self._config.library_folders_effective())
            self._store.set_locations(self._config.playlist_locations_effective())
            # 应用后自动重扫
            self._library.scan_async()
