"""Publish WMplayer's own Windows media session, independently of mpv."""

from __future__ import annotations

from datetime import timedelta
import logging
import sys

from PyQt6.QtCore import QObject, pyqtSignal

from .metadata import TrackMetadata

_log = logging.getLogger(__name__)


class MediaControls(QObject):
    command = pyqtSignal(int)
    seek_requested = pyqtSignal(int)
    _cover_ready = pyqtSignal(int, object)

    def __init__(self, window: QObject) -> None:
        super().__init__(window)
        self._controls = None
        self._tokens = []
        self._cover_stream = None
        self._cover_write = None
        self._cover_generation = 0
        self._cover_ready.connect(self._publish_cover)
        self._duration_ms = 0
        self._position_ms = 0
        if sys.platform != "win32":
            return
        try:
            from winrt.windows.foundation import AsyncStatus
            from winrt.windows.media import MediaPlaybackStatus, MediaPlaybackType
            from winrt.windows.media.interop import get_for_window
            from winrt.windows.storage.streams import (
                DataWriter, InMemoryRandomAccessStream, RandomAccessStreamReference,
            )

            self._status = MediaPlaybackStatus
            self._async_status = AsyncStatus
            self._music_type = MediaPlaybackType.MUSIC
            self._data_writer = DataWriter
            self._memory_stream = InMemoryRandomAccessStream
            self._stream_reference = RandomAccessStreamReference
            controls = get_for_window(int(window.winId()))
            self._controls = controls
            self._tokens.append((controls.remove_button_pressed,
                                 controls.add_button_pressed(self._on_button)))
            self._tokens.append((controls.remove_playback_position_change_requested,
                                 controls.add_playback_position_change_requested(self._on_seek)))
            controls.is_play_enabled = True
            controls.is_pause_enabled = True
            controls.is_stop_enabled = True
            controls.is_next_enabled = True
            controls.is_previous_enabled = True
            controls.playback_status = self._status.CLOSED
            controls.is_enabled = False
        except Exception as exc:
            self.close()
            _log.warning("WMplayer media controls unavailable; using mpv: %s", exc)

    @property
    def available(self) -> bool:
        return self._controls is not None

    def _on_button(self, _sender, args) -> None:
        # WinRT callbacks run on worker threads; Qt signals marshal commands
        # back to the main window's thread.
        from winrt.windows.media import SystemMediaTransportControlsButton as Button

        command = {
            Button.PLAY: 46, Button.PAUSE: 47, Button.STOP: 13,
            Button.NEXT: 11, Button.PREVIOUS: 12,
        }.get(args.button)
        if command is not None:
            self.command.emit(command)

    def _on_seek(self, _sender, args) -> None:
        self.seek_requested.emit(int(args.requested_playback_position.total_seconds() * 1000))

    def set_track(self, track: TrackMetadata) -> None:
        if not self.available:
            return
        try:
            updater = self._controls.display_updater
            updater.clear_all()
            updater.type = self._music_type
            props = updater.music_properties
            props.title = track.title
            props.artist = track.artist
            props.album_title = track.album
            props.track_number = max(0, track.track_number)
            self._duration_ms = max(0, track.duration_ms)
            self._position_ms = 0
            self._cover_stream = None
            self._cover_generation += 1
            self.set_cover(track.cover)
            updater.update()
            self._update_timeline()
        except Exception as exc:
            _log.warning("Could not update Windows media metadata: %s", exc)

    def set_cover(self, cover: bytes | None) -> None:
        if not self.available or not cover:
            return
        try:
            stream = self._memory_stream()
            writer = self._data_writer(stream)
            writer.write_bytes(cover)
            self._cover_generation += 1
            generation = self._cover_generation
            operation = writer.store_async()
            self._cover_write = operation

            def completed(result, _status):
                try:
                    if _status == self._async_status.CANCELED:
                        return
                    result.get_results()
                    writer.detach_stream()
                    stream.seek(0)
                    self._cover_ready.emit(generation, stream)
                except Exception as exc:
                    if self.available:
                        _log.warning("Could not write Windows media artwork: %s", exc)

            operation.completed = completed
        except Exception as exc:
            _log.warning("Could not update Windows media artwork: %s", exc)

    def _publish_cover(self, generation: int, stream) -> None:
        if not self.available or generation != self._cover_generation:
            return
        try:
            updater = self._controls.display_updater
            updater.thumbnail = self._stream_reference.create_from_stream(stream)
            # Windows can read the thumbnail after Update() returns.
            self._cover_stream = stream
            self._cover_write = None
            updater.update()
        except Exception as exc:
            _log.warning("Could not publish Windows media artwork: %s", exc)

    def set_state(self, state: str) -> None:
        if not self.available:
            return
        try:
            self._controls.playback_status = {
                "playing": self._status.PLAYING,
                "paused": self._status.PAUSED,
                "stopped": self._status.STOPPED,
            }.get(state, self._status.CLOSED)
            self._controls.is_enabled = state in ("playing", "paused")
        except Exception as exc:
            _log.warning("Could not update Windows media playback state: %s", exc)

    def set_duration(self, ms: int) -> None:
        self._duration_ms = max(0, ms)
        self._update_timeline()

    def set_position(self, ms: int) -> None:
        self._position_ms = max(0, ms)
        self._update_timeline()

    def _update_timeline(self) -> None:
        if not self.available:
            return
        try:
            from winrt.windows.media import SystemMediaTransportControlsTimelineProperties

            timeline = SystemMediaTransportControlsTimelineProperties()
            timeline.start_time = timeline.min_seek_time = timedelta(0)
            timeline.end_time = timeline.max_seek_time = timedelta(milliseconds=self._duration_ms)
            timeline.position = timedelta(milliseconds=min(self._position_ms, self._duration_ms))
            self._controls.update_timeline_properties(timeline)
        except Exception as exc:
            _log.warning("Could not update Windows media timeline: %s", exc)

    def close(self) -> None:
        if self._controls is None:
            return
        for remove, token in self._tokens:
            try:
                remove(token)
            except Exception:
                pass
        self._tokens.clear()
        try:
            self._controls.is_enabled = False
            self._controls.display_updater.clear_all()
            self._controls.display_updater.update()
            self._controls.playback_status = self._status.CLOSED
        except Exception:
            pass
        self._controls = None
        self._cover_stream = None
        self._cover_write = None
        self._cover_generation += 1
