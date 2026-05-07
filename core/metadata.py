"""
元数据模块
==========
封装 mutagen,用统一接口提供 标题/艺术家/专辑/时长/封面 信息。
封面以 bytes 返回,UI 层负责解码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis


SUPPORTED_EXTS = {
    ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".oga",
    ".opus", ".ape", ".wma", ".alac", ".aiff", ".aif", ".dsf", ".dff",
}


@dataclass
class TrackMetadata:
    path: str
    title: str = "未知歌曲"
    artist: str = "未知艺术家"
    album: str = "未知专辑"
    duration_ms: int = 0
    sample_rate: int = 0          # Hz, 例如 44100 / 48000 / 96000
    bits_per_sample: int = 0      # bit, 例如 16 / 24 / 32 (有些有损格式无此字段时为 0)
    track_number: int = 0         # 专辑内曲目序号,0 表示未知
    cover: Optional[bytes] = field(default=None, repr=False)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    def is_high_res(self) -> bool:
        """高于 CD 音质 (>16bit 或 >44.1kHz)。位深为 0(未知/有损) 时只看采样率。"""
        if self.bits_per_sample and self.bits_per_sample > 16:
            return True
        if self.sample_rate and self.sample_rate > 48000:
            return True
        return False


def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTS


def read_metadata(path: str, with_cover: bool = True) -> TrackMetadata:
    """读取一首曲目的元数据。出错时返回空模板而不抛异常。"""
    md = TrackMetadata(path=path)
    md.title = os.path.splitext(os.path.basename(path))[0]

    try:
        audio = MutagenFile(path)
    except Exception:
        return md

    if audio is None:
        return md

    # 时长 / 采样率 / 位深
    try:
        info = audio.info
        if info:
            length = getattr(info, "length", 0)
            if length:
                md.duration_ms = int(length * 1000)
            sr = getattr(info, "sample_rate", 0)
            if sr:
                md.sample_rate = int(sr)
            # 不同容器叫法不同
            for attr in ("bits_per_sample", "bitrate_per_sample", "bps"):
                bps = getattr(info, attr, 0)
                if bps:
                    md.bits_per_sample = int(bps)
                    break
    except Exception:
        pass

    # 标签
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
        track_raw = _first_tag(audio, ["TRCK", "tracknumber", "TRACKNUMBER", "trkn", "WM/TrackNumber"])
        if track_raw:
            try:
                md.track_number = int(str(track_raw).split("/")[0].strip())
            except (ValueError, TypeError):
                pass
    except Exception:
        pass

    # 封面
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
        # mutagen 返回的格式因容器而异
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
    # FLAC: 内嵌 pictures 列表
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

    # ID3 - APIC (MP3、有时 WAV/AIFF 也用 ID3)
    try:
        tags = getattr(audio, "tags", None)
        if tags is not None and hasattr(tags, "getall"):
            apic_list = tags.getall("APIC")
            if apic_list:
                return apic_list[0].data
    except Exception:
        pass

    # 兜底:同目录下 cover.* 文件 (限制 ≤20MB,避免读到几十 MB 的图把每次扫描卡死)
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
