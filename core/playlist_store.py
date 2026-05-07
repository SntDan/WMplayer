"""
歌单存储
========
- 默认目录(可写): 新建/重命名/删除都落到这里
- 附加源(只读): 用户在设置里加入的其它文件夹或单独 .m3u8 文件
  仅用于"读取并播放",不允许 rename/delete。
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from core import m3u


class PlaylistStore(QObject):
    """默认目录 + 多个附加源(文件夹或单独 .m3u8 文件)。"""

    changed = pyqtSignal()  # 歌单集合发生变化

    def __init__(self, default_dir: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._default_dir = default_dir
        self._locations: List[str] = []
        try:
            os.makedirs(self._default_dir, exist_ok=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    @property
    def default_dir(self) -> str:
        return self._default_dir

    def set_default_dir(self, directory: str) -> None:
        self._default_dir = directory
        try:
            os.makedirs(self._default_dir, exist_ok=True)
        except Exception:
            pass
        self.changed.emit()

    @property
    def locations(self) -> List[str]:
        return list(self._locations)

    def set_locations(self, locations: List[str]) -> None:
        self._locations = [l for l in locations if l]
        self.changed.emit()

    # ------------------------------------------------------------------
    # 内部: 把所有源解析成 (display_name, abs_path) 列表
    # ------------------------------------------------------------------
    def _collect_entries(self) -> List[Tuple[str, str]]:
        """按"默认目录优先 → 附加源按用户顺序"返回 (展示名, 绝对路径)。

        重名时:第一次出现的胜出,后面的同名跳过(尊重用户的优先级)。
        """
        seen_names: set = set()
        seen_paths: set = set()
        entries: List[Tuple[str, str]] = []

        def _try_add(path: str) -> None:
            ap = os.path.abspath(path)
            if ap in seen_paths:
                return
            if not os.path.isfile(ap):
                return
            if not ap.lower().endswith((".m3u", ".m3u8")):
                return
            name = os.path.splitext(os.path.basename(ap))[0]
            if name in seen_names:
                return
            seen_paths.add(ap)
            seen_names.add(name)
            entries.append((name, ap))

        # 默认目录优先
        if os.path.isdir(self._default_dir):
            try:
                for f in sorted(os.listdir(self._default_dir)):
                    _try_add(os.path.join(self._default_dir, f))
            except OSError:
                pass

        # 附加源:文件夹 / 单文件
        for loc in self._locations:
            if os.path.isfile(loc):
                _try_add(loc)
            elif os.path.isdir(loc):
                try:
                    for f in sorted(os.listdir(loc)):
                        _try_add(os.path.join(loc, f))
                except OSError:
                    pass

        return entries

    def _name_to_path(self) -> Dict[str, str]:
        return {name: path for name, path in self._collect_entries()}

    # ------------------------------------------------------------------
    # 列出
    # ------------------------------------------------------------------
    def list_names(self) -> List[str]:
        return [name for name, _ in self._collect_entries()]

    def file_path(self, name: str) -> str:
        """根据名字找到歌单文件;找不到时返回默认目录下的拟定路径。"""
        m = self._name_to_path()
        if name in m:
            return m[name]
        return os.path.join(self._default_dir, name + ".m3u8")

    def is_writable(self, name: str) -> bool:
        """歌单是否在默认目录里(允许 rename/delete)。"""
        path = self._name_to_path().get(name)
        if not path:
            return False
        return os.path.dirname(path) == os.path.abspath(self._default_dir)

    # ------------------------------------------------------------------
    # 加载/保存/删除/重命名 (写操作只针对默认目录)
    # ------------------------------------------------------------------
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
