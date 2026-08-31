from __future__ import annotations

import unittest
from unittest.mock import patch

from core.metadata import TrackMetadata
from core.playlist import Playlist, PlayMode, RepeatMode


def _track(name: str) -> TrackMetadata:
    return TrackMetadata(path=f"C:/{name}.flac", title=name)


class PlaylistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracks = [_track("a"), _track("b"), _track("c")]
        self.playlist = Playlist()

    def test_replace_append_and_remove_keep_queue_indices_consistent(self) -> None:
        self.assertEqual(self.playlist.replace_with_tracks(self.tracks, 1), 1)
        self.assertIs(self.playlist.current, self.tracks[1])

        added = self.playlist.append_tracks([self.tracks[1], _track("d")])
        self.assertEqual(added, 1)
        self.assertEqual(
            self.playlist.paths, [track.path for track in self.tracks] + ["C:/d.flac"]
        )

        self.playlist.remove(0)
        self.assertEqual(self.playlist.current_index, 0)
        self.assertIs(self.playlist.current, self.tracks[1])

    def test_navigation_preserves_repeat_contract(self) -> None:
        self.playlist.replace_with_tracks(self.tracks, 2)
        self.assertIsNone(self.playlist.next_index(auto=True))
        self.assertEqual(self.playlist.next_index(auto=False), 0)

        self.playlist.set_repeat(RepeatMode.ALL)
        self.assertEqual(self.playlist.next_index(auto=True), 0)
        self.playlist.set_current(0)
        self.assertEqual(self.playlist.prev_index(), 2)

        self.playlist.set_repeat(RepeatMode.ONE)
        self.assertEqual(self.playlist.next_index(auto=True), 0)
        self.assertEqual(self.playlist.next_index(auto=False), 1)

    def test_shuffle_round_trip_restores_original_order_and_current_track(self) -> None:
        self.playlist.replace_with_tracks(self.tracks, 1)
        with patch(
            "core.playlist.random.shuffle", side_effect=lambda items: items.reverse()
        ):
            self.playlist.set_shuffled(True)

        self.assertEqual(self.playlist.paths, ["C:/b.flac", "C:/c.flac", "C:/a.flac"])
        self.assertIs(self.playlist.current, self.tracks[1])
        self.playlist.set_shuffled(False)
        self.assertEqual(self.playlist.paths, [track.path for track in self.tracks])
        self.assertEqual(self.playlist.current_index, 1)

    def test_legacy_mode_mapping_remains_compatible(self) -> None:
        self.playlist.set_mode(PlayMode.REPEAT_ALL)
        self.assertFalse(self.playlist.shuffled)
        self.assertEqual(self.playlist.repeat, RepeatMode.ALL)
        self.assertEqual(self.playlist.mode, PlayMode.REPEAT_ALL)

        self.playlist.set_mode(PlayMode.SHUFFLE)
        self.assertTrue(self.playlist.shuffled)
        self.assertEqual(self.playlist.repeat, RepeatMode.NONE)
        self.assertEqual(self.playlist.mode, PlayMode.SHUFFLE)


if __name__ == "__main__":
    unittest.main()
