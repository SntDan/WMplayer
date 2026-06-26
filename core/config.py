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
    """程序根目录(WMplayer/ 目录所在位置)。"""
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
    "language": "en",

    # 用户在设置里加的曲库目录(默认 library/ 始终额外扫描,不在此列表)
    "library_folders": [],

    # 用户在设置里加的附加歌单源(文件夹或单独 .m3u8 文件)。
    # 默认歌单目录始终额外包含,不在此列表。
    "playlist_locations": [],

    "last_playlist_name": "",
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

    def get(self, key: str, default: Any = _MISSING) -> Any:
        if key in self._data:
            return self._data[key]
        if default is not _MISSING:
            return default
        return DEFAULT_CONFIG.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def has(self, key: str) -> bool:
        return key in self._data

    # 工厂重置: 由 SettingsDialog 触发, 由 MainWindow.closeEvent 检查。
    # 标志为 True 时, closeEvent 应跳过状态保存(否则会立刻把队列写回缓存)。
    def mark_factory_reset(self) -> None:
        self._factory_reset_pending = True

    @property
    def factory_reset_pending(self) -> bool:
        return self._factory_reset_pending

    def library_folders_effective(self) -> List[str]:
        """实际生效的曲库根目录(默认 library/ 始终包含,后接用户自定义)。"""
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
        """用户自定义的附加歌单源(默认目录由 PlaylistStore 单独传入,不在此列表)。"""
        result: List[str] = []
        default_abs = os.path.abspath(default_playlists_dir())
        for loc in self.get("playlist_locations", []) or []:
            if not loc:
                continue
            ap = os.path.abspath(loc)
            if ap == default_abs:
                continue  # 默认目录单独处理,避免重复
            if os.path.isdir(ap) or os.path.isfile(ap):
                if ap not in result:
                    result.append(ap)
        return result
