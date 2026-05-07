"""
LRC 歌词解析
============
标准 LRC 格式:
    [ti:歌曲标题]
    [ar:艺术家]
    [al:专辑]
    [offset:+200]    <- 整体偏移(毫秒,正值表示歌词延后)
    [00:12.34]第一行歌词
    [00:15.67]第二行歌词
    [00:20.00][00:50.00]同一句出现两次

支持:
- 多种编码 (UTF-8/UTF-8-BOM/GBK/Latin-1)
- 多时间戳行
- offset 元数据
- 毫秒精度 (xx 或 xxx)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional


# 时间戳: [mm:ss.xx] 或 [mm:ss.xxx] 或 [mm:ss]
_TIME_TAG_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
# 元数据标签: [key:value]  (key 是字母)
_META_TAG_RE = re.compile(r"\[([a-zA-Z]+):([^\]]*)\]")


@dataclass
class LyricLine:
    time_ms: int   # 起始时间(毫秒)
    text: str      # 歌词文本


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
        """有任何一行带非零时间戳才算同步歌词。"""
        return any(line.time_ms > 0 for line in self.lines)

    def index_at(self, position_ms: int) -> int:
        """根据当前播放位置返回应高亮的歌词行索引。

        二分查找,O(log n)。返回 -1 表示尚未到第一行。
        """
        if not self.lines:
            return -1
        target = position_ms - self.offset_ms
        # 二分:找到最后一个 time_ms <= target 的行
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


# ----------------------------------------------------------------------
# 解析
# ----------------------------------------------------------------------
def parse(content: str) -> Lyrics:
    """解析 LRC 文本,返回按时间排序的 Lyrics 对象。"""
    lines: List[LyricLine] = []
    offset_ms = 0
    title = artist = album = ""

    for raw in content.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue

        # 先收集这一行所有的时间戳
        time_matches = list(_TIME_TAG_RE.finditer(line))

        if not time_matches:
            # 没时间戳:可能是元数据标签,或纯文本(不带时间戳的歌词)
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
                # 纯文本(无时间戳)歌词文件 - 当成一整段文本
                lines.append(LyricLine(time_ms=0, text=line))
            continue

        # 提取时间戳后面的文本(去掉所有时间戳前缀)
        last_end = time_matches[-1].end()
        text = line[last_end:].strip()

        # 没有歌词文本的时间戳行直接跳过(常见于 LRC 间奏空行)
        if not text:
            continue

        for m in time_matches:
            mm = int(m.group(1))
            ss = int(m.group(2))
            frac_str = m.group(3) or "0"
            # 把 xx (1-2 位) 或 xxx (3 位) 都规范化到毫秒
            if len(frac_str) == 1:
                frac_ms = int(frac_str) * 100
            elif len(frac_str) == 2:
                frac_ms = int(frac_str) * 10
            else:  # 3 位
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
    """读取并解析 .lrc 文件,失败返回 None。"""
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
    """对于一个音频文件,在同目录下找同名的 .lrc 文件。

    例如  D:\\Music\\song.flac → D:\\Music\\song.lrc
    支持大小写不敏感的匹配。
    """
    if not audio_path:
        return None
    folder = os.path.dirname(audio_path)
    stem = os.path.splitext(os.path.basename(audio_path))[0]
    if not folder or not stem:
        return None
    # 优先精确匹配(常见情况,免去 listdir)
    cand = os.path.join(folder, stem + ".lrc")
    if os.path.isfile(cand):
        return cand
    # 大小写不敏感扫描(同目录下找一个 stem 相同的 .lrc)
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
