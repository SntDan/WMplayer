"""
歌单存储
========
管理一个目录下的多个 .m3u8 歌单文件。
"""

from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core import m3u


class PlaylistStore(QObject):
    """指向某个文件夹,提供该文件夹下歌单的 CRUD。"""

    changed = pyqtSignal()  # 歌单集合发生变化

    def __init__(self, directory: str, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._dir = directory
        try:
            os.makedirs(self._dir, exist_ok=True)
        except Exception:
            pass

    @property
    def directory(self) -> str:
        return self._dir

    def set_directory(self, directory: str) -> None:
        self._dir = directory
        try:
            os.makedirs(self._dir, exist_ok=True)
        except Exception:
            pass
        self.changed.emit()

    # ------------------------------------------------------------------
    # 列出
    # ------------------------------------------------------------------
    def list_names(self) -> List[str]:
        if not os.path.isdir(self._dir):
            return []
        names: List[str] = []
        for f in sorted(os.listdir(self._dir)):
            if f.lower().endswith((".m3u", ".m3u8")):
                names.append(os.path.splitext(f)[0])
        return names

    def file_path(self, name: str) -> str:
        # 优先返回已存在的文件;不存在则返回 .m3u8 默认路径
        for ext in (".m3u8", ".m3u"):
            p = os.path.join(self._dir, name + ext)
            if os.path.isfile(p):
                return p
        return os.path.join(self._dir, name + ".m3u8")

    # ------------------------------------------------------------------
    # 加载/保存/删除/重命名
    # ------------------------------------------------------------------
    def load(self, name: str) -> List[str]:
        return m3u.parse_file(self.file_path(name))

    def save(self, name: str, paths: List[str]) -> bool:
        if not name:
            return False
        # 去掉文件名里非法字符
        safe = _safe_filename(name)
        target = os.path.join(self._dir, safe + ".m3u8")
        ok = m3u.write_file(target, name, paths)
        if ok:
            self.changed.emit()
        return ok

    def delete(self, name: str) -> bool:
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
        old_path = self.file_path(old)
        if not os.path.isfile(old_path):
            return False
        ext = os.path.splitext(old_path)[1] or ".m3u8"
        new_path = os.path.join(self._dir, _safe_filename(new) + ext)
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
