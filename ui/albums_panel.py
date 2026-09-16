import os
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.library import Library
from core.metadata import TrackMetadata
from core.thumbnails import thumb_path_for
from ui.i18n import tr
from ui.list_delegates import (
    ROLE_IS_HR,
    ROLE_SUBTITLE,
    ROLE_THUMB_PATH,
)
from ui.list_helpers import (
    add_list_header,
    connect_debounced_filter,
    cover_list,
    filter_items_by_text,
    suspended_updates,
    track_item,
)
from ui.theme import PRIMARY_BTN_QSS


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._text = text
        sp = QSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred
        )
        self.setSizePolicy(sp)
        self.setMinimumWidth(10)

    def setText(self, text: str) -> None:
        self._text = text
        super().setText(text)
        self.update()

    def text(self) -> str:
        return getattr(self, "_text", super().text())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        metrics = self.fontMetrics()
        elided = metrics.elidedText(
            self._text, Qt.TextElideMode.ElideRight, self.width()
        )
        painter.drawText(self.rect(), self.alignment(), elided)


class AlbumsPanel(QWidget):
    play_paths_sequential = pyqtSignal(list, int)
    play_paths_shuffled = pyqtSignal(list)
    enqueue_paths = pyqtSignal(list)
    play_next_paths = pyqtSignal(list)
    add_paths_to_playlist = pyqtSignal(list)
    back_to_artists_requested = pyqtSignal()

    def __init__(
        self, library: Library, parent: Optional[QWidget] = None, embedded: bool = False
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._embedded = embedded
        self._filter_artist: Optional[str] = None
        self._albums_tracks: Dict[str, List[TrackMetadata]] = {}
        self._build_ui()
        self._wire()
        self.refresh()

    def set_artist_filter(self, artist: str) -> None:
        self._filter_artist = artist
        if self._embedded:
            self.lbl_embedded_title.setText(artist)
        self.stack.setCurrentIndex(0)
        self.refresh()

    def _build_ui(self) -> None:
        self.stack = QStackedWidget(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)

        self.page_list = QWidget()
        l0 = QVBoxLayout(self.page_list)
        l0.setContentsMargins(20, 16, 20, 16)
        l0.setSpacing(10)

        if self._embedded:
            (
                self.lbl_artist_cover,
                self.lbl_embedded_title,
                self.lbl_embedded_subtitle,
            ) = _add_detail_header(l0, spacing=17)

            h0 = QHBoxLayout()
            h0.addStretch()
            self.album_count = QLabel("0")
            self.album_count.setStyleSheet("color: #9E9E9E;")
            h0.addWidget(self.album_count)
            l0.addLayout(h0)
        else:
            self.title_label, self.album_count = add_list_header(l0, tr("albums"), "0")

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("search_albums"))
        self.search_box.setClearButtonEnabled(True)

        if self._embedded:
            self.search_box.setVisible(False)

        l0.addWidget(self.search_box)

        self.list_albums = cover_list()
        l0.addWidget(self.list_albums)

        if self._embedded:
            h_bottom = QHBoxLayout()
            self.btn_back_group = QPushButton(tr("back"))
            self.btn_back_group.setStyleSheet(PRIMARY_BTN_QSS)
            self.btn_back_group.setCursor(Qt.CursorShape.PointingHandCursor)
            h_bottom.addWidget(self.btn_back_group)
            h_bottom.addStretch()
            self.btn_shuffle_artist = QPushButton(tr("shuffle_play"))
            self.btn_shuffle_artist.setStyleSheet(PRIMARY_BTN_QSS)
            self.btn_shuffle_artist.setCursor(Qt.CursorShape.PointingHandCursor)
            h_bottom.addWidget(self.btn_shuffle_artist)
            l0.addLayout(h_bottom)

        self.stack.addWidget(self.page_list)

        self.page_detail = QWidget()
        l1 = QVBoxLayout(self.page_detail)
        l1.setContentsMargins(20, 16, 20, 16)
        l1.setSpacing(10)

        (
            self.lbl_album_cover,
            self.lbl_album_title,
            self.lbl_album_artist,
        ) = _add_detail_header(l1, spacing=16)

        self.list_tracks = cover_list()
        self.list_tracks.setSelectionMode(self.list_tracks.SelectionMode.ExtendedSelection)
        self.list_tracks.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        l1.addWidget(self.list_tracks)

        h_back = QHBoxLayout()
        self.btn_back = QPushButton(tr("back"))
        self.btn_back.setStyleSheet(PRIMARY_BTN_QSS)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        h_back.addWidget(self.btn_back)
        h_back.addStretch()

        self.btn_play_all = QPushButton(tr("sequential_play"))
        self.btn_play_all.setStyleSheet(PRIMARY_BTN_QSS)
        self.btn_play_all.setCursor(Qt.CursorShape.PointingHandCursor)
        h_back.addWidget(self.btn_play_all)
        l1.addLayout(h_back)

        self.stack.addWidget(self.page_detail)

    def _wire(self) -> None:
        self._library.tracks_changed.connect(self.refresh)
        self._search_timer = connect_debounced_filter(
            self, self.search_box, self._apply_filter
        )
        self.list_albums.itemClicked.connect(self._on_album_clicked)
        if self._embedded:
            self.btn_back_group.clicked.connect(self._on_back_to_artists)
            self.btn_shuffle_artist.clicked.connect(self._on_shuffle_artist)
        self.btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.list_tracks.itemDoubleClicked.connect(self._on_track_clicked)
        self.btn_play_all.clicked.connect(self._on_play_all)
        self.list_tracks.customContextMenuRequested.connect(self._on_track_context_menu)

    def refresh(self) -> None:
        self._albums_tracks = _group_tracks_by_album(
            self._library.tracks, self._filter_artist
        )
        albums = sorted(self._albums_tracks)
        self._populate_album_list(albums)
        if self._embedded and self._filter_artist:
            self._set_artist_cover()

        self.album_count.setText(tr("albums_count", n=len(albums)))
        if self._embedded:
            self.album_count.setVisible(False)
            self.lbl_embedded_subtitle.setText(tr("albums_count", n=len(albums)))

        self._apply_filter(self.search_box.text())

    def _populate_album_list(self, albums: List[str]) -> None:
        with suspended_updates(self.list_albums):
            self.list_albums.clear()
            for album in albums:
                item = QListWidgetItem(album)
                item.setData(Qt.ItemDataRole.UserRole, album)
                tracks = self._albums_tracks[album]
                if tracks:
                    item.setData(ROLE_THUMB_PATH, thumb_path_for(tracks[0].path))
                    item.setData(ROLE_SUBTITLE, tracks[0].artist or "")
                    item.setData(ROLE_IS_HR, all(t.is_high_res() for t in tracks))
                self.list_albums.addItem(item)

    def _set_artist_cover(self) -> None:
        pixmap = _first_album_cover(self._albums_tracks)
        _set_cover_label(self.lbl_artist_cover, pixmap, "No\nCover")

    def _apply_filter(self, text: str) -> None:
        filter_items_by_text(self.list_albums, text)

    def show_album(self, album: str) -> None:
        self._current_album = album
        self.lbl_album_title.setText(album)
        tracks = self._albums_tracks.get(album, [])
        artist_name = (
            tracks[0].artist if tracks and tracks[0].artist else tr("unknown_artist")
        )
        self.lbl_album_artist.setText(artist_name)
        cover_pixmap = _cover_pixmap(tracks[0].path) if tracks else None
        _set_cover_label(self.lbl_album_cover, cover_pixmap, tr("no_cover"))

        with suspended_updates(self.list_tracks):
            self.list_tracks.clear()
            for track in tracks:
                self.list_tracks.addItem(track_item(track, track.path))

        self.stack.setCurrentIndex(1)

    def _on_album_clicked(self, item: QListWidgetItem) -> None:
        album = item.data(Qt.ItemDataRole.UserRole)
        self.show_album(album)

    def _on_back_to_artists(self) -> None:
        self._filter_artist = None
        self.back_to_artists_requested.emit()

    def _on_shuffle_artist(self) -> None:
        paths = [
            t.path
            for album in sorted(self._albums_tracks.keys())
            for t in self._albums_tracks[album]
        ]
        if paths:
            self.play_paths_shuffled.emit(paths)

    def _on_track_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        album = getattr(self, "_current_album", "")
        tracks = self._albums_tracks.get(album, [])
        try:
            track_idx = next(i for i, t in enumerate(tracks) if t.path == path)
        except StopIteration:
            track_idx = 0
        self._play_from_album(album, track_idx)

    def _on_track_context_menu(self, pos) -> None:
        item = self.list_tracks.itemAt(pos)
        if item is None:
            return
        if not item.isSelected():
            self.list_tracks.setCurrentItem(item)
        paths = [self.list_tracks.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.list_tracks.count())
                 if self.list_tracks.item(i).isSelected()]
        menu = QMenu(self)
        play_next = menu.addAction(tr("play_next"))
        play_last = menu.addAction(tr("play_last"))
        action = menu.exec(self.list_tracks.viewport().mapToGlobal(pos))
        if action == play_next:
            self.play_next_paths.emit(paths)
        elif action == play_last:
            self.enqueue_paths.emit(paths)

    def _on_play_all(self) -> None:
        album = getattr(self, "_current_album", "")
        if album in self._albums_tracks:
            self._play_from_album(album, 0)

    def _play_from_album(self, album: str, track_index: int) -> None:
        """Play within the current album."""
        tracks = self._albums_tracks.get(album, [])
        if not tracks:
            return
        paths = [t.path for t in tracks]
        play_idx = max(0, min(track_index, len(paths) - 1))
        self.play_paths_sequential.emit(paths, play_idx)

    def retranslate(self) -> None:
        if not self._embedded and hasattr(self, "title_label"):
            self.title_label.setText(tr("albums"))
        self.search_box.setPlaceholderText(tr("search_albums"))
        if hasattr(self, "btn_back_group"):
            self.btn_back_group.setText(tr("back"))
        if hasattr(self, "btn_shuffle_artist"):
            self.btn_shuffle_artist.setText(tr("shuffle_play"))
        self.btn_back.setText(tr("back"))
        self.btn_play_all.setText(tr("sequential_play"))
        self.refresh()


