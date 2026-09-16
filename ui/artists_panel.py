from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QLineEdit,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.library import Library
from core.metadata import TrackMetadata
from core.thumbnails import thumb_path_for
from ui.i18n import tr
from ui.list_delegates import ROLE_SUBTITLE, ROLE_THUMB_PATH
from ui.list_helpers import (
    add_list_header,
    connect_debounced_filter,
    cover_list,
    filter_items_by_text,
    suspended_updates,
)


class ArtistsPanel(QWidget):
    play_paths_sequential = pyqtSignal(list, int)
    play_paths_shuffled = pyqtSignal(list)
    enqueue_paths = pyqtSignal(list)
    play_next_paths = pyqtSignal(list)
    add_paths_to_playlist = pyqtSignal(list)

    def __init__(self, library: Library, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._library = library
        self._artists_tracks: Dict[str, List[TrackMetadata]] = {}
        self._build_ui()
        self._wire()
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

        self.title_label, self.artist_count = add_list_header(l0, tr("artists"), "0")

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("search_artists"))
        self.search_box.setClearButtonEnabled(True)
        l0.addWidget(self.search_box)

        self.list_artists = cover_list()
        l0.addWidget(self.list_artists)
        self.stack.addWidget(self.page_list)

        from .albums_panel import AlbumsPanel

        self.albums_subpanel = AlbumsPanel(library=self._library, embedded=True)
        self.albums_subpanel.play_paths_sequential.connect(
            self.play_paths_sequential.emit
        )
        self.albums_subpanel.play_paths_shuffled.connect(self.play_paths_shuffled.emit)
        self.albums_subpanel.enqueue_paths.connect(self.enqueue_paths.emit)
        self.albums_subpanel.play_next_paths.connect(self.play_next_paths.emit)
        self.albums_subpanel.add_paths_to_playlist.connect(
            self.add_paths_to_playlist.emit
        )
        self.albums_subpanel.back_to_artists_requested.connect(
            lambda: self.stack.setCurrentIndex(0)
        )
        self.stack.addWidget(self.albums_subpanel)

    def _wire(self) -> None:
        self._library.tracks_changed.connect(self.refresh)
        self._search_timer = connect_debounced_filter(
            self, self.search_box, self._apply_filter
        )
        self.list_artists.itemClicked.connect(self._on_artist_clicked)

    def refresh(self) -> None:
        self._artists_tracks.clear()
        for t in self._library.tracks:
            artist = t.artist.strip() if t.artist else tr("unknown_artist")
            self._artists_tracks.setdefault(artist, []).append(t)

        for artist in self._artists_tracks:
            self._artists_tracks[artist].sort(
                key=lambda t: (t.album or "", t.title or "")
            )

        artists = sorted(self._artists_tracks)
        with suspended_updates(self.list_artists):
            self.list_artists.clear()
            for a in artists:
                tracks = self._artists_tracks[a]
                it = QListWidgetItem(a)
                it.setData(Qt.ItemDataRole.UserRole, a)
                it.setData(ROLE_THUMB_PATH, thumb_path_for(tracks[0].path))
                album_count = len({t.album for t in tracks})
                it.setData(ROLE_SUBTITLE, tr("albums_count", n=album_count))
                self.list_artists.addItem(it)
        self.artist_count.setText(tr("artists_count", n=len(artists)))
        self._apply_filter(self.search_box.text())

    def _apply_filter(self, text: str) -> None:
        filter_items_by_text(self.list_artists, text)

    def show_artist(self, artist: str) -> None:
        self.albums_subpanel.set_artist_filter(artist)
        self.stack.setCurrentIndex(1)

    def _on_artist_clicked(self, item: QListWidgetItem) -> None:
        artist = item.data(Qt.ItemDataRole.UserRole)
        self.show_artist(artist)

    def retranslate(self) -> None:
        self.title_label.setText(tr("artists"))
        self.search_box.setPlaceholderText(tr("search_artists"))
        self.refresh()
        self.albums_subpanel.retranslate()
