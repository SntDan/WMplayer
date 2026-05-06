"""
播放队列
========
当前在播的曲目集合 + 当前指针 + 播放模式。
持久化用 m3u8 文件(由外部代码控制保存路径)。
"""

from __future__ import annotations

import os
import random
from enum import Enum
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core.metadata import TrackMetadata, is_supported, read_metadata


class PlayMode(Enum):
    """旧版联合模式枚举,保留是为了兼容已存在的 settings.json。

    内部已改为 (shuffled, repeat) 两个独立维度;读取/写入 config 时通过
    `from_components` / `to_components` 互相转换。
    """
    SEQUENTIAL = "sequential"
    REPEAT_ONE = "repeat_one"
    REPEAT_ALL = "repeat_all"
    SHUFFLE = "shuffle"


class RepeatMode(Enum):
    NONE = "none"           # 不循环:播完最后一首停止
    ALL = "all"             # 列表循环:播完最后一首回到第一首
    ONE = "one"             # 单曲循环:自动结束时重播本曲;手动下一首仍然切歌


def _legacy_to_components(mode: PlayMode) -> tuple[bool, RepeatMode]:
    """旧 PlayMode → (shuffled, repeat)"""
    if mode == PlayMode.SHUFFLE:
        return True, RepeatMode.NONE
    if mode == PlayMode.REPEAT_ALL:
        return False, RepeatMode.ALL
    if mode == PlayMode.REPEAT_ONE:
        return False, RepeatMode.ONE
    return False, RepeatMode.NONE


def _components_to_legacy(shuffled: bool, repeat: RepeatMode) -> PlayMode:
    """(shuffled, repeat) → 最接近的旧 PlayMode 值,用于持久化兼容。"""
    if shuffled:
        return PlayMode.SHUFFLE
    if repeat == RepeatMode.ALL:
        return PlayMode.REPEAT_ALL
    if repeat == RepeatMode.ONE:
        return PlayMode.REPEAT_ONE
    return PlayMode.SEQUENTIAL


