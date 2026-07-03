"""LRC lyric parsing utilities."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional


_TIME_TAG_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_META_TAG_RE = re.compile(r"\[([a-zA-Z]+):([^\]]*)\]")


@dataclass
class LyricLine:
    time_ms: int
    text: str


@dataclass
class Lyrics:
    lines: List[LyricLine]
    offset_ms: int = 0
    title: str = ""
    artist: str = ""
    album: str = ""

    def __len__(self) -> int:
        return len(self.lines)

    def __iter__(self):
        return iter(self.lines)

    def is_synced(self) -> bool:
        """Return whether the lyrics contain real timestamps."""
        return any(line.time_ms > 0 for line in self.lines)

    def index_at(self, position_ms: int) -> int:
        """Return the active lyric line for a playback position."""
        if not self.lines:
            return -1
        target = position_ms - self.offset_ms
        lo, hi = 0, len(self.lines) - 1
        if target < self.lines[0].time_ms:
            return -1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.lines[mid].time_ms <= target:
                lo = mid
            else:
                hi = mid - 1
        return lo


def parse(content: str) -> Lyrics:
    """Parse text into a data object."""
    lines: List[LyricLine] = []
    offset_ms = 0
    title = artist = album = ""

    for raw in content.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue

        time_matches = list(_TIME_TAG_RE.finditer(line))

        if not time_matches:
            meta = _META_TAG_RE.match(line)
            if meta:
                key = meta.group(1).lower()
                value = meta.group(2).strip()
                if key == "ti":
                    title = value
                elif key == "ar":
                    artist = value
                elif key == "al":
                    album = value
                elif key == "offset":
                    try:
                        offset_ms = int(value)
                    except ValueError:
                        pass
            else:
                lines.append(LyricLine(time_ms=0, text=line))
            continue

        last_end = time_matches[-1].end()
        text = line[last_end:].strip()

        if not text:
            continue

        for m in time_matches:
            mm = int(m.group(1))
            ss = int(m.group(2))
            frac_str = m.group(3) or "0"
            if len(frac_str) == 1:
                frac_ms = int(frac_str) * 100
            elif len(frac_str) == 2:
                frac_ms = int(frac_str) * 10
            else:
                frac_ms = int(frac_str[:3])
            t = mm * 60_000 + ss * 1000 + frac_ms
            lines.append(LyricLine(time_ms=t, text=text))

    lines.sort(key=lambda x: x.time_ms)
    return Lyrics(
        lines=lines,
        offset_ms=offset_ms,
        title=title,
        artist=artist,
        album=album,
    )


def parse_file(path: str) -> Optional[Lyrics]:
    """Read and parse a file."""
    if not path or not os.path.isfile(path):
        return None
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030", "big5", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                content = f.read()
            return parse(content)
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


def find_lrc_for(audio_path: str) -> Optional[str]:
    """Find a matching LRC file beside an audio file."""
    if not audio_path:
        return None
    folder = os.path.dirname(audio_path)
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    if not folder or not stem:
        return None
    cand = os.path.join(folder, stem + ".lrc")
    if os.path.isfile(cand):
        return cand
    if os.path.isdir(folder):
        try:
            stem_lower = stem.lower()
            for fname in os.listdir(folder):
                if fname.lower().endswith(".lrc") and \
                        os.path.splitext(fname)[0].lower() == stem_lower:
                    return os.path.join(folder, fname)
        except OSError:
            pass
    return None
