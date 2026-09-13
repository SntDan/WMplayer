"""Playlist file storage and discovery."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from core import m3u


class PlaylistStore(QObject):
    """Playlist source manager."""

    changed = pyqtSignal()

    def __init__(self, default_dir: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._default_dir = default_dir
        self._locations: List[str] = []
        try:
            os.makedirs(self._default_dir, exist_ok=True)
        except Exception:
            pass

    @property
    def default_dir(self) -> str:
        return self._default_dir

    def set_locations(self, locations: List[str]) -> None:
        self._locations = [location for location in locations if location]
        self.changed.emit()

    def _collect_entries(self) -> List[Tuple[str, str]]:
        """Collect playlist files from configured sources."""
        seen_names: set = set()
        seen_paths: set = set()
        entries: List[Tuple[str, str]] = []

        sources = self._locations
        if os.path.isdir(self._default_dir):
            sources = [self._default_dir, *sources]
        for source in sources:
            for path in _playlist_files(source):
                entry = _playlist_entry(path, seen_names, seen_paths)
                if entry is not None:
                    entries.append(entry)

        return entries

    def _name_to_path(self) -> Dict[str, str]:
        return {name: path for name, path in self._collect_entries()}

    def list_names(self) -> List[str]:
        return [name for name, _ in self._collect_entries()]

    def file_path(self, name: str) -> str:
        """Resolve or create a playlist path."""
        m = self._name_to_path()
        if name in m:
            return m[name]
        return os.path.join(self._default_dir, name + ".m3u8")

    def is_writable(self, name: str) -> bool:
        """Return whether a playlist is in the writable folder."""
        path = self._name_to_path().get(name)
        if not path:
            return False
        return os.path.dirname(path) == os.path.abspath(self._default_dir)

    def load(self, name: str) -> List[str]:
        return m3u.parse_file(self.file_path(name))

    def save(self, name: str, paths: List[str]) -> bool:
        if not name:
            return False
        safe = _safe_filename(name)
        target = os.path.join(self._default_dir, safe + ".m3u8")
        ok = m3u.write_file(target, name, paths)
        if ok:
            self.changed.emit()
        return ok

    def delete(self, name: str) -> bool:
        if not self.is_writable(name):
            return False
        path = self.file_path(name)
        if not os.path.isfile(path):
            return False
        try:
            os.remove(path)
            self.changed.emit()
            return True
        except Exception:
            return False

    def rename(self, old: str, new: str) -> bool:
        if not new or new == old:
            return False
        if not self.is_writable(old):
            return False
        old_path = self.file_path(old)
        if not os.path.isfile(old_path):
            return False
        ext = os.path.splitext(old_path)[1] or ".m3u8"
        new_path = os.path.join(self._default_dir, _safe_filename(new) + ext)
        if os.path.exists(new_path):
            return False
        try:
            os.rename(old_path, new_path)
            self.changed.emit()
            return True
        except Exception:
            return False


_INVALID_FN_CHARS = '<>:"/\\|?*'


def _safe_filename(name: str) -> str:
    s = "".join("_" if c in _INVALID_FN_CHARS else c for c in name).strip()
    return s or "untitled"


def _playlist_files(source: str) -> List[str]:
    if os.path.isfile(source):
        return [source]
    if not os.path.isdir(source):
        return []
    try:
        return [os.path.join(source, name) for name in sorted(os.listdir(source))]
    except OSError:
        return []


def _playlist_entry(
    path: str,
    seen_names: set,
    seen_paths: set,
) -> Optional[Tuple[str, str]]:
    absolute_path = os.path.abspath(path)
    if absolute_path in seen_paths or not os.path.isfile(absolute_path):
        return None
    if not absolute_path.lower().endswith((".m3u", ".m3u8")):
        return None
    name = os.path.splitext(os.path.basename(absolute_path))[0]
    if name in seen_names:
        return None
    seen_paths.add(absolute_path)
    seen_names.add(name)
    return name, absolute_path
