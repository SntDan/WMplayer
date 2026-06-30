"""
Audio playback backend.

The UI talks to this class through a small Qt signal/method surface.  Playback
is handled by an mpv process over JSON IPC, which avoids requiring libmpv DLLs
while still letting mpv keep the next playlist entry ready for gapless handoff.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import Any, Dict, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class _MpvIpcProcess:
    """Small JSON IPC wrapper around mpv.exe."""

    def __init__(self) -> None:
        exe = self._find_mpv_executable()
        if not exe:
            raise RuntimeError("mpv.exe was not found on PATH.")

        self._pipe_name = rf"\\.\pipe\wmplayer-mpv-{os.getpid()}-{uuid.uuid4().hex}"
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        args = [
            exe,
            "--no-video",
            "--idle=yes",
            "--terminal=no",
            "--force-window=no",
            "--audio-display=no",
            "--gapless-audio=yes",
            "--keep-open=no",
            "--audio-buffer=0.5",
            "--cache=yes",
            "--demuxer-readahead-secs=20",
            "--demuxer-max-bytes=128MiB",
            "--input-default-bindings=no",
            f"--input-ipc-server={self._pipe_name}",
        ]
        if sys.platform == "win32":
            args.append("--ao=wasapi")
            args.append("--priority=abovenormal")

        if sys.platform == "win32" and hasattr(subprocess, "ABOVE_NORMAL_PRIORITY_CLASS"):
            creationflags |= subprocess.ABOVE_NORMAL_PRIORITY_CLASS
        self._process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        self._pipe = self._open_pipe()
        self._lock = threading.Lock()
        self._request_id = 0
        self._events = []
        self._closed = False

    def command(self, *command: Any, timeout: float = 1.5) -> Any:
        with self._lock:
            request_id = self._next_request_id()
            self._write_line({"command": list(command), "request_id": request_id})
            response, events = self._read_response(request_id, timeout)
        self._dispatch_events(events)
        if not isinstance(response, dict):
            return None
        error = response.get("error")
        if error and error != "success":
            raise RuntimeError(f"mpv command failed: {error}")
        return response.get("data")

    def add_event_handler(self, callback) -> None:
        self._events.append(callback)

    def close(self) -> None:
        self._closed = True
        try:
            self.command("quit", timeout=0.5)
        except Exception:
            pass
        try:
            self._pipe.close()
        except Exception:
            pass
        if self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

    def _open_pipe(self):
        if sys.platform == "win32":
            return self._open_windows_pipe()

        last_error: Optional[Exception] = None
        for _ in range(80):
            if self._process.poll() is not None:
                raise RuntimeError("mpv exited before IPC was ready.")
            try:
                return open(self._pipe_name, "r+b", buffering=0)
            except OSError as exc:
                last_error = exc
                time.sleep(0.05)
        raise RuntimeError(f"Could not connect to mpv IPC: {last_error}")

    def _open_windows_pipe(self):
        import pywintypes
        import win32pipe

        last_error: Optional[Exception] = None
        for _ in range(80):
            if self._process.poll() is not None:
                raise RuntimeError("mpv exited before IPC was ready.")
            try:
                win32pipe.WaitNamedPipe(self._pipe_name, 50)
                return _WindowsNamedPipe(self._pipe_name)
            except pywintypes.error as exc:
                last_error = exc
                time.sleep(0.05)
        raise RuntimeError(f"Could not connect to mpv IPC: {last_error}")

    def _read_response(self, request_id: int, timeout: float) -> tuple[Optional[Dict[str, Any]], list[Dict[str, Any]]]:
        deadline = time.monotonic() + timeout
        events: list[Dict[str, Any]] = []
        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            try:
                raw = self._pipe.readline(remaining)
            except TypeError:
                raw = self._pipe.readline()
            if not raw:
                continue
            try:
                message = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception:
                continue
            if message.get("request_id") == request_id:
                return message, events
            events.append(message)
        raise TimeoutError(f"mpv command timed out: request {request_id}")

    def _dispatch_events(self, events: list[Dict[str, Any]]) -> None:
        if not events:
            return
        callbacks = list(self._events)
        for message in events:
            for callback in callbacks:
                QTimer.singleShot(0, lambda msg=message, cb=callback: self._safe_dispatch(cb, msg))

    @staticmethod
    def _safe_dispatch(callback, message: Dict[str, Any]) -> None:
        try:
            callback(message)
        except Exception:
            pass

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _write_line(self, payload: Dict[str, Any]) -> None:
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self._pipe.write(data)

    @staticmethod
    def _find_mpv_executable() -> Optional[str]:
        for name in ("mpv.exe", "mpv.com", "mpv"):
            found = shutil.which(name)
            if found:
                return found
        local_dirs = [
            os.getcwd(),
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mpv"),
        ]
        for directory in local_dirs:
            for name in ("mpv.exe", "mpv.com"):
                path = os.path.join(directory, name)
                if os.path.exists(path):
                    return path
        return None


class _WindowsNamedPipe:
    def __init__(self, path: str) -> None:
        import win32con
        import win32file

        self._win32file = win32file
        self._buffer = bytearray()
        self._handle = win32file.CreateFile(
            path,
            win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            0,
            None,
            win32con.OPEN_EXISTING,
            0,
            None,
        )

    def readline(self, timeout: Optional[float] = None) -> bytes:
        import win32pipe

        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._buffer[: newline + 1])
                del self._buffer[: newline + 1]
                return line
            if deadline is not None:
                while True:
                    _data, available, _left = win32pipe.PeekNamedPipe(self._handle, 0)
                    if available > 0:
                        break
                    if time.monotonic() >= deadline:
                        return b""
                    time.sleep(0.005)
            _data, available, _left = win32pipe.PeekNamedPipe(self._handle, 0)
            size = max(1, min(available or 1, 4096))
            _code, data = self._win32file.ReadFile(self._handle, size)
            if not data:
                return b""
            self._buffer.extend(data)

    def write(self, data: bytes) -> None:
        self._win32file.WriteFile(self._handle, data)

    def close(self) -> None:
        self._win32file.CloseHandle(self._handle)


class AudioEngine(QObject):
    """Audio playback core used by the main window."""

    position_changed = pyqtSignal(int)  # current position in milliseconds
    duration_changed = pyqtSignal(int)  # total duration in milliseconds
    state_changed = pyqtSignal(str)     # "playing" / "paused" / "stopped"
    track_finished = pyqtSignal()       # current track reached EOF
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._player: Optional[_MpvIpcProcess] = None
        self._current_path: Optional[str] = None
        self._preloaded_path: Optional[str] = None
        self._gapless_handoff_path: Optional[str] = None
        self._duration_ms = 0
        self._position_ms = 0
        self._volume = 80
        self._playing = False
        self._loading_replacement = False
        self._stopping = False
        self._released = False
        self._finish_event_pending = False
        self._finish_fallback_triggered = False
        self._last_position_sync = 0.0
        self._last_duration_poll = 0.0

        try:
            self._player = _MpvIpcProcess()
            self._player.add_event_handler(self._on_mpv_event)
            self._player.command("set_property", "volume", self._volume)
        except Exception as exc:
            message = f"MPV backend is unavailable: {exc}"
            QTimer.singleShot(0, lambda: self.error_occurred.emit(message))
            self._init_error = exc

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)
        self._poll_timer.timeout.connect(self._poll_state)
        self._poll_timer.start()

    def load(self, path: str) -> bool:
        """Load a file without starting playback."""
        if not path or not os.path.exists(path):
            self.error_occurred.emit(f"File not found: {path}")
            return False
        if self._player is None:
            self.error_occurred.emit("MPV backend is unavailable.")
            return False

        if self._gapless_handoff_path and self._same_path(path, self._gapless_handoff_path):
            self._current_path = path
            self._preloaded_path = None
            self._gapless_handoff_path = None
            self._duration_ms = 0
            self._position_ms = 0
            self._finish_fallback_triggered = False
            self._last_position_sync = time.monotonic()
            self.duration_changed.emit(0)
            self.position_changed.emit(0)
            return True

        try:
            self._loading_replacement = True
            self._gapless_handoff_path = None
            self._preloaded_path = None
            self._player.command("set_property", "pause", True)
            self._player.command("loadfile", path, "replace")
            self._current_path = path
            self._duration_ms = 0
            self._position_ms = 0
            self._playing = False
            self._finish_fallback_triggered = False
            self._last_position_sync = time.monotonic()
            self.duration_changed.emit(0)
            self.position_changed.emit(0)
            self.state_changed.emit("paused")
            QTimer.singleShot(250, self._clear_loading_replacement)
            return True
        except Exception as exc:
            self._loading_replacement = False
            self.error_occurred.emit(f"Playback load failed: {exc}")
            return False

    def preload(self, path: Optional[str]) -> None:
        """Queue the next file in MPV so EOF handoff can be gapless."""
        if self._player is None:
            return
        if not path or not os.path.exists(path) or not self._current_path:
            self._clear_preload()
            return
        if self._same_path(path, self._current_path):
            self._clear_preload()
            return
        if self._preloaded_path and self._same_path(path, self._preloaded_path):
            return

        try:
            self._player.command("playlist-clear")
            self._player.command("loadfile", path, "append")
            self._preloaded_path = path
        except Exception:
            self._preloaded_path = None

    def play(self) -> None:
        if self._player is None or self._current_path is None:
            return
        try:
            self._stopping = False
            self._player.command("set_property", "pause", False, timeout=0.8)
            self._playing = True
            self._last_position_sync = time.monotonic()
            self.state_changed.emit("playing")
        except Exception as exc:
            self.error_occurred.emit(f"Playback failed: {exc}")

    def pause(self) -> None:
        if self._player is None:
            return
        try:
            self._player.command("set_property", "pause", True, timeout=0.8)
            self._position_ms = self._estimated_position_ms()
            self._last_position_sync = time.monotonic()
            self._playing = False
            self.state_changed.emit("paused")
        except Exception:
            pass

    def toggle_pause(self) -> None:
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        if self._player is None:
            return
        try:
            self._stopping = True
            self._clear_preload()
            self._player.command("stop", timeout=0.8)
            self._playing = False
            self._position_ms = 0
            self._last_position_sync = time.monotonic()
            self.position_changed.emit(0)
            self.state_changed.emit("stopped")
        except Exception:
            pass

    def seek(self, position_ms: int) -> None:
        if self._player is None or self._duration_ms <= 0:
            return
        position_ms = max(0, min(int(position_ms), self._duration_ms))
        try:
            self._player.command("seek", position_ms / 1000.0, "absolute", "exact", timeout=0.8)
            self._position_ms = position_ms
            self._last_position_sync = time.monotonic()
            self.position_changed.emit(position_ms)
        except Exception:
            pass

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        if self._player is None:
            return
        try:
            self._player.command("set_property", "volume", self._volume)
        except Exception:
            pass

    def get_volume(self) -> int:
        return self._volume

    def is_playing(self) -> bool:
        return self._playing

    def get_position(self) -> int:
        if self._playing:
            return self._estimated_position_ms()
        return self._position_ms

    def get_duration(self) -> int:
        return self._duration_ms

    def release(self) -> None:
        self._released = True
        try:
            self._poll_timer.stop()
        except Exception:
            pass
        if self._player is not None:
            self._player.close()

    def _on_mpv_event(self, event: Dict[str, Any]) -> None:
        if event.get("event") != "end-file":
            return
        if self._released or self._stopping or self._loading_replacement:
            return
        reason = str(event.get("reason") or "").lower()
        if reason and "eof" not in reason and reason not in {"end", "end-file"}:
            return
        if self._preloaded_path:
            self._gapless_handoff_path = self._preloaded_path
        else:
            self._playing = False
        self._last_position_sync = time.monotonic()
        self._queue_track_finished()

    def _queue_track_finished(self) -> None:
        if self._finish_event_pending:
            return
        self._finish_event_pending = True
        QTimer.singleShot(0, self._emit_track_finished)

    def _emit_track_finished(self) -> None:
        self._finish_event_pending = False
        if self._released or self._stopping:
            return
        self.track_finished.emit()

    def _poll_state(self) -> None:
        if self._player is None:
            return
        now = time.monotonic()
        if self._playing:
            estimated = self._estimated_position_ms(now)
            self.position_changed.emit(estimated)
            if now - self._last_position_sync >= 0.35:
                position = self._get_float_property("time-pos", timeout=0.05)
                if position is not None:
                    self._position_ms = max(0, int(position * 1000))
                    self._last_position_sync = now
            self._check_end_fallback(estimated)
        if self._duration_ms <= 0 or now - self._last_duration_poll >= 2.0:
            self._last_duration_poll = now
            duration = self._get_float_property("duration", timeout=0.05)
            if duration and duration > 0:
                duration_ms = int(duration * 1000)
                if abs(duration_ms - self._duration_ms) > 250:
                    self._duration_ms = duration_ms
                    self.duration_changed.emit(duration_ms)

    def _check_end_fallback(self, estimated_position_ms: int) -> None:
        if (
            self._finish_fallback_triggered
            or self._preloaded_path
            or self._duration_ms <= 0
            or estimated_position_ms < self._duration_ms - 120
        ):
            return
        idle = self._get_property("idle-active", timeout=0.05)
        if idle is True:
            self._finish_fallback_triggered = True
            self._playing = False
            self._position_ms = self._duration_ms
            self._queue_track_finished()

    def _estimated_position_ms(self, now: Optional[float] = None) -> int:
        if not self._playing or self._last_position_sync <= 0:
            return self._position_ms
        now = time.monotonic() if now is None else now
        estimated = self._position_ms + int((now - self._last_position_sync) * 1000)
        if self._duration_ms > 0:
            estimated = min(estimated, self._duration_ms)
        return max(0, estimated)

    def _clear_preload(self) -> None:
        self._preloaded_path = None
        self._gapless_handoff_path = None
        if self._player is None:
            return
        try:
            self._player.command("playlist-clear")
        except Exception:
            pass

    def _clear_loading_replacement(self) -> None:
        self._loading_replacement = False

    def _get_property(self, name: str, timeout: float = 0.4) -> Any:
        if self._player is None:
            return None
        try:
            return self._player.command("get_property", name, timeout=timeout)
        except Exception:
            return None

    def _get_float_property(self, name: str, timeout: float = 0.4) -> Optional[float]:
        value = self._get_property(name, timeout=timeout)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _same_path(a: str, b: str) -> bool:
        try:
            return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))
        except Exception:
            return a == b