class Playlist(QObject):
    """播放队列(注意:这是当前正在播的列表,不是磁盘上的歌单文件)。"""

    changed = pyqtSignal()                       # 整体内容变化
    current_changed = pyqtSignal(int)            # 当前曲目索引
    play_mode_changed = pyqtSignal(PlayMode)     # 兼容旧 UI(联合状态)
    shuffled_changed = pyqtSignal(bool)          # 是否随机变更
    repeat_changed = pyqtSignal(RepeatMode)      # 循环模式变更

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tracks: List[TrackMetadata] = []
        self._current_index: int = -1
        # 两个独立维度
        self._shuffled: bool = False
        self._repeat: RepeatMode = RepeatMode.NONE
        # 进入随机模式前的原始顺序快照(列表内容是 TrackMetadata 引用)。
        # 关闭随机时恢复;集合发生变化时清掉,避免还原成过时数据。
        self._original_order: Optional[List[TrackMetadata]] = None

    # ------------------------------------------------------------------
    # 集合操作
    # ------------------------------------------------------------------
    def replace_with_tracks(self, tracks: List[TrackMetadata], start_index: int = -1) -> int:
        """整体替换队列内容,可选指定一个起始索引。
        如果是随机模式，会对队列进行洗牌，并将指定的起始曲目放在第一首，返回它在洗牌后的新索引。"""
        self._tracks = list(tracks)
        if 0 <= start_index < len(self._tracks):
            self._current_index = start_index
        else:
            self._current_index = -1
            
        self._original_order = None
        # 如果当前是随机模式,新内容也要立即洗牌
        if self._shuffled and self._tracks:
            self._enter_shuffle()
        else:
            self.changed.emit()
            
        return max(0, self._current_index)

    def replace_with_paths(self, paths: List[str], start_index: int = -1) -> int:
        """按路径列表整体替换;只读基本元数据。"""
        tracks: List[TrackMetadata] = []
        for p in paths:
            if not p or not os.path.isfile(p) or not is_supported(p):
                continue
            try:
                tracks.append(read_metadata(p, with_cover=False))
            except Exception:
                continue
        return self.replace_with_tracks(tracks, start_index)

    def restore_with_paths(self, paths: List[str], original_paths: Optional[List[str]]) -> None:
        """直接还原原有的播放列表状态，不触发额外的洗牌逻辑。"""
        tracks: List[TrackMetadata] = []
        for p in paths:
            if p and os.path.isfile(p) and is_supported(p):
                try:
                    tracks.append(read_metadata(p, with_cover=False))
                except Exception:
                    pass
        self._tracks = tracks
        
        if original_paths:
            orig_tracks: List[TrackMetadata] = []
            for p in original_paths:
                if p and os.path.isfile(p) and is_supported(p):
                    try:
                        orig_tracks.append(read_metadata(p, with_cover=False))
                    except Exception:
                        pass
            self._original_order = orig_tracks if orig_tracks else None
        else:
            self._original_order = None
            
        self._current_index = -1
        self.changed.emit()

    def append_tracks(self, tracks: List[TrackMetadata]) -> int:
        existing = {t.path for t in self._tracks}
        added = 0
        for t in tracks:
            if t.path in existing:
                continue
            self._tracks.append(t)
            existing.add(t.path)
            added += 1
        if added:
            self.changed.emit()
        return added

    def append_paths(self, paths: List[str]) -> int:
        existing = {t.path for t in self._tracks}
        added = 0
        for p in paths:
            if not p or p in existing or not os.path.isfile(p) or not is_supported(p):
                continue
            try:
                t = read_metadata(p, with_cover=False)
            except Exception:
                continue
            self._tracks.append(t)
            existing.add(p)
            added += 1
        if added:
            self.changed.emit()
        return added

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._tracks):
            del self._tracks[index]
            if index == self._current_index:
                self._current_index = -1
            elif index < self._current_index:
                self._current_index -= 1
            self.changed.emit()

    def clear(self) -> None:
        self._tracks.clear()
        self._current_index = -1
        self._original_order = None
        self.changed.emit()

    # ------------------------------------------------------------------
    # 访问
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self._tracks)

    def __iter__(self):
        return iter(self._tracks)

    def get(self, index: int) -> Optional[TrackMetadata]:
        if 0 <= index < len(self._tracks):
            return self._tracks[index]
        return None

    @property
    def tracks(self) -> List[TrackMetadata]:
        return self._tracks

    @property
    def paths(self) -> List[str]:
        return [t.path for t in self._tracks]

    @property
    def original_paths(self) -> Optional[List[str]]:
        if self._original_order is not None:
            return [t.path for t in self._original_order]
        return None

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def current(self) -> Optional[TrackMetadata]:
        return self.get(self._current_index)

    # ------------------------------------------------------------------
    # 选择 / 导航
    # ------------------------------------------------------------------
    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._tracks):
            self._current_index = index
            self.current_changed.emit(index)

    def find_index_by_path(self, path: str) -> int:
        for i, t in enumerate(self._tracks):
            if t.path == path:
                return i
        return -1

    def next_index(self, auto: bool = False) -> Optional[int]:
        n = len(self._tracks)
        if n == 0:
            return None
        # 单曲循环只在自动结束时停留在本曲;手动按下一首仍前进
        if auto and self._repeat == RepeatMode.ONE:
            return self._current_index if self._current_index >= 0 else 0
        nxt = self._current_index + 1
        if nxt >= n:
            # 列表循环 → 回到开头继续
            if self._repeat == RepeatMode.ALL:
                return 0
            # 不循环:自动结束→停止;手动→回到开头
            return None if auto else 0
        return nxt

    def prev_index(self) -> Optional[int]:
        n = len(self._tracks)
        if n == 0:
            return None
        prv = self._current_index - 1
        if prv < 0:
            if self._repeat == RepeatMode.ALL:
                return n - 1
            return 0
        return prv

    # ------------------------------------------------------------------
    # 模式 (shuffled / repeat 两个独立维度)
    # ------------------------------------------------------------------
    @property
    def shuffled(self) -> bool:
        return self._shuffled

    @property
    def repeat(self) -> RepeatMode:
        return self._repeat

    @property
    def mode(self) -> PlayMode:
        """旧式联合 mode,只用于持久化。"""
        return _components_to_legacy(self._shuffled, self._repeat)

    def set_shuffled(self, shuffled: bool) -> None:
        if shuffled == self._shuffled:
            return
        self._shuffled = shuffled
        if shuffled:
            self._enter_shuffle()
        else:
            self._exit_shuffle()
        self.shuffled_changed.emit(shuffled)
        self.play_mode_changed.emit(self.mode)

    def set_repeat(self, repeat: RepeatMode) -> None:
        if repeat == self._repeat:
            return
        self._repeat = repeat
        # repeat 切换不影响队列顺序
        self.repeat_changed.emit(repeat)
        self.play_mode_changed.emit(self.mode)

    def set_mode(self, mode: PlayMode) -> None:
        """兼容旧接口:把联合 mode 拆成两个独立维度后分别设置。"""
        shuffled, repeat = _legacy_to_components(mode)
        # 注意顺序:先调 repeat 再调 shuffled,避免 enter_shuffle/exit_shuffle
        # 中途看到的 _repeat 还是旧值
        self.set_repeat(repeat)
        self.set_shuffled(shuffled)

    def _enter_shuffle(self) -> None:
        if not self._tracks:
            return
        # 保存当前顺序
        self._original_order = list(self._tracks)
        cur = self.current  # 可能为 None
        rest = [t for t in self._tracks if t is not cur]
        random.shuffle(rest)
        if cur is not None:
            self._tracks = [cur] + rest
            self._current_index = 0
        else:
            self._tracks = rest
            self._current_index = -1
        # 只发 changed 让 UI 刷新列表;current 指的还是同一首歌曲对象,
        # 不能发 current_changed,否则主窗口会以为换歌而重新加载播放
        self.changed.emit()

    def _exit_shuffle(self) -> None:
        if not self._original_order:
            return
        cur = self.current
        # 当前列表中的曲目集合(用 id 判断,因为 TrackMetadata 没实现 __eq__)
        current_ids = {id(t) for t in self._tracks}
        original_ids = {id(t) for t in self._original_order}
        # 1) 按原始顺序保留仍存在的曲目
        rebuilt = [t for t in self._original_order if id(t) in current_ids]
        # 2) SHUFFLE 期间新加的曲目追加到末尾(保持它们在当前列表里的相对顺序)
        rebuilt += [t for t in self._tracks if id(t) not in original_ids]
        self._tracks = rebuilt
        self._original_order = None
        # 重新定位 current(对象不变,只是 index 变了)
        if cur is not None:
            try:
                self._current_index = self._tracks.index(cur)
            except ValueError:
                self._current_index = -1
        else:
            self._current_index = -1
        # 同样只发 changed,不发 current_changed
        self.changed.emit()
