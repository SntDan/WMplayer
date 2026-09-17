"""Main application window and signal wiring."""

from __future__ import annotations

import os
import time
from typing import List, Optional

from PyQt6.QtCore import (
    QEvent,
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    qWarning,
    pyqtSignal,
)
from PyQt6.QtGui import QGuiApplication, QKeySequence, QShortcut
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

from core import lrc as lrc_mod
from core import m3u
from core.audio_engine import AudioEngine
from core.config import (
    LIBRARY_CACHE_PATH,
    QUEUE_CACHE_PATH,
    QUEUE_ORIGINAL_CACHE_PATH,
    Config,
    default_playlists_dir,
)
from core.library import Library
from core.metadata import read_metadata
from core.playlist import Playlist, PlayMode, RepeatMode
from core.playlist_store import PlaylistStore

from .albums_panel import AlbumsPanel
from .artists_panel import ArtistsPanel
from .i18n import set_language, tr
from .library_panel import LibraryPanel
from .lyrics_panel import LyricsPanel
from .player_panel import PlayerPanel
from .playlists_panel import PlaylistsPanel
from .queue_panel import QueuePanel
from .settings_dialog import SettingsDialog
from .theme import GLOBAL_QSS


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


class _MediaKeyHook(QObject):
    command = pyqtSignal(int)

    _WH_KEYBOARD_LL = 13
    _WM_KEYDOWN = 0x0100
    _WM_SYSKEYDOWN = 0x0104
    _VK_TO_COMMAND = {
        0xB0: 11,  # next track
        0xB1: 12,  # previous track
        0xB2: 13,  # stop
        0xB3: 14,  # play/pause
        0xFA: 46,  # play
    }

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._hook = None
        self._callback = None
        if os.name == "nt":
            self._install()

    def close(self) -> None:
        if not self._hook:
            return
        try:
            import ctypes

            ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
        except Exception:
            pass
        self._hook = None

    def _install(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p),
                ]

            hook_proc = ctypes.WINFUNCTYPE(
                ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
            )
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            def _proc(n_code, w_param, l_param):
                if n_code == 0 and int(w_param) in (
                    self._WM_KEYDOWN,
                    self._WM_SYSKEYDOWN,
                ):
                    data = ctypes.cast(
                        l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)
                    ).contents
                    command = self._VK_TO_COMMAND.get(int(data.vkCode))
                    if command is not None:
                        self.command.emit(command)
                        return 1
                return user32.CallNextHookEx(self._hook, n_code, w_param, l_param)

            self._callback = hook_proc(_proc)
            self._hook = user32.SetWindowsHookExW(
                self._WH_KEYBOARD_LL,
                self._callback,
                kernel32.GetModuleHandleW(None),
                0,
            )
        except Exception:
            self._hook = None
            self._callback = None


class _Segmented(QWidget):
    """Right-side tab bar."""

    changed = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 14, 12, 0)
        h.setSpacing(0)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._label_keys = [
            "library",
            "artists",
            "albums",
            "queue",
            "lyrics",
            "playlists",
        ]
        for i, key in enumerate(self._label_keys):
            b = QPushButton(tr(key))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_SEG_QSS)
            self._group.addButton(b, i)
            h.addWidget(b)
        h.addStretch(1)
        self._group.idClicked.connect(self.changed.emit)
        self.set_index(3)

    def set_index(self, idx: int) -> None:
        btn = self._group.button(idx)
        if btn is not None:
            btn.setChecked(True)

    def retranslate(self) -> None:
        for i, key in enumerate(self._label_keys):
            btn = self._group.button(i)
            if btn is not None:
                btn.setText(tr(key))


_SEG_QSS = """
QPushButton {
    background: transparent;
    color: #999;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 11px;
    font-size: 13px;
}
QPushButton:hover { color: #FFF; }
QPushButton:checked {
    color: #FFF;
    border-bottom: 2px solid #E63946;
}
"""


