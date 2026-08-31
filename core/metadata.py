"""Audio metadata and cover extraction."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis

SUPPORTED_EXTS = {
    ".mp3",
    ".flac",
    ".wav",
    ".m4a",
    ".aac",
    ".ogg",
    ".oga",
    ".opus",
    ".ape",
    ".wma",
    ".alac",
    ".aiff",
    ".aif",
    ".dsf",
    ".dff",
}


@dataclass
class TrackMetadata:
    path: str
    title: str = "Unknown Song"
    artist: str = "Unknown Artist"
    album: str = "Unknown Album"
    duration_ms: int = 0
    sample_rate: int = 0
    bits_per_sample: int = 0
    track_number: int = 0
    cover: Optional[bytes] = field(default=None, repr=False)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    def is_high_res(self) -> bool:
        """Return whether the track is above CD quality when known."""
        if self.bits_per_sample and self.bits_per_sample > 16:
            return True
        if self.sample_rate and self.sample_rate > 48000:
            return True
        return False


def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS


def read_metadata(path: str, with_cover: bool = True) -> TrackMetadata:
    """Read metadata and return a safe fallback on failure."""
    md = TrackMetadata(path=path)
    md.title = os.path.splitext(os.path.basename(path))[0]

    try:
        audio = MutagenFile(path)
    except Exception:
        return md

    if audio is None:
        return md

    try:
        info = audio.info
        if info:
            length = getattr(info, "length", 0)
            if length:
                md.duration_ms = int(length * 1000)
            sr = getattr(info, "sample_rate", 0)
            if sr:
                md.sample_rate = int(sr)
            for attr in ("bits_per_sample", "bitrate_per_sample", "bps"):
                bps = getattr(info, attr, 0)
                if bps:
                    md.bits_per_sample = int(bps)
                    break
    except Exception:
        pass

    try:
        title = _first_tag(audio, ["TIT2", "title", "\xa9nam", "Title"])
        artist = _first_tag(audio, ["TPE1", "artist", "\xa9ART", "Artist"])
        album = _first_tag(audio, ["TALB", "album", "\xa9alb", "Album"])
        if title:
            md.title = title
        if artist:
            md.artist = artist
        if album:
            md.album = album
        track_raw = _first_tag(
            audio, ["TRCK", "tracknumber", "TRACKNUMBER", "trkn", "WM/TrackNumber"]
        )
        if track_raw:
            try:
                md.track_number = int(str(track_raw).split("/")[0].strip())
            except (ValueError, TypeError):
                pass
    except Exception:
        pass

    if with_cover:
        try:
            md.cover = _extract_cover(audio, path)
        except Exception:
            md.cover = None

    return md


def _first_tag(audio, keys) -> Optional[str]:
    for key in keys:
        try:
            value = audio.get(key)
        except Exception:
            value = None
        if value is None:
            continue
        if isinstance(value, list) and value:
            value = value[0]
        if hasattr(value, "text"):
            text = value.text
            if isinstance(text, list) and text:
                return str(text[0]).strip() or None
            return str(text).strip() or None
        if isinstance(value, (list, tuple)) and value:
            return str(value[0]).strip() or None
        if isinstance(value, str):
            return value.strip() or None
        return str(value).strip() or None
    return None


def _extract_cover(audio, path: str) -> Optional[bytes]:
    try:
        if isinstance(audio, FLAC) and audio.pictures:
            return audio.pictures[0].data
    except Exception:
        pass

    # MP4 / M4A: covr atom
    try:
        if isinstance(audio, MP4) and audio.tags is not None:
            covr = audio.tags.get("covr")
            if covr:
                return bytes(covr[0])
    except Exception:
        pass

    # OGG Vorbis (METADATA_BLOCK_PICTURE base64)
    try:
        if isinstance(audio, OggVorbis):
            import base64

            b64list = audio.get("metadata_block_picture", [])
            for b64 in b64list:
                try:
                    pic = Picture(base64.b64decode(b64))
                    return pic.data
                except Exception:
                    continue
    except Exception:
        pass

    try:
        tags = getattr(audio, "tags", None)
        if tags is not None and hasattr(tags, "getall"):
            apic_list = tags.getall("APIC")
            if apic_list:
                return apic_list[0].data
    except Exception:
        pass

    try:
        folder = os.path.dirname(path)
        max_bytes = 20 * 1024 * 1024
        for name in ("cover", "folder", "front", "albumart", "Cover", "Folder"):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                cand = os.path.join(folder, name + ext)
                if os.path.isfile(cand) and os.path.getsize(cand) <= max_bytes:
                    with open(cand, "rb") as f:
                        return f.read()
    except Exception:
        pass

    return None
