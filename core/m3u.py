"""M3U and M3U8 playlist helpers."""

from __future__ import annotations

import os
from typing import List


def list_files(source: str) -> List[str]:
    """List M3U files in a source, or return a single playlist file."""
    source = os.path.abspath(source)
    if os.path.isdir(source):
        try:
            paths = [os.path.join(source, name) for name in sorted(os.listdir(source))]
        except OSError:
            return []
    else:
        paths = [source]
    return [
        path for path in paths
        if path.lower().endswith((".m3u", ".m3u8")) and os.path.isfile(path)
    ]


def parse(content: str, base_dir: str = "") -> List[str]:
    """Parse text into a data object."""
    paths: List[str] = []
    for raw in content.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if base_dir and not os.path.isabs(line):
            line = os.path.normpath(os.path.join(base_dir, line))
        paths.append(line)
    return paths


def write(name: str, paths: List[str]) -> str:
    """Build playlist text."""
    lines: List[str] = ["#EXTM3U", f"#{name}.m3u8"]
    lines.extend(paths)
    return "\n".join(lines) + "\n"


def parse_file(path: str) -> List[str]:
    """Read and parse a file."""
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