class MainWindow(QMainWindow):
    VIEW_LIBRARY = 0
    VIEW_ARTISTS = 1
    VIEW_ALBUMS = 2
    VIEW_QUEUE = 3
    VIEW_LYRICS = 4
    VIEW_PLAYLISTS = 5

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WMplayer")
        self.setMinimumSize(QSize(983, 785))
        self.resize(QSize(983, 785))
        self._frame_dpr = self.devicePixelRatioF()
        self.setStyleSheet(GLOBAL_QSS)
        self._config = Config()
        set_language(str(self._config.get("language", "en")))

        self._last_media_command: tuple[int, float] = (-1, 0.0)
        self._media_key_hook = _MediaKeyHook(self)

        self._engine = AudioEngine(self)
        self._playlist = Playlist(self)
        self._library = Library(LIBRARY_CACHE_PATH, self)
        self._library.set_folders(self._config.library_folders_effective())
        self._store = PlaylistStore(default_playlists_dir(), self)
        self._store.set_locations(self._config.playlist_locations_effective())

        self._pool = QThreadPool.globalInstance()
        self._cover_signals = _CoverSignals(self)
        self._cover_signals.done.connect(self._on_cover_loaded)
        self._cover_cache: dict[str, Optional[bytes]] = {}
        self._cover_pending: set[str] = set()
        self._cover_cache_limit = 64

        self._autoplay_after_load = True

        self._build_ui()
        self._wire()
        self._restore_state()

    def _build_ui(self) -> None:
        # Reserve status space before the first message can resize the player.
        self.statusBar().setSizeGripEnabled(False)
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.player_panel = PlayerPanel()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setStyleSheet("background-color: #333333; border: none;")
        sep.setFixedWidth(1)

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
        self.stack.addWidget(self.library_panel)  # 0
        self.stack.addWidget(self.artists_panel)  # 1
        self.stack.addWidget(self.albums_panel)  # 2
        self.stack.addWidget(self.queue_panel)  # 3
        self.stack.addWidget(self.lyrics_panel)  # 4
        self.stack.addWidget(self.playlists_panel)  # 5
        self.stack.setCurrentIndex(self.VIEW_QUEUE)
        rv.addWidget(self.stack, 1)

        layout.addWidget(self.player_panel, 0)
        layout.addWidget(sep, 0)
        layout.addWidget(right, 1)

    def _wire(self) -> None:
        self._media_key_hook.command.connect(self._handle_media_app_command)

        self.segmented.changed.connect(self._switch_view)

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
        self._engine.position_changed.connect(self.player_panel.set_position)
        self._engine.position_changed.connect(self.lyrics_panel.update_position)
        self._engine.duration_changed.connect(self._on_duration_changed)
        self._engine.state_changed.connect(self._on_state_changed)
        self._engine.track_finished.connect(self._on_track_finished)
        self._engine.backend_track_changed.connect(self._on_backend_track_changed)
        self._engine.error_occurred.connect(
            lambda msg: self.statusBar().showMessage(tr("error_status", msg=msg), 4000)
        )

        self._playlist.current_changed.connect(self._on_current_changed)
        self._playlist.changed.connect(self._on_playlist_changed)
        self._playlist.shuffled_changed.connect(self.player_panel.set_shuffled)
        self._playlist.repeat_changed.connect(self.player_panel.set_repeat)
        self._playlist.shuffled_changed.connect(
            lambda _shuffled: self._preload_next_track()
        )
        self._playlist.repeat_changed.connect(
            lambda _repeat: self._preload_next_track()
        )

        self.queue_panel.track_double_clicked.connect(self._play_index)
        self.queue_panel.remove_requested.connect(self._on_remove_track)
        self.queue_panel.clear_requested.connect(self._on_clear_queue)
        self.queue_panel.save_as_playlist_requested.connect(
            self._on_save_queue_as_playlist
        )

        self.library_panel.play_paths_now.connect(self._play_paths_now)
        self.library_panel.enqueue_paths.connect(self._enqueue_paths)
        self.library_panel.play_next_paths.connect(self._play_next_paths)
        self.library_panel.add_paths_to_playlist.connect(
            self._add_paths_to_some_playlist
        )
        self.library_panel.open_artist_requested.connect(self._open_artist_from_search)
        self.library_panel.open_album_requested.connect(self._open_album_from_search)
        self.library_panel.rescan_requested.connect(self._rescan_library)

        self.albums_panel.play_paths_sequential.connect(self._play_paths_sequential_now)
        self.albums_panel.enqueue_paths.connect(self._enqueue_paths)
        self.albums_panel.play_next_paths.connect(self._play_next_paths)
        self.albums_panel.add_paths_to_playlist.connect(
            self._add_paths_to_some_playlist
        )

        self.artists_panel.play_paths_sequential.connect(
            self._play_paths_sequential_now
        )
        self.artists_panel.play_paths_shuffled.connect(self._play_paths_shuffled_now)
        self.artists_panel.enqueue_paths.connect(self._enqueue_paths)
        self.artists_panel.play_next_paths.connect(self._play_next_paths)
        self.artists_panel.add_paths_to_playlist.connect(
            self._add_paths_to_some_playlist
        )

        self.playlists_panel.open_playlist.connect(self._on_open_playlist)
        self.playlists_panel.rename_playlist.connect(self._on_rename_playlist)
        self.playlists_panel.delete_playlist.connect(self._on_delete_playlist)

        self.lyrics_panel.seek_to_ms.connect(self._engine.seek)

        def _sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.activated.connect(fn)
            return s

        _sc("Space", self._toggle_play)
        _sc(Qt.Key.Key_MediaPlay, self._toggle_play)
        _sc(Qt.Key.Key_MediaNext, self._play_next)
        _sc(Qt.Key.Key_MediaPrevious, self._play_prev)
        _sc("Right", lambda: self._engine.seek(self._engine.get_position() + 5000))
        _sc("Left", lambda: self._engine.seek(self._engine.get_position() - 5000))
        _sc(
            "Up",
            lambda: self._engine.set_volume(min(100, self._engine.get_volume() + 5)),
        )
        _sc(
            "Down",
            lambda: self._engine.set_volume(max(0, self._engine.get_volume() - 5)),
        )

    def _handle_media_app_command(self, command: int) -> bool:
        now = time.monotonic()
        last_command, last_time = self._last_media_command
        if command == last_command and now - last_time < 0.18:
            return True
        self._last_media_command = (command, now)

        handlers = {
            11: self._play_next,
            12: self._play_prev,
            13: self._stop_from_media_key,
            14: self._toggle_play,
            46: self._play_from_media_key,
            47: self._pause_from_media_key,
        }
        handler = handlers.get(command)
        if handler is None:
            return False
        handler()
        return True

    def _stop_from_media_key(self) -> None:
        self._engine.stop()
        self.player_panel.set_playing(False)

    def _play_from_media_key(self) -> None:
        if not self._engine.is_playing():
            self._toggle_play()

    def _pause_from_media_key(self) -> None:
        if self._engine.is_playing():
            self._toggle_play()

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

    def _open_artist_from_search(self, artist: str) -> None:
        self._switch_view(self.VIEW_ARTISTS)
        self.artists_panel.show_artist(artist)

    def _open_album_from_search(self, album: str) -> None:
        self._switch_view(self.VIEW_ALBUMS)
        self.albums_panel.show_album(album)

    def _switch_view(self, idx: int) -> None:
        self.segmented.set_index(idx)
        self.stack.setCurrentIndex(idx)

        if idx == self.VIEW_ALBUMS:
            self.albums_panel.stack.setCurrentIndex(0)
        elif idx == self.VIEW_ARTISTS:
            self.artists_panel.stack.setCurrentIndex(0)

    def _retranslate_ui(self) -> None:
        self.segmented.retranslate()
        for panel in (
            self.library_panel,
            self.artists_panel,
            self.albums_panel,
            self.queue_panel,
            self.lyrics_panel,
            self.playlists_panel,
        ):
            fn = getattr(panel, "retranslate", None)
            if callable(fn):
                fn()

    def _restore_state(self) -> None:
        self._engine.set_volume(int(self._config.get("volume", 80)))
        self._restore_playback_mode()
        self._restore_queue()

        if len(self._library) == 0 and self._library.folders:
            self._library.scan_async()

    def _restore_playback_mode(self) -> None:
        if self._config.has("shuffled") or self._config.has("repeat"):
            try:
                self._playlist.set_repeat(
                    RepeatMode(self._config.get("repeat", "none"))
                )
            except Exception:
                self._playlist.set_repeat(RepeatMode.NONE)
            self._playlist.set_shuffled(bool(self._config.get("shuffled", False)))
        else:
            try:
                self._playlist.set_mode(
                    PlayMode(self._config.get("play_mode", "sequential"))
                )
            except Exception:
                self._playlist.set_mode(PlayMode.SEQUENTIAL)

    def _restore_queue(self) -> None:
        if not os.path.isfile(QUEUE_CACHE_PATH):
            return
        paths = m3u.parse_file(QUEUE_CACHE_PATH)
        if not paths:
            return
        original_paths = (
            m3u.parse_file(QUEUE_ORIGINAL_CACHE_PATH)
            if os.path.isfile(QUEUE_ORIGINAL_CACHE_PATH)
            else None
        )
        original_tracks = (
            self._tracks_from_paths(original_paths) if original_paths else None
        )
        self._playlist.restore_with_tracks(
            self._tracks_from_paths(paths), original_tracks
        )

        last_path = self._config.get("last_track_path", "")
        index = self._config.get("last_queue_index", -1)
        track = self._playlist.get(index) if isinstance(index, int) else None
        if track is None or track.path != last_path:
            index = self._playlist.find_index_by_path(last_path) if last_path else -1
        if index < 0:
            return
        self._autoplay_after_load = False
        self._playlist.set_current(index)
        if self._config.get("auto_resume", True):
            position_ms = int(self._config.get("last_position_ms", 0))
            if position_ms > 0:
                self._engine.seek(position_ms)

    def event(self, e):
        if (
            e.type() == QEvent.Type.DevicePixelRatioChange
            and hasattr(self, "_frame_dpr")
        ):
            self._refresh_frame_for_dpi()
        return super().event(e)

    def _refresh_frame_for_dpi(self) -> None:
        dpr = self.devicePixelRatioF()
        if dpr == self._frame_dpr:
            return
        self._frame_dpr = dpr
        if QGuiApplication.platformName() != "windows" or self.windowHandle() is None:
            return
        # QTBUG-142163: refresh native frame metrics before Qt applies the
        # DPI-scaled geometry. Match QWindowsContext::forceNcCalcSize without
        # replacing a window procedure or changing the window's position/size.
        try:
            import win32con
            import win32gui

            flags = (
                win32con.SWP_FRAMECHANGED | win32con.SWP_NOACTIVATE
                | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                | win32con.SWP_NOZORDER | win32con.SWP_NOOWNERZORDER
            )
            win32gui.SetWindowPos(int(self.winId()), 0, 0, 0, 0, 0, flags)
        except Exception as exc:
            qWarning(f"Could not refresh the window frame after DPI change: {exc}")

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "player_panel"):
            self.player_panel._lock_width_to_height()

    def closeEvent(self, e):  # noqa: N802
        if not self._config.factory_reset_pending:
            self._save_state()
        try:
            self._media_key_hook.close()
        except Exception:
            pass
        try:
            self._engine.release()
        except Exception:
            pass
        super().closeEvent(e)

    def _save_state(self) -> None:
        try:
            self._config.set("volume", self._engine.get_volume())
            self._config.set("shuffled", self._playlist.shuffled)
            self._config.set("repeat", self._playlist.repeat.value)
            self._config.set("play_mode", self._playlist.mode.value)
            self._config.set("last_position_ms", self._engine.get_position())
            current = self._playlist.current
            self._config.set("last_track_path", current.path if current else "")
            self._config.set("last_queue_index", self._playlist.current_index)
            self._config.save()
            m3u.write_file(QUEUE_CACHE_PATH, "queue", self._playlist.paths)
            self._save_original_queue()
        except Exception:
            pass

    def _save_original_queue(self) -> None:
        original_paths = self._playlist.original_paths
        if original_paths is not None:
            m3u.write_file(QUEUE_ORIGINAL_CACHE_PATH, "queue_original", original_paths)
        elif os.path.isfile(QUEUE_ORIGINAL_CACHE_PATH):
            os.remove(QUEUE_ORIGINAL_CACHE_PATH)

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

    def _on_backend_track_changed(self, path: str) -> None:
        idx = self._playlist.next_index(auto=True)
        track = self._playlist.get(idx) if idx is not None else None
        if track is None or track.path != path:
            return
        if idx == self._playlist.current_index:
            return
        self._autoplay_after_load = self._engine.is_playing()
        self._playlist.set_current(idx)

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
        cached_cover = self._cover_cache.get(track.path)
        if cached_cover and not track.cover:
            track.cover = cached_cover
        self.player_panel.set_track(track, index, len(self._playlist))
        if self._engine.load(track.path) and self._autoplay_after_load:
            self._engine.play()
        self._fetch_cover_async(track.path)
        self._load_lyrics_for(track.path)
        self._preload_next_track()

    def _on_playlist_changed(self) -> None:
        """Refresh queue-dependent UI without reloading playback."""
        cur = self._playlist.current
        idx = self._playlist.current_index
        total = len(self._playlist)
        if cur is None or idx < 0:
            self._engine.preload(None)
            return
        self.player_panel.lbl_index.setText(f"{idx + 1}/{total}")
        self._preload_next_track()

    def _preload_next_track(self) -> None:
        nxt = self._playlist.next_index(auto=True)
        if nxt is None or nxt == self._playlist.current_index:
            self._engine.preload(None)
            return
        track = self._playlist.get(nxt)
        if track is None:
            self._engine.preload(None)
            return
        self._engine.preload(track.path)
        self._fetch_cover_async(track.path)

    def _load_lyrics_for(self, audio_path: str) -> None:
        """Load lyrics for an audio path."""
        lrc_path = lrc_mod.find_lrc_for(audio_path)
        lyr = lrc_mod.parse_file(lrc_path) if lrc_path else None
        cur = self._playlist.current
        label = ""
        if cur is not None:
            label = f"{cur.title} - {cur.artist}"
        self.lyrics_panel.set_lyrics(lyr, track_label=label)
        self.player_panel.set_lyrics_available(self.lyrics_panel.has_lyrics())

    def _on_duration_changed(self, ms: int) -> None:
        self.player_panel.set_duration(ms)
        track = self._playlist.current
        if track is not None and ms > 0:
            track.duration_ms = ms

    def _on_state_changed(self, state: str) -> None:
        self.player_panel.set_playing(state == "playing")

    def _remember_cover(self, path: str, cover: Optional[bytes]) -> None:
        self._cover_cache[path] = cover
        while len(self._cover_cache) > self._cover_cache_limit:
            self._cover_cache.pop(next(iter(self._cover_cache)))

    def _fetch_cover_async(self, path: str) -> None:
        if not path:
            return
        cur = self._playlist.current
        if path in self._cover_cache:
            cover = self._cover_cache[path]
            if cur and cur.path == path and cover:
                cur.cover = cover
                self.player_panel.cover.set_cover(cover)
            return
        if cur and cur.path == path and cur.cover:
            self._remember_cover(path, cur.cover)
            self.player_panel.cover.set_cover(cur.cover)
            return
        if path in self._cover_pending:
            return
        self._cover_pending.add(path)
        self._pool.start(_CoverFetcher(path, self._cover_signals))

    def _on_cover_loaded(self, path: str, cover) -> None:
        self._cover_pending.discard(path)
        self._remember_cover(path, cover)
        for t in self._playlist:
            if t.path == path:
                t.cover = cover
                break
        cur = self._playlist.current
        if cur is None or cur.path != path:
            return
        if cover:
            cur.cover = cover
            self.player_panel.cover.set_cover(cover)

    def _on_remove_track(self, index: int) -> None:
        was_current = index == self._playlist.current_index
        self._playlist.remove(index)
        if was_current:
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
        ans = QMessageBox.question(
            self, tr("clear_queue_title"), tr("clear_queue_confirm")
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._engine.stop()
            self._engine.preload(None)
            self._playlist.clear()
            self.player_panel.set_track(None, -1, 0)
            self.lyrics_panel.set_lyrics(None)
            self.player_panel.set_lyrics_available(False)

    def _on_save_queue_as_playlist(self, name: str) -> None:
        if not name:
            return
        ok = self._store.save(name, self._playlist.paths)
        if ok:
            self.statusBar().showMessage(tr("saved_playlist_status", name=name), 3000)
        else:
            QMessageBox.warning(self, tr("save_failed_title"), tr("save_failed_msg"))

    def _tracks_from_paths(self, paths):
        """Resolve tracks from paths with cache fallback."""
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

    def _play_paths_sequential_now(
        self, paths: List[str], start_index: int = 0
    ) -> None:
        if not paths:
            return
        self._playlist.set_mode(PlayMode.SEQUENTIAL)
        self._play_paths_now(paths, start_index)

    def _play_paths_shuffled_now(self, paths: List[str]) -> None:
        if not paths:
            return
        tracks = self._tracks_from_paths(paths)
        self._playlist.replace_with_tracks(tracks, -1)
        self._playlist.set_mode(PlayMode.SHUFFLE)
        if len(self._playlist) > 0:
            self._play_index(0)

    def _enqueue_paths(self, paths: List[str]) -> None:
        if not paths:
            return
        tracks = self._tracks_from_paths(paths)
        n = self._playlist.append_tracks(tracks)
        self.statusBar().showMessage(tr("added_to_queue_status", n=n), 3000)

    def _play_next_paths(self, paths: List[str]) -> None:
        if not paths:
            return
        n = self._playlist.insert_next(self._tracks_from_paths(paths))
        self.statusBar().showMessage(tr("play_next_status", n=n), 3000)

    def _add_paths_to_some_playlist(self, paths: List[str]) -> None:
        if not paths:
            return
        names = self._store.list_names()
        if not names:
            name = self._prompt_new_playlist_name()
            if name is None:
                return
            self._store.save(name, paths)
            self.statusBar().showMessage(
                tr("create_playlist_status", name=name, n=len(paths)), 3000
            )
            return
        new_label = f"<{tr('new_playlist')}>"
        choice, ok = QInputDialog.getItem(
            self,
            tr("join_playlist"),
            tr("select_playlist"),
            [new_label] + names,
            0,
            False,
        )
        if not ok:
            return
        if choice == new_label:
            name = self._prompt_new_playlist_name()
            if name is not None:
                self._store.save(name, paths)
            return
        self._append_paths_to_playlist(choice, paths)

    def _prompt_new_playlist_name(self) -> Optional[str]:
        name, ok = QInputDialog.getText(self, tr("new_playlist"), tr("playlist_name"))
        if not ok or not name.strip():
            return None
        return name.strip()

    def _append_paths_to_playlist(self, name: str, paths: List[str]) -> None:
        merged = self._store.load(name)
        seen = set(merged)
        for path in paths:
            if path not in seen:
                merged.append(path)
                seen.add(path)
        self._store.save(name, merged)
        self.statusBar().showMessage(
            tr("added_to_playlist_status", n=len(paths), name=name), 3000
        )

    def _rescan_library(self) -> None:
        self._library.set_folders(self._config.library_folders_effective())
        self._library.scan_async()

    def _on_open_playlist(self, name: str) -> None:
        paths = self._store.load(name)
        if not paths:
            QMessageBox.information(
                self, tr("empty_playlist_title"), tr("empty_playlist_msg", name=name)
            )
            return
        self._playlist.replace_with_tracks(self._tracks_from_paths(paths))
        self._switch_view(self.VIEW_QUEUE)
        if len(self._playlist) > 0:
            self._play_index(0)

    def _on_rename_playlist(self, old: str, new: str) -> None:
        if not self._store.is_writable(old):
            QMessageBox.information(
                self, tr("readonly_rename_title"), tr("readonly_rename_msg")
            )
            return
        if not self._store.rename(old, new):
            QMessageBox.warning(
                self, tr("rename_failed_title"), tr("rename_failed_msg")
            )

    def _on_delete_playlist(self, name: str) -> None:
        if not self._store.is_writable(name):
            QMessageBox.information(
                self, tr("readonly_delete_title"), tr("readonly_delete_msg")
            )
            return
        self._store.delete(name)

    def _on_settings(self) -> None:
        dlg = SettingsDialog(self._config, self)
        if dlg.exec():
            dlg.apply_to_config()
            self._engine.set_volume(int(self._config.get("volume", 80)))
            set_language(str(self._config.get("language", "en")))
            self._retranslate_ui()
            self._library.set_folders(self._config.library_folders_effective())
            self._store.set_locations(self._config.playlist_locations_effective())
            self._library.scan_async()
