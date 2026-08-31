from __future__ import annotations

# Qt and config environment variables must be set before importing application modules.
# ruff: noqa: E402
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TEST_APPDATA = tempfile.TemporaryDirectory()
os.environ["APPDATA"] = _TEST_APPDATA.name

from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication

from core.library import Library
from core.metadata import TrackMetadata
from ui.albums_panel import AlbumsPanel
from ui.library_panel import LibraryPanel
from ui.main_window import MainWindow


class _FakeMpvProcess:
    def __init__(self) -> None:
        self.callback = None

    def add_event_handler(self, callback) -> None:
        self.callback = callback

    def command(self, *_command, **_kwargs):
        return None

    def close(self) -> None:
        pass


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        _TEST_APPDATA.cleanup()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.library = Library(os.path.join(self.temp_dir.name, "cache.json"))
        self.library._tracks = [
            TrackMetadata(
                path="C:/album/two.flac",
                title="Two",
                artist="Artist",
                album="Album",
                track_number=2,
            ),
            TrackMetadata(
                path="C:/album/one.flac",
                title="One",
                artist="Artist",
                album="Album",
                track_number=1,
            ),
        ]
        self.library._rebuild_display()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_library_double_click_emits_visible_queue_and_selected_index(self) -> None:
        panel = LibraryPanel(self.library)
        spy = QSignalSpy(panel.play_paths_now)
        selected = panel.list.item(1)

        panel._on_double_click(selected)

        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], ["C:/album/two.flac", "C:/album/one.flac"])
        self.assertEqual(spy[0][1], 1)

    def test_album_playback_stays_sequential_and_track_number_sorted(self) -> None:
        panel = AlbumsPanel(self.library)
        panel.show_album("Album")
        spy = QSignalSpy(panel.play_paths_sequential)

        panel._on_track_clicked(panel.list_tracks.item(1))

        self.assertEqual(len(spy), 1)
        self.assertEqual(spy[0][0], ["C:/album/one.flac", "C:/album/two.flac"])
        self.assertEqual(spy[0][1], 1)

    def test_main_window_builds_the_same_six_views_offscreen(self) -> None:
        with (
            patch("core.audio_engine._MpvIpcProcess", _FakeMpvProcess),
            patch("ui.main_window._MediaKeyHook._install"),
            patch.object(Library, "scan_async"),
        ):
            window = MainWindow()
            self.assertEqual(window.stack.count(), 6)
            self.assertEqual(window.stack.currentIndex(), window.VIEW_QUEUE)
            self.assertIs(
                window.stack.widget(window.VIEW_LIBRARY), window.library_panel
            )
            self.assertIs(window.stack.widget(window.VIEW_LYRICS), window.lyrics_panel)
            window.close()


if __name__ == "__main__":
    unittest.main()
