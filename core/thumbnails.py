"""
封面缩略图缓存
==============
扫描曲库时为每首有封面的歌曲生成 64x64 JPEG 小图,落盘到 CONFIG_DIR/thumbnails/。
- 文件名为原路径的 md5,跨次启动能秒命中
- 没有封面的曲目也会写一个 0 字节占位文件,避免每次扫描重复尝试解码
- UI 列表渲染时只读这些小图,不会再每帧解码原始大图
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage

from core.config import CONFIG_DIR


THUMB_SIZE = 128
THUMB_DIR = os.path.join(CONFIG_DIR, "thumbnails")


def thumb_path_for(track_path: str) -> str:
    """根据原文件绝对路径计算缩略图缓存路径。"""
    h = hashlib.md5(track_path.encode("utf-8", errors="replace")).hexdigest()
    return os.path.join(THUMB_DIR, h + ".jpg")


def thumb_exists(track_path: str) -> bool:
    """检查缩略图(或空封面占位)是否已生成。"""
    return os.path.isfile(thumb_path_for(track_path))


def ensure_thumb(track_path: str, cover_bytes: Optional[bytes]) -> Optional[str]:
    """
    保证 track_path 对应的缩略图已存在。
    - 有封面: 写入 64x64 JPEG,返回路径
    - 无封面: 写入 0 字节占位文件,返回 None (不再重复尝试)
    """
    out = thumb_path_for(track_path)
    if os.path.isfile(out):
        return out if os.path.getsize(out) > 0 else None
    try:
        os.makedirs(THUMB_DIR, exist_ok=True)
    except Exception:
        return None

    if not cover_bytes:
        try:
            open(out, "wb").close()
        except Exception:
            pass
        return None

    try:
        img = QImage()
        if not img.loadFromData(cover_bytes):
            open(out, "wb").close()
            return None
        scaled = img.scaled(
            THUMB_SIZE, THUMB_SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.width() > THUMB_SIZE or scaled.height() > THUMB_SIZE:
            x = max(0, (scaled.width() - THUMB_SIZE) // 2)
            y = max(0, (scaled.height() - THUMB_SIZE) // 2)
            scaled = scaled.copy(x, y, THUMB_SIZE, THUMB_SIZE)
        if scaled.save(out, "JPG", 82):
            return out
    except Exception:
        pass
    return None
