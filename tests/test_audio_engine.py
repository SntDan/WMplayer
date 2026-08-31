from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication

from core.audio_engine import AudioEngine


class _FakeMpvProcess:
    def __init__(self) -> None:
        self.commands = []
        self.callback = None
        self.closed = False

    def add_event_handler(self, callback) -> None:
        self.callback = callback

    def command(self, *command, **_kwargs):
        self.commands.append(command)
        return None

    def close(self) -> None:
        self.closed = True


class AudioEngineStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        patcher = patch("core.audio_engine._MpvIpcProcess", _FakeMpvProcess)
        self.addCleanup(patcher.stop)
        patcher.start()
        self.engine = AudioEngine()
        self.engine._poll_timer.stop()

    def tearDown(self) -> None:
        self.engine.release()

    def test_property_updates_keep_duration_position_and_pause_signals(self) -> None:
        duration_spy = QSignalSpy(self.engine.duration_changed)
        position_spy = QSignalSpy(self.engine.position_changed)
        state_spy = QSignalSpy(self.engine.state_changed)
        self.engine._current_path = "C:/current.flac"

        self.engine._on_mpv_property_change({"name": "duration", "data": 2.5})
        self.engine._on_mpv_property_change({"name": "time-pos", "data": 1.25})
        self.engine._on_mpv_property_change({"name": "pause", "data": False})

        self.assertEqual(self.engine._duration_ms, 2500)
        self.assertEqual(duration_spy[0][0], 2500)
        self.assertEqual(position_spy[0][0], 1250)
        self.assertEqual(state_spy[0][0], "playing")

    def test_preloaded_path_change_resets_timing_and_emits_handoff(self) -> None:
        handoff_spy = QSignalSpy(self.engine.backend_track_changed)
        self.engine._current_path = "C:/current.flac"
        self.engine._preloaded_path = "C:/next.flac"
        self.engine._duration_ms = 5000
        self.engine._position_ms = 4900

        self.engine._on_mpv_property_change({"name": "path", "data": "C:/next.flac"})

        self.assertEqual(self.engine._current_path, "C:/next.flac")
        self.assertIsNone(self.engine._preloaded_path)
        self.assertEqual(self.engine._duration_ms, 0)
        self.assertEqual(self.engine._position_ms, 0)
        self.assertEqual(handoff_spy[0][0], "C:/next.flac")


if __name__ == "__main__":
    unittest.main()