def _group_tracks_by_album(
    tracks: List[TrackMetadata], artist_filter: Optional[str]
) -> Dict[str, List[TrackMetadata]]:
    albums: Dict[str, List[TrackMetadata]] = {}
    unknown_artist = tr("unknown_artist")
    unknown_album = tr("unknown_album")
    for track in tracks:
        artist = track.artist.strip() if track.artist else unknown_artist
        if artist_filter and artist != artist_filter:
            continue
        album = track.album.strip() if track.album else unknown_album
        albums.setdefault(album, []).append(track)

    for album_tracks in albums.values():
        album_tracks.sort(
            key=lambda track: (
                track.track_number if track.track_number > 0 else 9999,
                track.title or "",
            )
        )
    return albums


def _cover_pixmap(path: str) -> Optional[QPixmap]:
    thumbnail = thumb_path_for(path)
    if not os.path.isfile(thumbnail) or os.path.getsize(thumbnail) <= 0:
        return None
    pixmap = QPixmap(thumbnail)
    if pixmap.isNull():
        return None
    return pixmap.scaled(
        80,
        80,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )


def _first_album_cover(
    albums: Dict[str, List[TrackMetadata]],
) -> Optional[QPixmap]:
    for tracks in albums.values():
        if tracks:
            pixmap = _cover_pixmap(tracks[0].path)
            if pixmap is not None:
                return pixmap
    return None


