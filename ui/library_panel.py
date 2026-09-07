"""Library search and playback panel."""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.library import Library
from core.thumbnails import thumb_path_for
from ui.i18n import tr
from ui.list_delegates import (
    ROLE_IS_HR,
    ROLE_SECTION_HEADER,
    ROLE_SUBTITLE,
    ROLE_THUMB_PATH,
)
from ui.list_helpers import (
    add_list_header,
    connect_debounced_filter,
    cover_list,
    suspended_updates,
)
from ui.theme import BTN_QSS as _BTN_QSS


class LibraryPanel(QWidget):
    play_paths_now = pyqtSignal(list, int)
    enqueue_paths = pyqtSignal(list)
    add_paths_to_playlist = pyqtSignal(list)
    open_artist_requested = pyqtSignal(str)
    open_album_requested = pyqtSignal(str)
    rescan_requested = pyqtSignal()

    def __init__(self, library: Library, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._library = library
        self._build_ui()
        self._wire()
        self.refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        self.title_label, self.count_label = add_list_header(
            outer, tr("library"), tr("tracks_count", n=0)
        )

        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_library"))
        self.search.setClearButtonEnabled(True)
        action_row.addWidget(self.search, 1)

        self.btn_scan = QPushButton(tr("scan_library"))
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet(_BTN_QSS)
        action_row.addWidget(self.btn_scan)
        outer.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet(
            "QProgressBar{border:1px solid #333; border-radius:3px; "
            "background:#1a1a1a; height:14px; text-align:center;}"
            "QProgressBar::chunk{background:#E63946; border-radius:2px;}"
        )
        outer.addWidget(self.progress)

        self.list = cover_list(uniform_sizes=False)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._library.tracks_changed.connect(self.refresh)
        self._library.scan_started.connect(self._on_scan_started)
        self._library.scan_progress.connect(self._on_scan_progress)
        self._library.scan_finished.connect(self._on_scan_finished)
        self.btn_scan.clicked.connect(self.rescan_requested.emit)
        self._search_timer = connect_debounced_filter(
            self, self.search, self._apply_filter
        )
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

    _ROLE_RESULT_KIND = Qt.ItemDataRole.UserRole + 10
    _ROLE_RESULT_PATHS = Qt.ItemDataRole.UserRole + 11

    def refresh(self) -> None:
        self.count_label.setText(tr("tracks_count", n=len(self._library.tracks)))
        self._rebuild_results(self.search.text())

    def _rebuild_results(self, text: str) -> None:
        with suspended_updates(self.list):
            self.list.clear()
            tracks = self._library.tracks
            q = (text or "").strip().lower()
            self.list.setUniformItemSizes(not bool(q))
            if not q:
                self._add_song_rows(tracks)
                return

            artist_rows, album_rows, song_rows = _group_search_results(tracks, q)
            self._add_artist_rows(artist_rows)
            self._add_album_rows(album_rows)
            self._add_header(tr("song_header", n=len(song_rows)))
            self._add_song_rows(song_rows)

    def _add_artist_rows(self, rows) -> None:
        self._add_header(tr("artist_header", n=len(rows)))
        unknown_album = tr("unknown_album")
        for artist, tracks in rows:
            album_count = len(
                {
                    (track.album or unknown_album).strip() or unknown_album
                    for track in tracks
                }
            )
            self._add_result_item(
                "artist",
                artist,
                tr("album_track_count", albums=album_count, tracks=len(tracks)),
                tracks[0].path if tracks else "",
                [track.path for track in tracks],
            )

    def _add_album_rows(self, rows) -> None:
        self._add_header(tr("album_header", n=len(rows)))
        for album, artist, tracks in rows:
            self._add_result_item(
                "album",
                album,
                tr("artist_track_count", artist=artist, tracks=len(tracks)),
                tracks[0].path if tracks else "",
                [track.path for track in tracks],
                data=album,
            )

    def _add_song_rows(self, tracks) -> None:
        for t in tracks:
            self._add_result_item(
                "song",
                t.title or "",
                f"{t.artist or ''} - {t.album or ''}".strip(" -"),
                t.path,
                [t.path],
                is_hr=t.is_high_res(),
            )

    def _add_header(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setData(ROLE_SECTION_HEADER, True)
        self.list.addItem(item)

    def _add_result_item(
        self,
        kind: str,
        title: str,
        subtitle: str,
        thumb_source_path: str,
        paths: List[str],
        *,
        data: Optional[str] = None,
        is_hr: bool = False,
    ) -> None:
        item = QListWidgetItem(title)
        item.setData(
            Qt.ItemDataRole.UserRole,
            data
            if data is not None
            else title
            if kind != "song"
            else (paths[0] if paths else ""),
        )
        item.setData(self._ROLE_RESULT_KIND, kind)
        item.setData(self._ROLE_RESULT_PATHS, paths)
        item.setData(
            ROLE_THUMB_PATH,
            thumb_path_for(thumb_source_path) if thumb_source_path else "",
        )
        item.setData(ROLE_SUBTITLE, subtitle)
        item.setData(ROLE_IS_HR, is_hr)
        self.list.addItem(item)

    def _on_scan_started(self) -> None:
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat(tr("scanning"))
        self.btn_scan.setEnabled(False)

    def _on_scan_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress.setFormat(tr("scan_progress", done=done, total=total))

    def _on_scan_finished(self) -> None:
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)

    def _selected_paths(self) -> List[str]:
        items = self.list.selectedItems() or (
            [self.list.currentItem()] if self.list.currentItem() else []
        )
        paths: List[str] = []
        for item in items:
            if item.data(self._ROLE_RESULT_KIND) != "song":
                continue
            p = item.data(Qt.ItemDataRole.UserRole)
            if p:
                paths.append(p)
        return paths

    def _on_double_click(self, item: QListWidgetItem) -> None:
        kind = item.data(self._ROLE_RESULT_KIND)
        if kind == "artist":
            artist = item.data(Qt.ItemDataRole.UserRole)
            if artist:
                self.open_artist_requested.emit(artist)
            return
        if kind == "album":
            album = item.data(Qt.ItemDataRole.UserRole)
            if album:
                self.open_album_requested.emit(album)
            return
        if kind != "song":
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return

        visible_paths, start_index = self._visible_song_paths(path)
        if visible_paths:
            self.play_paths_now.emit(visible_paths, start_index)
        else:
            self.play_paths_now.emit([path], 0)

    def _visible_song_paths(self, selected_path: str) -> tuple[List[str], int]:
        paths: List[str] = []
        selected_index = 0
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(self._ROLE_RESULT_KIND) != "song":
                continue
            path = item.data(Qt.ItemDataRole.UserRole)
            if not path:
                continue
            if path == selected_path:
                selected_index = len(paths)
            paths.append(path)
        return paths, selected_index

    def _on_context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        self.list.setCurrentItem(item)
        kind = item.data(self._ROLE_RESULT_KIND)
        menu = QMenu(self)
        a_open = None
        a_play = a_enq = a_add = None
        if kind == "artist":
            a_open = menu.addAction(tr("open_artist"))
        elif kind == "album":
            a_open = menu.addAction(tr("open_album"))
        elif kind == "song":
            a_play = menu.addAction(tr("play_now"))
            a_enq = menu.addAction(tr("enqueue"))
            a_add = menu.addAction(tr("add_to_playlist"))
        else:
            return
        act = menu.exec(self.list.mapToGlobal(pos))
        if act == a_open:
            self._on_double_click(item)
            return
        paths = self._selected_paths()
        if not paths:
            return
        if act == a_play:
            self.play_paths_now.emit(paths, 0)
        elif act == a_enq:
            self.enqueue_paths.emit(paths)
        elif act == a_add:
            self.add_paths_to_playlist.emit(paths)

    def _apply_filter(self, text: str) -> None:
        self._rebuild_results(text)

    def retranslate(self) -> None:
        self.title_label.setText(tr("library"))
        self.search.setPlaceholderText(tr("search_library"))
        self.btn_scan.setText(tr("scan_library"))
        self.refresh()


def _group_search_results(tracks, query: str):
    artists = defaultdict(list)
    albums = defaultdict(list)
    unknown_artist = tr("unknown_artist")
    unknown_album = tr("unknown_album")

    for track in tracks:
        artist = (track.artist or unknown_artist).strip() or unknown_artist
        album = (track.album or unknown_album).strip() or unknown_album
        artists[artist].append(track)
        albums[(album, artist)].append(track)

    artist_rows = [
        (artist, sorted(items, key=_artist_track_sort_key))
        for artist, items in artists.items()
        if query in artist.lower()
    ]
    album_rows = [
        (album, artist, sorted(items, key=_album_track_sort_key))
        for (album, artist), items in albums.items()
        if query in album.lower() or query in artist.lower()
    ]
    song_rows = [
        track
        for track in tracks
        if query
        in f"{track.title or ''} {track.artist or ''} {track.album or ''}".lower()
    ]

    artist_rows.sort(key=lambda row: row[0].lower())
    album_rows.sort(key=lambda row: (row[0].lower(), row[1].lower()))
    song_rows.sort(key=_song_search_sort_key)
    return artist_rows, album_rows, song_rows


def _track_number_or_last(track) -> int:
    return track.track_number if track.track_number > 0 else 9999


def _artist_track_sort_key(track) -> tuple:
    return track.album or "", _track_number_or_last(track), track.title or ""


def _album_track_sort_key(track) -> tuple:
    return _track_number_or_last(track), track.title or ""


def _song_search_sort_key(track) -> tuple:
    return (
        (track.artist or "").lower(),
        (track.album or "").lower(),
        _track_number_or_last(track),
        (track.title or "").lower(),
    )
