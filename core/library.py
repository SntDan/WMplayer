"""Music library scanning and metadata cache."""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from core.metadata import TrackMetadata, is_supported, read_metadata
from core.thumbnails import ensure_thumb, thumb_exists


class _ScanSignals(QObject):
    progress = pyqtSignal(int, int)  # done, total
    finished = pyqtSignal(list)  # List[TrackMetadata]


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
        files = _discover_audio_files(self._folders)
        results: List[TrackMetadata] = []
        total = len(files)
        for i, path in enumerate(files):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            metadata = _metadata_for_scan(path, mtime, self._cache.get(path))
            if metadata is None:
                continue
            results.append(metadata)

            if (i + 1) % 25 == 0 or (i + 1) == total:
                self._signals.progress.emit(i + 1, total)
            if (i + 1) % 10 == 0:
                time.sleep(0.001)

        results.sort(
            key=lambda t: (
                (t.title or "").lower(),
                (t.artist or "").lower(),
            )
        )
        self._signals.finished.emit(results)


def _discover_audio_files(folders: List[str]) -> List[str]:
    """Return supported files from the configured folders without duplicates."""
    files: List[str] = []
    seen = set()
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for root, _dirs, names in os.walk(folder):
            for name in names:
                path = os.path.join(root, name)
                if path in seen or not is_supported(path):
                    continue
                seen.add(path)
                files.append(path)
    return files


def _metadata_for_scan(
    path: str,
    mtime: float,
    cached: Optional[dict],
) -> Optional[TrackMetadata]:
    """Load one scan result, reusing cache data and creating its thumbnail."""
    needs_thumbnail = not thumb_exists(path)
    if _cache_entry_is_current(cached, mtime):
        metadata = _metadata_from_cache(path, cached)
        if needs_thumbnail:
            _create_thumbnail(path)
        return metadata

    try:
        metadata = read_metadata(path, with_cover=needs_thumbnail)
        if needs_thumbnail:
            ensure_thumb(path, metadata.cover)
            metadata.cover = None
        return metadata
    except Exception:
        return None


def _cache_entry_is_current(cached: Optional[dict], mtime: float) -> bool:
    return bool(
        cached and abs(cached.get("mtime", 0) - mtime) < 1 and "track_number" in cached
    )


_TEXT_FIELDS = ("title", "artist", "album")
_INTEGER_FIELDS = ("duration_ms", "sample_rate", "bits_per_sample", "track_number")


def _metadata_from_cache(path: str, cached: dict) -> TrackMetadata:
    return TrackMetadata(
        path=path,
        **{name: cached.get(name, "") for name in _TEXT_FIELDS},
        **{name: int(cached.get(name, 0)) for name in _INTEGER_FIELDS},
    )


def _metadata_to_cache(track: TrackMetadata, mtime: float) -> dict:
    """Keep disk and scan cache fields identical, excluding in-memory covers."""
    return {
        **{name: getattr(track, name) for name in (*_TEXT_FIELDS, *_INTEGER_FIELDS)},
        "mtime": mtime,
    }


def _create_thumbnail(path: str) -> None:
    try:
        metadata = read_metadata(path, with_cover=True)
        ensure_thumb(path, metadata.cover)
    except Exception:
        pass


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
        self._display_tracks: List[TrackMetadata] = []
        self._path_map: Optional[Dict[str, TrackMetadata]] = None
        self._scanning = False
        self._signals = _ScanSignals(self)
        self._signals.progress.connect(self.scan_progress.emit)
        self._signals.finished.connect(self._on_scan_finished)
        self._load_cache()
        self._rebuild_display()

    @property
    def folders(self) -> List[str]:
        return list(self._folders)

    @property
    def tracks(self) -> List[TrackMetadata]:
        return self._display_tracks

    def __len__(self) -> int:
        return len(self._display_tracks)

    def find_by_path(self, path: str) -> Optional[TrackMetadata]:
        if self._path_map is None:
            self._path_map = {t.path: t for t in self._tracks}
        return self._path_map.get(path)

    def _rebuild_display(self) -> None:
        """Build the deduplicated library view."""
        best: Dict[tuple, TrackMetadata] = {}
        for t in self._tracks:
            key = (
                (t.title or "").strip().lower(),
                (t.artist or "").strip().lower(),
                (t.album or "").strip().lower(),
            )
            if key not in best or _spec_score(t) > _spec_score(best[key]):
                best[key] = t
        self._display_tracks = list(best.values())

    def set_folders(self, folders: List[str]) -> None:
        self._folders = list(dict.fromkeys(os.path.abspath(f) for f in folders if f))
        self.folders_changed.emit()

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
        self._path_map = None  # Invalidate the path index.
        self._rebuild_display()
        self._scanning = False
        self._save_cache()
        self.tracks_changed.emit()
        self.scan_finished.emit()

    def _build_cache_dict(self) -> Dict[str, dict]:
        cache: Dict[str, dict] = {}
        for t in self._tracks:
            try:
                mtime = os.path.getmtime(t.path)
            except OSError:
                continue
            cache[t.path] = _metadata_to_cache(t, mtime)
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
            self._tracks.append(_metadata_from_cache(path, entry))

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            data = {
                "folders": list(self._folders),
                "tracks": [
                    {
                        "path": t.path,
                        **_metadata_to_cache(t, _safe_mtime(t.path)),
                    }
                    for t in self._tracks
                ],
            }
            tmp = self._cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._cache_path)
        except Exception:
            pass


def _safe_mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _spec_score(t: TrackMetadata) -> tuple:
    """Return a quality score used for duplicate selection."""
    return (
        1 if t.is_high_res() else 0,
        t.bits_per_sample or 0,
        t.sample_rate or 0,
        t.duration_ms or 0,
    )
