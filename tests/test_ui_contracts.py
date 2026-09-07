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
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

from core.library import Library
from core.metadata import TrackMetadata
from core.playlist import Playlist
from ui.albums_panel import AlbumsPanel
from ui.library_panel import LibraryPanel
from ui.main_window import MainWindow
from ui.queue_panel import QueuePanel
from ui.list_delegates import ROLE_IS_PLAYING
from ui.list_helpers import suspended_updates


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

    def test_queue_filter_and_highlight_follow_indices_after_removal(self):
        playlist = Playlist()
        playlist.replace_with_tracks(self.library.tracks, 1)
        panel = QueuePanel(playlist)
        panel.search.setText("one")
        panel._apply_filter("one")
        self.assertTrue(panel.list.item(0).isHidden())
        self.assertTrue(panel.list.item(1).data(ROLE_IS_PLAYING))
        playlist.set_current(0)
        self.assertFalse(panel.list.item(1).data(ROLE_IS_PLAYING))
        self.assertTrue(panel.list.item(0).data(ROLE_IS_PLAYING))
        playlist.set_current(1)
        playlist.remove(0)
        item = panel.list.item(0)
        self.assertEqual(item.data(Qt.ItemDataRole.UserRole), 0)
        self.assertFalse(item.isHidden())
        self.assertTrue(item.data(ROLE_IS_PLAYING))
        spy = QSignalSpy(panel.track_double_clicked)
        panel._on_double_click(item)
        self.assertEqual(spy[0][0], 0)
        playlist.set_current(-1)
        self.assertTrue(item.data(ROLE_IS_PLAYING))  # Invalid indices are ignored.
        playlist.clear()
        self.assertEqual(panel.list.count(), 0)
        self.assertIsNone(panel._current_item)

    def test_suspended_updates_restores_nested_and_disabled_state_on_error(self):
        widget = QWidget()
        with suspended_updates(widget):
            with self.assertRaises(RuntimeError), suspended_updates(widget):
                raise RuntimeError("rebuild failed")
            self.assertFalse(widget.updatesEnabled())
        self.assertTrue(widget.updatesEnabled())
        widget.setUpdatesEnabled(False)
        with suspended_updates(widget):
            pass
        self.assertFalse(widget.updatesEnabled())

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
