"""
曲库
====
管理多个根目录,扫描出全部音频文件并缓存元数据(标题/艺术家/专辑)。

设计要点:
- 扫描在工作线程跑,通过信号汇报进度,主线程不卡
- 缓存到 library_cache.json,启动秒加载
- 增量扫描:文件 mtime 没变就直接复用缓存的元数据
- 不预读封面,封面只在播放时按需取
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from core.metadata import TrackMetadata, is_supported, read_metadata
from core.thumbnails import ensure_thumb, thumb_exists


# ----------------------------------------------------------------------
# 后台扫描
# ----------------------------------------------------------------------
class _ScanSignals(QObject):
    progress = pyqtSignal(int, int)          # done, total
    finished = pyqtSignal(list)              # List[TrackMetadata]


class _ScanRunnable(QRunnable):
    def __init__(
        self,
        folders: List[str],
        cache_by_path: Dict[str, dict],
        signals: _ScanSignals,
    ) -> None:
        super().__init__()
        self._folders = folders
        self._cache = cache_by_path
        self._signals = signals

    def run(self) -> None:
        # 1) 收集所有候选文件
        files: List[str] = []
        seen = set()
        for folder in self._folders:
            if not folder or not os.path.isdir(folder):
                continue
            for root, _dirs, fs in os.walk(folder):
                for f in fs:
                    p = os.path.join(root, f)
                    if p in seen:
                        continue
                    if is_supported(p):
                        seen.add(p)
                        files.append(p)

        # 2) 对每个文件:缓存有效就跳过 read_metadata
        results: List[TrackMetadata] = []
        total = len(files)
        for i, path in enumerate(files):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue

            cached = self._cache.get(path)
            need_thumb = not thumb_exists(path)

            if cached and abs(cached.get("mtime", 0) - mtime) < 1 and "track_number" in cached:
                md = TrackMetadata(
                    path=path,
                    title=cached.get("title", ""),
                    artist=cached.get("artist", ""),
                    album=cached.get("album", ""),
                    duration_ms=int(cached.get("duration_ms", 0)),
                    sample_rate=int(cached.get("sample_rate", 0)),
                    bits_per_sample=int(cached.get("bits_per_sample", 0)),
                    track_number=int(cached.get("track_number", 0)),
                )
                if need_thumb:
                    try:
                        cover_md = read_metadata(path, with_cover=True)
                        ensure_thumb(path, cover_md.cover)
                    except Exception:
                        pass
            else:
                try:
                    md = read_metadata(path, with_cover=need_thumb)
                    if need_thumb:
                        ensure_thumb(path, md.cover)
                        md.cover = None
                except Exception:
                    continue
            results.append(md)

            if (i + 1) % 25 == 0 or (i + 1) == total:
                self._signals.progress.emit(i + 1, total)

        # 排序:艺术家 → 专辑 → 标题
        results.sort(key=lambda t: (
            (t.artist or "").lower(),
            (t.album or "").lower(),
            (t.title or "").lower(),
        ))
        self._signals.finished.emit(results)


# ----------------------------------------------------------------------
# Library 主体
# ----------------------------------------------------------------------
class Library(QObject):

    folders_changed = pyqtSignal()
    tracks_changed = pyqtSignal()
    scan_progress = pyqtSignal(int, int)
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal()

    def __init__(self, cache_path: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._cache_path = cache_path
        self._folders: List[str] = []
        self._tracks: List[TrackMetadata] = []
        self._scanning = False
        # 扫描信号(单实例,长期存在,与 worker 安全跨线程通信)
        self._signals = _ScanSignals(self)
        self._signals.progress.connect(self.scan_progress.emit)
        self._signals.finished.connect(self._on_scan_finished)
        # 启动加载缓存
        self._load_cache()

    # ------------------------------------------------------------------
    # 数据访问
    # ------------------------------------------------------------------
    @property
    def folders(self) -> List[str]:
        return list(self._folders)

    @property
    def tracks(self) -> List[TrackMetadata]:
        return self._tracks

    def __len__(self) -> int:
        return len(self._tracks)

    def find_by_path(self, path: str) -> Optional[TrackMetadata]:
        # 优化: 改用字典缓存查找
        if not hasattr(self, "_path_map") or len(getattr(self, "_path_map", {})) != len(self._tracks):
            self._path_map = {t.path: t for t in self._tracks}
        return self._path_map.get(path)

    def search(self, query: str) -> List[TrackMetadata]:
        q = (query or "").strip().lower()
        if not q:
            return list(self._tracks)
        return [
            t for t in self._tracks
            if q in (t.title or "").lower()
            or q in (t.artist or "").lower()
            or q in (t.album or "").lower()
        ]

    # ------------------------------------------------------------------
    # 文件夹管理
    # ------------------------------------------------------------------
    def set_folders(self, folders: List[str]) -> None:
        # 去重并保持原顺序
        cleaned: List[str] = []
        seen = set()
        for f in folders:
            if not f:
                continue
            f = os.path.abspath(f)
            if f in seen:
                continue
            seen.add(f)
            cleaned.append(f)
        self._folders = cleaned
        self.folders_changed.emit()

    def add_folder(self, folder: str) -> bool:
        if not folder or not os.path.isdir(folder):
            return False
        folder = os.path.abspath(folder)
        if folder in self._folders:
            return False
        self._folders.append(folder)
        self.folders_changed.emit()
        return True

    def remove_folder(self, folder: str) -> None:
        folder = os.path.abspath(folder)
        if folder in self._folders:
            self._folders.remove(folder)
            self.folders_changed.emit()

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------
    def is_scanning(self) -> bool:
        return self._scanning

    def scan_async(self) -> None:
        if self._scanning:
            return
        self._scanning = True
        self.scan_started.emit()
        cache = self._build_cache_dict()
        worker = _ScanRunnable(list(self._folders), cache, self._signals)
        QThreadPool.globalInstance().start(worker)

    def _on_scan_finished(self, tracks) -> None:
        self._tracks = list(tracks)
        self._scanning = False
        self._save_cache()
        self.tracks_changed.emit()
        self.scan_finished.emit()

    # ------------------------------------------------------------------
    # 缓存持久化
    # ------------------------------------------------------------------
    def _build_cache_dict(self) -> Dict[str, dict]:
        cache: Dict[str, dict] = {}
        for t in self._tracks:
            try:
                mtime = os.path.getmtime(t.path)
            except OSError:
                continue
            cache[t.path] = {
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "duration_ms": t.duration_ms,
                "sample_rate": t.sample_rate,
                "bits_per_sample": t.bits_per_sample,
                "track_number": t.track_number,
                "mtime": mtime,
            }
        return cache

    def _load_cache(self) -> None:
        if not os.path.isfile(self._cache_path):
            return
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self._folders = [os.path.abspath(p) for p in data.get("folders", []) if p]
        for entry in data.get("tracks", []):
            path = entry.get("path", "")
            if not path or not os.path.isfile(path):
                continue
            self._tracks.append(TrackMetadata(
                path=path,
                title=entry.get("title", ""),
                artist=entry.get("artist", ""),
                album=entry.get("album", ""),
                duration_ms=int(entry.get("duration_ms", 0)),
                sample_rate=int(entry.get("sample_rate", 0)),
                bits_per_sample=int(entry.get("bits_per_sample", 0)),
                track_number=int(entry.get("track_number", 0)),
            ))

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            data = {
                "folders": list(self._folders),
                "tracks": [
                    {
                        "path": t.path,
                        "title": t.title,
                        "artist": t.artist,
                        "album": t.album,
                        "duration_ms": t.duration_ms,
                        "sample_rate": t.sample_rate,
                        "bits_per_sample": t.bits_per_sample,
                        "track_number": t.track_number,
                        "mtime": _safe_mtime(t.path),
                    }
                    for t in self._tracks
                ],
            }
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass


def _safe_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0
