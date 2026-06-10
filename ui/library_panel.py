"""
曲库视图
========
显示扫描到的所有曲目。可以统一搜索歌手/专辑/歌曲,双击播放或跳转。
顶部有"扫描曲库"按钮和扫描进度条。
"""

from __future__ import annotations

from collections import defaultdict
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
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
from ui.list_delegates import (
    CoverRowDelegate,
    ROLE_IS_HR,
    ROLE_SECTION_HEADER,
    ROLE_SUBTITLE,
    ROLE_THUMB_PATH,
)
from ui.theme import BTN_QSS as _BTN_QSS


class LibraryPanel(QWidget):

    # 用户操作信号 (path 或 path 列表)
    play_paths_now = pyqtSignal(list, int)           # 立即替换队列并播放第 N 首
    enqueue_paths = pyqtSignal(list)               # 追加到队列尾
    add_paths_to_playlist = pyqtSignal(list)       # 弹出选择对话框 → 加入某个歌单
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

        # 标题 + 计数
        header = QHBoxLayout()
        title = QLabel("曲库")
        f = QFont(); f.setPointSize(15); f.setBold(True); title.setFont(f)
        self.count_label = QLabel("0 首")
        self.count_label.setStyleSheet("color: #9E9E9E;")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        outer.addLayout(header)

        # 操作行: 搜索 + 扫描
        action_row = QHBoxLayout()
        action_row.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索歌手 / 专辑 / 歌曲")
        self.search.setClearButtonEnabled(True)
        action_row.addWidget(self.search, 1)

        self.btn_scan = QPushButton("扫描曲库")
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scan.setStyleSheet(_BTN_QSS)
        action_row.addWidget(self.btn_scan)
        outer.addLayout(action_row)

        # 扫描进度
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet(
            "QProgressBar{border:1px solid #333; border-radius:3px; "
            "background:#1a1a1a; height:14px; text-align:center;}"
            "QProgressBar::chunk{background:#E63946; border-radius:2px;}"
        )
        outer.addWidget(self.progress)

        # 列表
        self.list = QListWidget()
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setUniformItemSizes(False)
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._row_delegate = CoverRowDelegate(self.list)
        self.list.setItemDelegate(self._row_delegate)
        outer.addWidget(self.list, 1)

    def _wire(self) -> None:
        self._library.tracks_changed.connect(self.refresh)
        self._library.scan_started.connect(self._on_scan_started)
        self._library.scan_progress.connect(self._on_scan_progress)
        self._library.scan_finished.connect(self._on_scan_finished)
        self.btn_scan.clicked.connect(self.rescan_requested.emit)
        self.search.textChanged.connect(self._apply_filter)
        self.list.itemDoubleClicked.connect(self._on_double_click)
        self.list.customContextMenuRequested.connect(self._on_context_menu)

    # ------------------------------------------------------------------
    # 数据
    # ------------------------------------------------------------------
    _ROLE_RESULT_KIND = Qt.ItemDataRole.UserRole + 10
    _ROLE_RESULT_PATHS = Qt.ItemDataRole.UserRole + 11
    _ROLE_FILTER_HAY = Qt.ItemDataRole.UserRole + 12

    def refresh(self) -> None:
        self.count_label.setText(f"{len(self._library.tracks)} 首")
        self._rebuild_results(self.search.text())

    def _rebuild_results(self, text: str) -> None:
        self.list.clear()
        tracks = self._library.tracks
        q = (text or "").strip().lower()
        if not q:
            self._add_song_rows(tracks)
            return

        artists = defaultdict(list)
        albums = defaultdict(list)
        for t in tracks:
            artist = (t.artist or "未知歌手").strip() or "未知歌手"
            album = (t.album or "未知专辑").strip() or "未知专辑"
            artists[artist].append(t)
            albums[(album, artist)].append(t)

        artist_rows = [
            (artist, sorted(items, key=lambda t: ((t.album or ""), (t.track_number if t.track_number > 0 else 9999), t.title or "")))
            for artist, items in artists.items()
            if not q or q in artist.lower()
        ]
        album_rows = [
            (album, artist, sorted(items, key=lambda t: (t.track_number if t.track_number > 0 else 9999, t.title or "")))
            for (album, artist), items in albums.items()
            if not q or q in album.lower() or q in artist.lower()
        ]
        song_rows = [
            t for t in tracks
            if not q or q in f"{t.title or ''} {t.artist or ''} {t.album or ''}".lower()
        ]

        artist_rows.sort(key=lambda row: row[0].lower())
        album_rows.sort(key=lambda row: (row[0].lower(), row[1].lower()))
        song_rows.sort(key=lambda t: ((t.artist or "").lower(), (t.album or "").lower(), t.track_number if t.track_number > 0 else 9999, (t.title or "").lower()))

        self._add_header(f"歌手 ({len(artist_rows)})")
        for artist, items in artist_rows:
            albums_count = len({(t.album or "未知专辑").strip() or "未知专辑" for t in items})
            self._add_result_item(
                "artist",
                artist,
                f"{albums_count} 张专辑 · {len(items)} 首",
                items[0].path if items else "",
                [t.path for t in items],
            )

        self._add_header(f"专辑 ({len(album_rows)})")
        for album, artist, items in album_rows:
            self._add_result_item(
                "album",
                album,
                f"{artist} · {len(items)} 首",
                items[0].path if items else "",
                [t.path for t in items],
                data=album,
            )

        self._add_header(f"歌曲 ({len(song_rows)})")
        self._add_song_rows(song_rows)

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
        item.setData(Qt.ItemDataRole.UserRole, data if data is not None else title if kind != "song" else (paths[0] if paths else ""))
        item.setData(self._ROLE_RESULT_KIND, kind)
        item.setData(self._ROLE_RESULT_PATHS, paths)
        item.setData(ROLE_THUMB_PATH, thumb_path_for(thumb_source_path) if thumb_source_path else "")
        item.setData(ROLE_SUBTITLE, subtitle)
        item.setData(ROLE_IS_HR, is_hr)
        hay = f"{title} {subtitle}".lower()
        item.setData(self._ROLE_FILTER_HAY, hay)
        self.list.addItem(item)

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def _on_scan_started(self) -> None:
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat("正在扫描…")
        self.btn_scan.setEnabled(False)

    def _on_scan_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
            self.progress.setFormat(f"扫描中 {done}/{total}")

    def _on_scan_finished(self) -> None:
        self.progress.setVisible(False)
        self.btn_scan.setEnabled(True)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------
    def _selected_paths(self) -> List[str]:
        items = self.list.selectedItems() or ([self.list.currentItem()] if self.list.currentItem() else [])
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

        visible_paths: List[str] = []
        start_index = 0
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(self._ROLE_RESULT_KIND) != "song":
                continue
            p = it.data(Qt.ItemDataRole.UserRole)
            if p:
                if p == path:
                    start_index = len(visible_paths)
                visible_paths.append(p)
        
        if visible_paths:
            self.play_paths_now.emit(visible_paths, start_index)
        else:
            self.play_paths_now.emit([path], 0)

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
            a_open = menu.addAction("打开歌手")
        elif kind == "album":
            a_open = menu.addAction("打开专辑")
        elif kind == "song":
            a_play = menu.addAction("立即播放(替换队列)")
            a_enq = menu.addAction("加入播放队列")
            a_add = menu.addAction("加入歌单…")
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
