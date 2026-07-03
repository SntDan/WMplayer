"""Album-cover thumbnail cache."""

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
    """Return the thumbnail cache path for a track."""
    h = hashlib.md5(track_path.encode("utf-8", errors="replace")).hexdigest()
    return os.path.join(THUMB_DIR, h + ".jpg")


def thumb_exists(track_path: str) -> bool:
    """Return whether a thumbnail marker exists."""
    return os.path.isfile(thumb_path_for(track_path))


def ensure_thumb(track_path: str, cover_bytes: Optional[bytes]) -> Optional[str]:
    """Create a thumbnail marker when needed."""
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
