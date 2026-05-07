"""
配置模块
========
- 跨平台的配置目录(用于 settings.json 与 library_cache.json)
- 程序根目录(用于自动发现 ./library/ 与 ./playlists/ 子文件夹)
- DEFAULT_CONFIG 集中管理默认值
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List


# ----------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------
def program_root() -> str:
    """程序根目录(music_player/ 目录所在位置)。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_library_dir() -> str:
    """程序内置曲库目录。"""
    return os.path.join(program_root(), "library")


def default_playlists_dir() -> str:
    """歌单(.m3u8)默认存放目录。"""
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


# ----------------------------------------------------------------------
# 默认配置
# ----------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "volume": 80,
    "play_mode": "sequential",
    "last_position_ms": 0,
    "last_track_path": "",
    "window_geometry": None,
    "auto_resume": True,

    "library_folders": [],
    "include_default_library": True,

    "playlists_dir": default_playlists_dir(),

    "last_playlist_name": "",
}


class Config:
    def __init__(self) -> None:
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        if os.path.isfile(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._data.update(json.load(f))
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

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._data:
            return self._data[key]
        if default is not None:
            return default
        return DEFAULT_CONFIG.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def library_folders_effective(self) -> List[str]:
        """实际生效的曲库根目录(用户自定义 + 默认 library/)。"""
        result: List[str] = []
        for f in self.get("library_folders", []) or []:
            if f and os.path.isdir(f):
                result.append(os.path.abspath(f))
        if self.get("include_default_library", True):
            d = default_library_dir()
            if os.path.isdir(d) and d not in result:
                result.append(d)
        return result
