"""Application paths and persistent settings."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

from core import m3u


def program_root() -> str:
    """Return the project root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_library_dir() -> str:
    """Return the bundled library folder."""
    return os.path.join(program_root(), "library")


def default_playlists_dir() -> str:
    """Return the default playlist folder."""
    return os.path.join(program_root(), "playlists")


def _config_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    path = os.path.join(base, "MusicPlayer")
    os.makedirs(path, exist_ok=True)
    return path


CONFIG_DIR = _config_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")
LIBRARY_CACHE_PATH = os.path.join(CONFIG_DIR, "library_cache.json")
QUEUE_CACHE_PATH = os.path.join(CONFIG_DIR, "queue.m3u8")
QUEUE_ORIGINAL_CACHE_PATH = os.path.join(CONFIG_DIR, "queue_original.m3u8")


DEFAULT_VOLUME = 100

DEFAULT_CONFIG: Dict[str, Any] = {
    "volume": DEFAULT_VOLUME,
    "shuffled": False,
    "repeat": "none",
    "last_position_ms": 0,
    "last_track_path": "",
    "auto_resume": False,
    "album_continuation": True,
    "language": "en",
    "library_folders": [],
    "playlist_locations": [],
}


_MISSING = object()


class Config:
    def __init__(self) -> None:
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._factory_reset_pending: bool = False
        self.load()

    def load(self) -> None:
        if os.path.isfile(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Migrate the old combined mode once; persist only separate states.
                old_mode = data.pop("play_mode", None)
                if old_mode is not None:
                    data.setdefault("shuffled", old_mode == "shuffle")
                    data.setdefault("repeat", {
                        "repeat_all": "all", "repeat_one": "one",
                    }.get(old_mode, "none"))
                self._data.update(data)
            except Exception:
                pass

    def save(self) -> None:
        try:
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except Exception:
            pass

    def get(self, key: str, default: Any = _MISSING) -> Any:
        if key in self._data:
            return self._data[key]
        if default is not _MISSING:
            return default
        return DEFAULT_CONFIG.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def mark_factory_reset(self) -> None:
        self._factory_reset_pending = True

    @property
    def factory_reset_pending(self) -> bool:
        return self._factory_reset_pending

    def library_folders_effective(self) -> List[str]:
        """Return active library folders."""
        result: List[str] = []
        d = default_library_dir()
        if os.path.isdir(d):
            result.append(os.path.abspath(d))
        for f in self.get("library_folders", []) or []:
            if not f:
                continue
            ap = os.path.abspath(f)
            if os.path.isdir(ap) and ap not in result:
                result.append(ap)
        return result

    def playlist_locations_effective(self) -> List[str]:
        """Return external playlist files, expanding legacy folder sources."""
        result: List[str] = []
        seen: set[str] = set()
        default_abs = os.path.normcase(os.path.abspath(default_playlists_dir()))
        for loc in self.get("playlist_locations", []) or []:
            if not loc:
                continue
            for path in m3u.list_files(loc):
                key = os.path.normcase(path)
                if os.path.normcase(os.path.dirname(path)) == default_abs or key in seen:
                    continue
                seen.add(key)
                result.append(path)
        return result
