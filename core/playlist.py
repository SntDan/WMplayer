"""In-memory playback queue and playback modes."""

from __future__ import annotations

import os
import random
from enum import Enum
from typing import List, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from core.metadata import TrackMetadata, is_supported, read_metadata


class PlayMode(Enum):
    """Legacy combined playback mode."""
    SEQUENTIAL = "sequential"
    REPEAT_ONE = "repeat_one"
    REPEAT_ALL = "repeat_all"
    SHUFFLE = "shuffle"


class RepeatMode(Enum):
    NONE = "none"
    ALL = "all"
    ONE = "one"


def _legacy_to_components(mode: PlayMode) -> tuple[bool, RepeatMode]:
    """Convert a legacy mode into shuffle and repeat state."""
    if mode == PlayMode.SHUFFLE:
        return True, RepeatMode.NONE
    if mode == PlayMode.REPEAT_ALL:
        return False, RepeatMode.ALL
    if mode == PlayMode.REPEAT_ONE:
        return False, RepeatMode.ONE
    return False, RepeatMode.NONE


def _components_to_legacy(shuffled: bool, repeat: RepeatMode) -> PlayMode:
    """Convert shuffle and repeat state into a legacy mode."""
    if shuffled:
        return PlayMode.SHUFFLE
    if repeat == RepeatMode.ALL:
        return PlayMode.REPEAT_ALL
    if repeat == RepeatMode.ONE:
        return PlayMode.REPEAT_ONE
    return PlayMode.SEQUENTIAL


class Playlist(QObject):
    """In-memory playback queue."""

    changed = pyqtSignal()
    current_changed = pyqtSignal(int)
    play_mode_changed = pyqtSignal(PlayMode)
    shuffled_changed = pyqtSignal(bool)
    repeat_changed = pyqtSignal(RepeatMode)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tracks: List[TrackMetadata] = []
        self._current_index: int = -1
        self._shuffled: bool = False
        self._repeat: RepeatMode = RepeatMode.NONE
        self._original_order: Optional[List[TrackMetadata]] = None

    def replace_with_tracks(self, tracks: List[TrackMetadata], start_index: int = -1) -> int:
        """Replace the queue with parsed tracks."""
        self._tracks = list(tracks)
        if 0 <= start_index < len(self._tracks):
            self._current_index = start_index
        else:
            self._current_index = -1
            
        self._original_order = None
        if self._shuffled and self._tracks:
            self._enter_shuffle()
        else:
            self.changed.emit()
            
        return max(0, self._current_index)

    def replace_with_paths(self, paths: List[str], start_index: int = -1) -> int:
        """Replace the queue from file paths."""
        tracks: List[TrackMetadata] = []
        for p in paths:
            if not p or not os.path.isfile(p) or not is_supported(p):
                continue
            try:
                tracks.append(read_metadata(p, with_cover=False))
            except Exception:
                continue
        return self.replace_with_tracks(tracks, start_index)

    def restore_with_tracks(
        self,
        tracks: List[TrackMetadata],
        original_tracks: Optional[List[TrackMetadata]] = None,
    ) -> None:
        """Restore a parsed queue snapshot."""
        self._tracks = list(tracks)
        self._original_order = list(original_tracks) if original_tracks else None
        self._current_index = -1
        self.changed.emit()

    def restore_with_paths(self, paths: List[str], original_paths: Optional[List[str]]) -> None:
        """Restore a queue snapshot from paths."""
        tracks = self._resolve_paths(paths)
        orig = self._resolve_paths(original_paths) if original_paths else None
        self.restore_with_tracks(tracks, orig)

    @staticmethod
    def _resolve_paths(paths: List[str]) -> List[TrackMetadata]:
        out: List[TrackMetadata] = []
        for p in paths:
            if p and os.path.isfile(p) and is_supported(p):
                try:
                    out.append(read_metadata(p, with_cover=False))
                except Exception:
                    pass
        return out

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
        if auto and self._repeat == RepeatMode.ONE:
            return self._current_index if self._current_index >= 0 else 0
        nxt = self._current_index + 1
        if nxt >= n:
            if self._repeat == RepeatMode.ALL:
                return 0
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

    @property
    def shuffled(self) -> bool:
        return self._shuffled

    @property
    def repeat(self) -> RepeatMode:
        return self._repeat

    @property
    def mode(self) -> PlayMode:
        """Legacy playback mode for persistence."""
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
        self.repeat_changed.emit(repeat)
        self.play_mode_changed.emit(self.mode)

    def set_mode(self, mode: PlayMode) -> None:
        """Set playback state from a legacy mode."""
        shuffled, repeat = _legacy_to_components(mode)
        self.set_repeat(repeat)
        self.set_shuffled(shuffled)

    def _enter_shuffle(self) -> None:
        if not self._tracks:
            return
        self._original_order = list(self._tracks)
        cur = self.current
        rest = [t for t in self._tracks if t is not cur]
        random.shuffle(rest)
        if cur is not None:
            self._tracks = [cur] + rest
            self._current_index = 0
        else:
            self._tracks = rest
            self._current_index = -1
        self.changed.emit()

    def _exit_shuffle(self) -> None:
        if not self._original_order:
            return
        cur = self.current
        current_ids = {id(t) for t in self._tracks}
        original_ids = {id(t) for t in self._original_order}
        rebuilt = [t for t in self._original_order if id(t) in current_ids]
        rebuilt += [t for t in self._tracks if id(t) not in original_ids]
        self._tracks = rebuilt
        self._original_order = None
        if cur is not None:
            try:
                self._current_index = self._tracks.index(cur)
            except ValueError:
                self._current_index = -1
        else:
            self._current_index = -1
        self.changed.emit()
