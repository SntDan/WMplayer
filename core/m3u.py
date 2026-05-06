"""
M3U / M3U8 读写
================
兼容如下格式:
    #EXTM3U
    #自定义注释行
    D:\\path\\to\\song1.flac
    D:\\path\\to\\song2.mp3

解析:跳过所有以 # 开头的行。
写入:首行 #EXTM3U,次行 #<name>.m3u8 作为标识。
"""

from __future__ import annotations

import os
from typing import List


def parse(content: str, base_dir: str = "") -> List[str]:
    """解析 m3u/m3u8 文本,返回路径列表。"""
    paths: List[str] = []
    for raw in content.splitlines():
        line = raw.strip().lstrip("\ufeff")  # 去 BOM
        if not line or line.startswith("#"):
            continue
        if base_dir and not os.path.isabs(line):
            line = os.path.normpath(os.path.join(base_dir, line))
        paths.append(line)
    return paths


def write(name: str, paths: List[str]) -> str:
    """生成 m3u8 文本(UTF-8)。"""
    lines: List[str] = ["#EXTM3U", f"#{name}.m3u8"]
    lines.extend(paths)
    return "\n".join(lines) + "\n"


def parse_file(path: str) -> List[str]:
    """读 m3u/m3u8 文件,返回路径列表。"""
    if not os.path.isfile(path):
        return []
    base = os.path.dirname(os.path.abspath(path))
    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return parse(f.read(), base_dir=base)
        except UnicodeDecodeError:
            continue
        except Exception:
            return []
    return []


def write_file(path: str, name: str, paths: List[str]) -> bool:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(write(name, paths))
        return True
    except Exception:
        return False
