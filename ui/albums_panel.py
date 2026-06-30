import os
from typing import List, Optional, Dict
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget, QStackedWidget, QSizePolicy
)
from core.library import Library
from core.metadata import TrackMetadata
from core.thumbnails import thumb_path_for
from ui.i18n import tr
from ui.list_delegates import CoverRowDelegate, ROLE_IS_HR, ROLE_SUBTITLE, ROLE_THUMB_PATH
from ui.theme import PRIMARY_BTN_QSS

class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self._text = text
        sp = QSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
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
        elided = metrics.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), self.alignment(), elided)

class AlbumsPanel(QWidget):
    play_paths_now = pyqtSignal(list, int)
    play_paths_sequential = pyqtSignal(list, int)
    play_paths_shuffled = pyqtSignal(list)
    enqueue_paths = pyqtSignal(list)
    add_paths_to_playlist = pyqtSignal(list)
    back_to_artists_requested = pyqtSignal()

    def __init__(self, library: Library, parent: Optional[QWidget] = None, embedded: bool = False) -> None:
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
            h_info_artist = QHBoxLayout()
            h_info_artist.setSpacing(17)
            self.lbl_artist_cover = QLabel()
            self.lbl_artist_cover.setFixedSize(80, 80)
            self.lbl_artist_cover.setStyleSheet("background-color: #222; border-radius: 4px;")
            self.lbl_artist_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h_info_artist.addWidget(self.lbl_artist_cover)

            v_texts_artist = QVBoxLayout()
            v_texts_artist.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            v_texts_artist.setContentsMargins(0, 0, 0, 8)
            v_texts_artist.setSpacing(5)
            
            self.lbl_embedded_title = ElidedLabel("")
            femb = QFont(); femb.setPointSize(17); femb.setBold(True); self.lbl_embedded_title.setFont(femb)
            self.lbl_embedded_title.setStyleSheet("font-size: 17pt; font-weight: bold;")
            v_texts_artist.addWidget(self.lbl_embedded_title)
            
            self.lbl_embedded_subtitle = ElidedLabel("")
            femb_sub = QFont(); femb_sub.setPointSize(13); self.lbl_embedded_subtitle.setFont(femb_sub)
            self.lbl_embedded_subtitle.setStyleSheet("color: #AAA; font-size: 13pt;")
            v_texts_artist.addWidget(self.lbl_embedded_subtitle)
            
            h_info_artist.addLayout(v_texts_artist)
            h_info_artist.addStretch()
            
            l0.addLayout(h_info_artist)
            
            h0 = QHBoxLayout()
            h0.addStretch()
            self.album_count = QLabel("0")
            self.album_count.setStyleSheet("color: #9E9E9E;")
            h0.addWidget(self.album_count)
            l0.addLayout(h0)
        else:
            h0 = QHBoxLayout()
            self.title_label = QLabel(tr("albums"))
            f = QFont(); f.setPointSize(15); f.setBold(True); self.title_label.setFont(f)
            h0.addWidget(self.title_label)
            h0.addStretch()
            self.album_count = QLabel("0")
            self.album_count.setStyleSheet("color: #9E9E9E;")
            h0.addWidget(self.album_count)
            l0.addLayout(h0)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("search_albums"))
        self.search_box.setClearButtonEnabled(True)
        
        if self._embedded:
            self.search_box.setVisible(False)
            
        l0.addWidget(self.search_box)

        self.list_albums = QListWidget()
        self.list_albums.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list_albums.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_albums.setUniformItemSizes(True)
        self.list_albums.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_albums.setMouseTracking(True)
        self._album_delegate = CoverRowDelegate(self.list_albums)
        self.list_albums.setItemDelegate(self._album_delegate)
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

        h_info = QHBoxLayout()
        h_info.setSpacing(16)
        self.lbl_album_cover = QLabel()
        self.lbl_album_cover.setFixedSize(80, 80)
        self.lbl_album_cover.setStyleSheet("background-color: #222; border-radius: 4px;")
        self.lbl_album_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_info.addWidget(self.lbl_album_cover)

        v_texts = QVBoxLayout()
        v_texts.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        v_texts.setContentsMargins(0, 0, 0, 8)
        v_texts.setSpacing(5)
        self.lbl_album_title = ElidedLabel("")
        f2 = QFont(); f2.setPointSize(17); f2.setBold(True); self.lbl_album_title.setFont(f2)
        self.lbl_album_title.setStyleSheet("font-size: 17pt; font-weight: bold;")
        v_texts.addWidget(self.lbl_album_title)
        
        self.lbl_album_artist = ElidedLabel("")
        f3 = QFont(); f3.setPointSize(13); self.lbl_album_artist.setFont(f3)
        self.lbl_album_artist.setStyleSheet("color: #AAA; font-size: 13pt;")
        v_texts.addWidget(self.lbl_album_artist)
        
        h_info.addLayout(v_texts)
        h_info.addStretch()
        
        l1.addLayout(h_info)

        self.list_tracks = QListWidget()
        self.list_tracks.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list_tracks.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_tracks.setUniformItemSizes(True)
        self.list_tracks.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_tracks.setMouseTracking(True)
        self._track_delegate = CoverRowDelegate(self.list_tracks)
        self.list_tracks.setItemDelegate(self._track_delegate)
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
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(90)
        self._search_timer.timeout.connect(lambda: self._apply_filter(self.search_box.text()))
        self.search_box.textChanged.connect(lambda _text: self._search_timer.start())
        # 单信号: 单击直接进详情(避免双击同时触发 click+doubleClick 重复加载封面)
        self.list_albums.itemClicked.connect(self._on_album_clicked)
        if self._embedded:
            self.btn_back_group.clicked.connect(self._on_back_to_artists)
            self.btn_shuffle_artist.clicked.connect(self._on_shuffle_artist)
        self.btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.list_tracks.itemDoubleClicked.connect(self._on_track_clicked)
        self.btn_play_all.clicked.connect(self._on_play_all)

    def refresh(self) -> None:
        self._albums_tracks.clear()
        for t in self._library.tracks:
            if self._filter_artist:
                a = t.artist.strip() if t.artist else tr("unknown_artist")
                if a != self._filter_artist:
                    continue
            album = t.album.strip() if t.album else tr("unknown_album")
            if album not in self._albums_tracks:
                self._albums_tracks[album] = []
            self._albums_tracks[album].append(t)
        
        for tracks in self._albums_tracks.values():
            tracks.sort(key=lambda t: (t.track_number if t.track_number > 0 else 9999, t.title or ""))

        self.list_albums.setUpdatesEnabled(False)
        self.list_albums.clear()
        albums = sorted(self._albums_tracks.keys())
        for a in albums:
            it = QListWidgetItem(a)
            it.setData(Qt.ItemDataRole.UserRole, a)
            tracks = self._albums_tracks.get(a, [])
            if tracks:
                it.setData(ROLE_THUMB_PATH, thumb_path_for(tracks[0].path))
                it.setData(ROLE_SUBTITLE, tracks[0].artist or "")
                it.setData(ROLE_IS_HR, all(t.is_high_res() for t in tracks))
            self.list_albums.addItem(it)
            
        self.list_albums.setUpdatesEnabled(True)

        if self._embedded and self._filter_artist:
            # 用预生成的缩略图代替同步读完整封面,避免 refresh() 阻塞 UI
            artist_cover_set = False
            for tracks in self._albums_tracks.values():
                if not tracks:
                    continue
                tp = thumb_path_for(tracks[0].path)
                if os.path.isfile(tp) and os.path.getsize(tp) > 0:
                    pix = QPixmap(tp)
                    if not pix.isNull():
                        self.lbl_artist_cover.setPixmap(
                            pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                        )
                        artist_cover_set = True
                        break
            if not artist_cover_set:
                self.lbl_artist_cover.clear()
                self.lbl_artist_cover.setText("No\nCover")
        
        self.album_count.setText(tr("albums_count", n=len(albums)))
        if self._embedded:
            self.album_count.setVisible(False)
            if hasattr(self, 'lbl_embedded_subtitle'):
                self.lbl_embedded_subtitle.setText(tr("albums_count", n=len(albums)))
                
        self._apply_filter(self.search_box.text())

    def _apply_filter(self, text: str) -> None:
        text = (text or "").strip().lower()
        for i in range(self.list_albums.count()):
            it = self.list_albums.item(i)
            album = it.data(Qt.ItemDataRole.UserRole)
            if not text:
                it.setHidden(False)
            else:
                it.setHidden(text not in album.lower())

    def show_album(self, album: str) -> None:
        self._current_album = album
        self.lbl_album_title.setText(album)
        self.list_tracks.setUpdatesEnabled(False)
        self.list_tracks.clear()
        
        tracks = self._albums_tracks.get(album, [])
        
        artist_name = tracks[0].artist if tracks and tracks[0].artist else tr("unknown_artist")
        self.lbl_album_artist.setText(artist_name)
        
        cover_pixmap = None
        if tracks:
            tp = thumb_path_for(tracks[0].path)
            if os.path.isfile(tp) and os.path.getsize(tp) > 0:
                pix = QPixmap(tp)
                if not pix.isNull():
                    cover_pixmap = pix.scaled(
                        80, 80,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )

        if cover_pixmap:
            self.lbl_album_cover.setPixmap(cover_pixmap)
        else:
            self.lbl_album_cover.clear()
            self.lbl_album_cover.setText(tr("no_cover"))
            
        for t in tracks:
            it = QListWidgetItem(t.title)
            it.setData(Qt.ItemDataRole.UserRole, t.path)
            it.setData(ROLE_THUMB_PATH, thumb_path_for(t.path))
            it.setData(ROLE_SUBTITLE, t.artist or "")
            it.setData(ROLE_IS_HR, t.is_high_res())
            self.list_tracks.addItem(it)
            
        self.list_tracks.setUpdatesEnabled(True)
        self.stack.setCurrentIndex(1)

    def _on_album_clicked(self, item: QListWidgetItem) -> None:
        album = item.data(Qt.ItemDataRole.UserRole)
        self.show_album(album)

    def _on_back_to_artists(self) -> None:
        # 切回艺术家列表前清掉过滤,避免下次再打开时残留前一位艺术家的视图
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
        self._play_from_album(album, track_idx, sequential=True)

    def _on_play_all(self) -> None:
        album = getattr(self, "_current_album", "")
        if album in self._albums_tracks:
            self._play_from_album(album, 0, sequential=True)

    def _play_from_album(self, album: str, track_index: int, *, sequential: bool = False) -> None:
        """从当前专辑内播起;队列范围始终限制在这张专辑内。"""
        tracks = self._albums_tracks.get(album, [])
        if not tracks:
            return
        paths = [t.path for t in tracks]
        play_idx = max(0, min(track_index, len(paths) - 1))
        if sequential:
            self.play_paths_sequential.emit(paths, play_idx)
        else:
            self.play_paths_now.emit(paths, play_idx)

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