def _set_cover_label(label: QLabel, pixmap: Optional[QPixmap], fallback: str) -> None:
    if pixmap is not None:
        label.setPixmap(pixmap)
        return
    label.clear()
    label.setText(fallback)


def _add_detail_header(layout: QVBoxLayout, *, spacing: int) -> tuple:
    """Build the matching artist/album headers with their original spacing."""
    row = QHBoxLayout()
    row.setSpacing(spacing)
    cover = QLabel()
    cover.setFixedSize(80, 80)
    cover.setStyleSheet("background-color: #222; border-radius: 4px;")
    cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
    row.addWidget(cover)

    texts = QVBoxLayout()
    texts.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    texts.setContentsMargins(0, 0, 0, 8)
    texts.setSpacing(5)
    title, subtitle = ElidedLabel(""), ElidedLabel("")
    for label, size, bold, style in (
        (title, 17, True, "font-size: 17pt; font-weight: bold;"),
        (subtitle, 13, False, "color: #AAA; font-size: 13pt;"),
    ):
        font = QFont()
        font.setPointSize(size)
        if bold:
            font.setBold(True)
        label.setFont(font)
        label.setStyleSheet(style)
        texts.addWidget(label)
    row.addLayout(texts)
    row.addStretch()
    layout.addLayout(row)
    return cover, title, subtitle
