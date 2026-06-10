from typing import List, Optional, Dict
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget, QStackedWidget
)
from core.library import Library
from core.metadata import TrackMetadata
from core.thumbnails import thumb_path_for
from ui.list_delegates import CoverRowDelegate, ROLE_SUBTITLE, ROLE_THUMB_PATH

class ArtistsPanel(QWidget):
    play_paths_now = pyqtSignal(list, int)
    play_paths_sequential = pyqtSignal(list, int)
    play_paths_shuffled = pyqtSignal(list)
    enqueue_paths = pyqtSignal(list)
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
        
        h0 = QHBoxLayout()
        title0 = QLabel("歌手")
        f = QFont(); f.setPointSize(15); f.setBold(True); title0.setFont(f)
        h0.addWidget(title0)
        h0.addStretch()
        self.artist_count = QLabel("0")
        self.artist_count.setStyleSheet("color: #9E9E9E;")
        h0.addWidget(self.artist_count)
        l0.addLayout(h0)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索歌手...")
        self.search_box.setClearButtonEnabled(True)
        l0.addWidget(self.search_box)

        self.list_artists = QListWidget()
        self.list_artists.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list_artists.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_artists.setUniformItemSizes(True)
        self.list_artists.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_artists.setMouseTracking(True)
        self._row_delegate = CoverRowDelegate(self.list_artists)
        self.list_artists.setItemDelegate(self._row_delegate)
        l0.addWidget(self.list_artists)
        self.stack.addWidget(self.page_list)

        from .albums_panel import AlbumsPanel
        self.albums_subpanel = AlbumsPanel(library=self._library, embedded=True)
        self.albums_subpanel.play_paths_now.connect(self.play_paths_now.emit)
        self.albums_subpanel.play_paths_sequential.connect(self.play_paths_sequential.emit)
        self.albums_subpanel.play_paths_shuffled.connect(self.play_paths_shuffled.emit)
        self.albums_subpanel.enqueue_paths.connect(self.enqueue_paths.emit)
        self.albums_subpanel.add_paths_to_playlist.connect(self.add_paths_to_playlist.emit)
        self.albums_subpanel.back_to_artists_requested.connect(lambda: self.stack.setCurrentIndex(0))
        self.stack.addWidget(self.albums_subpanel)

    def _wire(self) -> None:
        self._library.tracks_changed.connect(self.refresh)
        self.search_box.textChanged.connect(self._apply_filter)
        # 单信号: 单击进入(避免双击触发两次重复加载)
        self.list_artists.itemClicked.connect(self._on_artist_clicked)

    def refresh(self) -> None:
        self._artists_tracks.clear()
        for t in self._library.tracks:
            artist = t.artist.strip() if t.artist else "未知歌手"
            if artist not in self._artists_tracks:
                self._artists_tracks[artist] = []
            self._artists_tracks[artist].append(t)

        # 按照专辑排序，保证“一个一个专辑播放”
        for artist in self._artists_tracks:
            self._artists_tracks[artist].sort(key=lambda t: (t.album or "", t.title or ""))

        self.list_artists.clear()
        artists = sorted(self._artists_tracks.keys())
        for a in artists:
            tracks = self._artists_tracks[a]
            it = QListWidgetItem(a)
            it.setData(Qt.ItemDataRole.UserRole, a)
            if tracks:
                # 用该歌手「首张专辑」首曲的封面缩略图
                it.setData(ROLE_THUMB_PATH, thumb_path_for(tracks[0].path))
                # 副标题: 该歌手有几张专辑
                album_count = len({t.album for t in tracks})
                it.setData(ROLE_SUBTITLE, f"{album_count} 张专辑")
            self.list_artists.addItem(it)

        self.artist_count.setText(f"{len(artists)} 位歌手")
        self._apply_filter(self.search_box.text())

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for i in range(self.list_artists.count()):
            it = self.list_artists.item(i)
            artist = it.data(Qt.ItemDataRole.UserRole)
            if not text:
                it.setHidden(False)
            else:
                it.setHidden(text not in artist.lower())

    def show_artist(self, artist: str) -> None:
        self._current_artist = artist
        self.albums_subpanel.set_artist_filter(artist)
        self.stack.setCurrentIndex(1)

    def _on_artist_clicked(self, item: QListWidgetItem) -> None:
        artist = item.data(Qt.ItemDataRole.UserRole)
        self.show_artist(artist)
