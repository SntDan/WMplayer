"""Main application window and signal wiring."""

from __future__ import annotations

import os
import time
from typing import List, Optional

from PyQt6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QObject,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QVariantAnimation,
    qWarning,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QGuiApplication, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyleOptionButton,
    QVBoxLayout,
    QWidget,
)

from core import lrc as lrc_mod
from core import m3u
from core.audio_engine import AudioEngine
from core.config import (
    DEFAULT_VOLUME,
    LIBRARY_CACHE_PATH,
    QUEUE_CACHE_PATH,
    QUEUE_ORIGINAL_CACHE_PATH,
    Config,
    default_playlists_dir,
)
from core.library import Library
from core.metadata import read_metadata
from core.media_controls import MediaControls
from core.playlist import Playlist, RepeatMode
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


_TAB_ANIMATION_MS = 70


class _SegmentButton(QPushButton):
    """Fade the label and underline in place, keeping native button behavior."""

    def __init__(self, text: str, parent: QWidget) -> None:
        super().__init__(text, parent)
        self._label_brightness = 153.0
        self._underline_opacity = 0.0
        self._start_brightness = self._target_brightness = self._label_brightness
        self._start_opacity = self._target_opacity = self._underline_opacity
        self._hovered = False
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(_TAB_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.valueChanged.connect(self._set_progress)
        self.toggled.connect(self._animate_state)

    def _set_progress(self, progress: float) -> None:
        self._label_brightness = self._start_brightness + (
            self._target_brightness - self._start_brightness
        ) * progress
        self._underline_opacity = self._start_opacity + (
            self._target_opacity - self._start_opacity
        ) * progress
        self.update()

    def _animate_state(self) -> None:
        self._animation.stop()
        self._start_brightness = self._label_brightness
        self._start_opacity = self._underline_opacity
        self._target_brightness = 255.0 if self.isChecked() or self._hovered else 153.0
        self._target_opacity = 1.0 if self.isChecked() else 0.0
        if not self.isVisible():
            self._set_progress(1.0)
            return
        self._animation.start()

    def enterEvent(self, event) -> None:  # noqa: N802
        super().enterEvent(event)
        self._hovered = True
        self._animate_state()

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._hovered = False
        self._animate_state()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(
            QStyle.SubElement.SE_PushButtonContents, option, self
        )
        painter = QPainter(self)
        brightness = round(self._label_brightness)
        painter.setPen(QColor(brightness, brightness, brightness))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        painter.setOpacity(self._underline_opacity)
        # Match the 6px side margins, 4px bottom margin and 2px line.
        painter.fillRect(6, self.height() - 6, self.width() - 12, 2, QColor("#E63946"))


class _Segmented(QWidget):
    """Right-side tab bar."""

    changed = pyqtSignal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 4, 12, 0)
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
            b = _SegmentButton(tr(key), self)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(_SEG_QSS)
            self._group.addButton(b, i)
            h.addWidget(b)
        h.addStretch(1)
        self._group.idClicked.connect(self._on_clicked)
        self.set_index(3)

    def _on_clicked(self, idx: int) -> None:
        self.set_index(idx)
        self.changed.emit(idx)

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
    color: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    margin: 0px 6px 4px 6px;
    padding: 8px 5px 4px 5px;
    font-size: 13px;
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
        self.setMinimumSize(QSize(983, 760))
        self.resize(QSize(983, 760))
        self._frame_dpr = self.devicePixelRatioF()
        self.setStyleSheet(GLOBAL_QSS)
        self._config = Config()
        set_language(str(self._config.get("language", "en")))

        self._last_media_command: tuple[int, float] = (-1, 0.0)
        self._media_key_hook = _MediaKeyHook(self)

        self._media_controls = MediaControls(self)
        self._engine = AudioEngine(self, media_controls=not self._media_controls.available)
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
        self._restore_position_ms = 0

        self._build_ui()
        self._wire()
        self._restore_state()

    def _build_ui(self) -> None:
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
        self._media_controls.command.connect(self._handle_media_app_command)
        self._media_controls.seek_requested.connect(self._engine.seek)
        self._engine.state_changed.connect(self._media_controls.set_state)
        self._engine.duration_changed.connect(self._media_controls.set_duration)
        self._engine.position_changed.connect(self._media_controls.set_position)

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
            lambda msg: qWarning(f"Playback error: {msg}")
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

        self.library_panel.play_track_requested.connect(self._play_library_track_now)
        self.library_panel.play_paths_now.connect(self._play_paths_now)
        self.library_panel.enqueue_paths.connect(self._enqueue_paths)
        self.library_panel.play_next_paths.connect(self._play_next_paths)
        self.library_panel.add_paths_to_playlist.connect(
            self._add_paths_to_some_playlist
        )
        self.library_panel.open_artist_requested.connect(self._open_artist)
        self.library_panel.open_album_requested.connect(self._open_album)
        self.library_panel.rescan_requested.connect(self._rescan_library)

        self.albums_panel.play_album_requested.connect(self._play_album_now)
        self.albums_panel.enqueue_paths.connect(self._enqueue_paths)
        self.albums_panel.play_next_paths.connect(self._play_next_paths)
        self.albums_panel.add_paths_to_playlist.connect(
            self._add_paths_to_some_playlist
        )

        self.artists_panel.play_album_requested.connect(self._play_album_now)
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
            self._open_artist(track.artist)

    def _on_player_album_double_clicked(self) -> None:
        track = self._playlist.current
        if track and track.album:
            self._open_album(track.album, track.artist)

    def _open_artist(self, artist: str) -> None:
        self._switch_view(self.VIEW_ARTISTS)
        self.artists_panel.show_artist(artist)

    def _open_album(self, album: str, artist: Optional[str] = None) -> None:
        self._switch_view(self.VIEW_ALBUMS)
        self.albums_panel.show_album(album, artist)

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
            panel.retranslate()

    def _restore_state(self) -> None:
        self._engine.set_volume(int(self._config.get("volume", DEFAULT_VOLUME)))
        self._restore_playback_mode()
        self._restore_queue()
        self._restore_view_state()

        if len(self._library) == 0 and self._library.folders:
            self._library.scan_async()

    def _restore_playback_mode(self) -> None:
        try:
            repeat = RepeatMode(self._config.get("repeat"))
        except (TypeError, ValueError):
            repeat = RepeatMode.NONE
        self._playlist.set_repeat(repeat)
        self._playlist.set_shuffled(bool(self._config.get("shuffled")))

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
        self._restore_position_ms = 0
        if self._config.get("auto_resume"):
            try:
                position = int(self._config.get("last_position_ms", 0))
                self._restore_position_ms = max(0, position)
            except (TypeError, ValueError):
                pass
        self._playlist.set_current(index)

    def _view_searches(self) -> dict:
        return {
            "library": (self.library_panel.search, self.library_panel),
            "queue": (self.queue_panel.search, self.queue_panel),
            "artists": (self.artists_panel.search_box, self.artists_panel),
            "albums": (self.albums_panel.search_box, self.albums_panel),
        }

    def _view_lists(self) -> dict:
        subpanel = self.artists_panel.albums_subpanel
        return {
            "library": self.library_panel.list,
            "queue": self.queue_panel.list,
            "artists": self.artists_panel.list_artists,
            "artist_albums": subpanel.list_albums,
            "artist_tracks": subpanel.list_tracks,
            "albums": self.albums_panel.list_albums,
            "album_tracks": self.albums_panel.list_tracks,
            "playlists": self.playlists_panel.list,
        }

    def _save_view_state(self) -> None:
        subpanel = self.artists_panel.albums_subpanel
        self._config.set("right_panel_state", {
            "view": self.stack.currentIndex(),
            "searches": {
                key: editor.text() for key, (editor, _) in self._view_searches().items()
            },
            "album": self.albums_panel._current_album
            if self.albums_panel.stack.currentIndex() == 1 else None,
            "album_artist": self.albums_panel._current_artist,
            "artist": subpanel._filter_artist
            if self.artists_panel.stack.currentIndex() == 1 else None,
            "artist_album": subpanel._current_album
            if subpanel.stack.currentIndex() == 1 else None,
            "scrolls": {
                key: widget.verticalScrollBar().value()
                for key, widget in self._view_lists().items()
            },
        })
        geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self._config.set("window_geometry", geometry)

    def _restore_view_state(self) -> None:
        geometry = self._config.get("window_geometry")
        if isinstance(geometry, str):
            encoded = geometry.encode("ascii", errors="ignore")
            self.restoreGeometry(QByteArray.fromBase64(encoded))
        state = self._config.get("right_panel_state", {})
        if not isinstance(state, dict):
            state = {}
        view = state.get("view", self.VIEW_QUEUE)
        if not isinstance(view, int) or not 0 <= view < self.stack.count():
            view = self.VIEW_QUEUE
        self._switch_view(view)
        searches = state.get("searches", {})
        if isinstance(searches, dict):
            for key, (editor, panel) in self._view_searches().items():
                text = searches.get(key, "")
                if isinstance(text, str):
                    editor.setText(text)
                    panel._search_timer.stop()
                    panel._apply_filter(text)
        album = state.get("album")
        if isinstance(album, str) and album in self.albums_panel._albums_tracks:
            album_artist = state.get("album_artist")
            self.albums_panel.show_album(album, album_artist if isinstance(album_artist, str) else None)
        artist = state.get("artist")
        if isinstance(artist, str) and any(
            self.artists_panel.list_artists.item(i).data(Qt.ItemDataRole.UserRole) == artist
            for i in range(self.artists_panel.list_artists.count())
        ):
            self.artists_panel.show_artist(artist)
            subpanel = self.artists_panel.albums_subpanel
            album = state.get("artist_album")
            if isinstance(album, str) and album in subpanel._albums_tracks:
                subpanel.show_album(album)
        scrolls = state.get("scrolls", {})
        if isinstance(scrolls, dict):
            # Apply after the restored page has its final layout and scroll range.
            QTimer.singleShot(0, lambda: self._restore_view_scrolls(scrolls))

    def _restore_view_scrolls(self, scrolls: dict) -> None:
        for key, widget in self._view_lists().items():
            value = scrolls.get(key)
            if isinstance(value, int):
                widget.verticalScrollBar().setValue(value)

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
        self._media_controls.close()
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
            self._config.set("last_position_ms", self._engine.get_position())
            current = self._playlist.current
            self._config.set("last_track_path", current.path if current else "")
            self._config.set("last_queue_index", self._playlist.current_index)
            self._save_view_state()
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
        self._media_controls.set_track(track)
        self._load_lyrics_for(track.path)
        position_ms = self._restore_position_ms
        self._restore_position_ms = 0
        if self._engine.load(track.path):
            if position_ms > 0:
                self._engine.seek(position_ms)
            if self._autoplay_after_load:
                self._engine.play()
        self._fetch_cover_async(track.path)
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
            self._media_controls.set_cover(cover)

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
        self._save_playlist(name, self._playlist.paths, "readonly_save_msg")

    def _confirm_internal_playlist(
        self, name: str, message_key: str = "readonly_edit_msg"
    ) -> bool:
        if self._store.is_writable(name) or name not in self._store.list_names():
            return True
        return QMessageBox.question(
            self,
            tr("copy_playlist_title"),
            tr(message_key, name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Yes

    def _save_playlist(
        self, name: str, paths: List[str], message_key: str = "readonly_edit_msg"
    ) -> None:
        if not name or not self._confirm_internal_playlist(name, message_key):
            return
        source = (
            self._store.file_path(name)
            if name in self._store.list_names() and not self._store.is_writable(name)
            else None
        )
        if not self._store.save(name, paths):
            QMessageBox.warning(self, tr("save_failed_title"), tr("save_failed_msg"))
        elif source is not None:
            self._remove_external_playlist_source(source)

    def _remove_external_playlist_source(self, source: str) -> None:
        """Keep only the internal copy after a confirmed external playlist edit."""
        source_key = os.path.normcase(os.path.abspath(source))
        locations = [
            path for path in self._config.playlist_locations_effective()
            if os.path.normcase(os.path.abspath(path)) != source_key
        ]
        self._config.set("playlist_locations", locations)
        self._config.save()
        self._store.set_locations(locations)

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

    def _play_library_track_now(self, path: str) -> None:
        track = self._library.find_by_path(path)
        if track is None:
            return
        paths = [item.path for item in self._library.album_tracks(track)]
        try:
            index = paths.index(path)
        except ValueError:
            return
        self._play_album_now(paths, index)

    def _play_paths_now(self, paths: List[str], start_index: int = 0) -> None:
        if not paths:
            return
        tracks = self._tracks_from_paths(paths)
        new_start_index = self._playlist.replace_with_tracks(tracks, start_index)
        if len(self._playlist) > 0:
            self._play_index(new_start_index)

    def _play_album_now(
        self, paths: List[str], start_index: int = 0, play_all: bool = False
    ) -> None:
        """Play an ordered album block, then continue the existing queue."""
        if not paths:
            return
        start_index = max(0, min(start_index, len(paths) - 1))
        continue_album = play_all or self._config.get("album_continuation")
        end_index = None if continue_album else start_index + 1
        tracks = self._tracks_from_paths(paths[start_index:end_index])
        index = self._playlist.replace_current(tracks)
        if index >= 0:
            self._play_index(index)

    def _play_paths_shuffled_now(self, paths: List[str]) -> None:
        if not paths:
            return
        tracks = self._tracks_from_paths(paths)
        self._playlist.replace_with_tracks(tracks, -1)
        self._playlist.set_repeat(RepeatMode.NONE)
        self._playlist.set_shuffled(True)
        if len(self._playlist) > 0:
            self._play_index(0)

    def _enqueue_paths(self, paths: List[str]) -> None:
        if not paths:
            return
        tracks = self._tracks_from_paths(paths)
        self._playlist.append_tracks(tracks)

    def _play_next_paths(self, paths: List[str]) -> None:
        if not paths:
            return
        self._playlist.insert_next(self._tracks_from_paths(paths))

    def _add_paths_to_some_playlist(self, paths: List[str]) -> None:
        if not paths:
            return
        names = self._store.list_names()
        if not names:
            name = self._prompt_new_playlist_name()
            if name is None:
                return
            self._save_playlist(name, paths, "readonly_save_msg")
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
                self._save_playlist(name, paths, "readonly_save_msg")
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
        self._save_playlist(name, merged)

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
        if not new or old == new:
            return
        if not self._store.is_writable(old):
            if not self._confirm_internal_playlist(old):
                return
            source = self._store.file_path(old)
            ok = self._store.copy_to_default(old, new)
            if ok:
                self._remove_external_playlist_source(source)
        else:
            ok = self._store.rename(old, new)
        if not ok:
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
        original_volume = self._engine.get_volume()
        dlg = SettingsDialog(self._config, self)
        dlg.slider_vol.setValue(original_volume)
        dlg.volume_changed.connect(self._engine.set_volume)
        if dlg.exec():
            dlg.apply_to_config()
            self._retranslate_ui()
            self._library.set_folders(self._config.library_folders_effective())
            self._store.set_locations(self._config.playlist_locations_effective())
            self._library.scan_async()
        else:
            self._engine.set_volume(original_volume)
        dlg.deleteLater()
