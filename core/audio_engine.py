"""
音频引擎模块
============
基于 libVLC 的播放后端，支持几乎所有音频格式
（MP3 / FLAC / WAV / ALAC / APE / OGG / Opus / DSD 等）。
通过 Qt 信号将状态变化广播给 UI 层，避免 UI 阻塞。
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import vlc
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class AudioEngine(QObject):
    """音频播放核心。"""

    # 状态信号
    position_changed = pyqtSignal(int)        # 当前播放位置 (毫秒)
    duration_changed = pyqtSignal(int)        # 总时长 (毫秒)
    state_changed = pyqtSignal(str)           # "playing" / "paused" / "stopped"
    track_finished = pyqtSignal()             # 当前曲目结束
    error_occurred = pyqtSignal(str)          # 播放错误

    # 高质量 VLC 参数(尽可能保持原始采样率/位深直通,不下采样)
    _VLC_ARGS = [
        "--no-video",                # 不输出视频
        "--quiet",                   # 静默日志
        "--no-video-title-show",
        "--audio-resampler=soxr",    # 高质量重采样(若可用,失败时回退默认)
        "--no-sout-video",
        "--file-caching=1500",       # 文件缓冲 (ms),避免本地播放卡顿
        "--network-caching=3000",    # 网络流缓冲
    ]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        # 创建 VLC 实例。如果带 soxr 失败则回退最简参数
        try:
            self._instance = vlc.Instance(self._VLC_ARGS)
            if self._instance is None:
                raise RuntimeError("VLC Instance returned None")
        except Exception:
            self._instance = vlc.Instance(["--no-video", "--quiet"])

        self._player: vlc.MediaPlayer = self._instance.media_player_new()
        self._current_path: Optional[str] = None
        self._duration_ms: int = 0

        # VLC 事件 → Qt 信号 (跨线程,所以只做最小操作)
        ev = self._player.event_manager()
        ev.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_end_reached)
        ev.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)
        ev.event_attach(vlc.EventType.MediaPlayerLengthChanged, self._on_length_changed)

        # 用 Qt 定时器轮询位置,避免在 VLC 回调线程里直接动 UI
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(200)  # 5 Hz 已经足够丝滑且省电
        self._poll_timer.timeout.connect(self._poll_position)
        self._poll_timer.start()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def load(self, path: str) -> bool:
        """加载文件但不播放。"""
        if not path or not os.path.exists(path):
            self.error_occurred.emit(f"文件不存在: {path}")
            return False

        media = self._instance.media_new(path)
        # 解析媒体以拿到时长(对不同版本的 python-vlc 做兼容)
        try:
            media.parse_with_options(vlc.MediaParseFlag.local, 3000)
        except Exception:
            try:
                media.parse()  # 旧 API
            except Exception:
                pass
        self._player.set_media(media)
        self._current_path = path
        self._duration_ms = 0  # 等 length_changed 事件回填
        return True

    def play(self) -> None:
        if self._current_path is None:
            return
        if self._player.play() == -1:
            self.error_occurred.emit("播放失败")
            return
        self.state_changed.emit("playing")

    def pause(self) -> None:
        if self._player.is_playing():
            self._player.pause()
            self.state_changed.emit("paused")

    def toggle_pause(self) -> None:
        if self._player.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()
        self.state_changed.emit("stopped")

    def seek(self, position_ms: int) -> None:
        """跳转到指定毫秒。"""
        if self._duration_ms <= 0:
            return
        position_ms = max(0, min(position_ms, self._duration_ms))
        self._player.set_time(position_ms)
        self.position_changed.emit(position_ms)

    def set_volume(self, volume: int) -> None:
        """0-100"""
        self._player.audio_set_volume(max(0, min(100, int(volume))))

    def get_volume(self) -> int:
        return self._player.audio_get_volume()

    def is_playing(self) -> bool:
        return bool(self._player.is_playing())

    def get_position(self) -> int:
        return max(0, self._player.get_time())

    def get_duration(self) -> int:
        return self._duration_ms

    def release(self) -> None:
        """关闭时调用,释放资源。"""
        try:
            self._poll_timer.stop()
            self._player.stop()
            self._player.release()
            self._instance.release()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 内部回调
    # ------------------------------------------------------------------
    def _poll_position(self) -> None:
        if self._player.is_playing():
            pos = self._player.get_time()
            if pos >= 0:
                self.position_changed.emit(pos)

    def _on_end_reached(self, _event) -> None:
        # 在 VLC 线程被调用,信号默认是 QueuedConnection 跨线程安全
        self.track_finished.emit()

    def _on_error(self, _event) -> None:
        self.error_occurred.emit("播放过程中发生错误")

    def _on_length_changed(self, event) -> None:
        try:
            length = event.u.new_length
        except Exception:
            length = self._player.get_length()
        if length and length > 0:
            self._duration_ms = int(length)
            self.duration_changed.emit(self._duration_ms)
