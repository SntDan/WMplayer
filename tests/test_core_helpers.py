from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path

from core import lrc, m3u
from core.library import Library, _discover_audio_files, _metadata_from_cache
from core.metadata import TrackMetadata
from core.playlist_store import PlaylistStore


class CoreHelperTests(unittest.TestCase):
    def test_library_cache_round_trip_preserves_schema_without_cover_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            song = Path(directory) / "song.flac"
            song.touch()
            cache = Path(directory) / "cache.json"
            library = Library(str(cache))
            track = TrackMetadata(
                path=str(song),
                title="Song",
                artist="Artist",
                album="Album",
                duration_ms=1234,
                sample_rate=96000,
                bits_per_sample=24,
                track_number=7,
                cover=b"in-memory cover",
            )
            library.set_folders([directory, directory, ""])
            library._tracks = [track]
            library._save_cache()
            record = json.loads(cache.read_text(encoding="utf-8"))["tracks"][0]
            self.assertNotIn("cover", record)
            self.assertEqual(
                {key: value for key, value in record.items() if key != "path"},
                library._build_cache_dict()[str(song)],
            )
            restored = Library(str(cache))
            track.cover = None
            self.assertEqual(restored.tracks, [track])
            self.assertEqual(restored.folders, [directory])

            # Legacy caches allow numeric strings and missing metadata fields.
            cache.write_text(
                json.dumps({"tracks": [{"path": str(song), "duration_ms": "4321"}]}),
                encoding="utf-8",
            )
            restored = Library(str(cache)).tracks[0]
            self.assertEqual(
                (restored.title, restored.duration_ms, restored.track_number),
                ("", 4321, 0),
            )

    def test_library_dedup_preserves_first_position_and_best_quality(self):
        library = Library("")
        low = TrackMetadata("low.flac", title=" Song ", artist="Artist", album="Album")
        other = TrackMetadata("other.flac", title="Other")
        high = TrackMetadata(
            "high.flac", title="song", artist="artist", album="album", sample_rate=96000
        )
        tied = TrackMetadata(
            "tied.flac", title="song", artist="artist", album="album", sample_rate=96000
        )
        library._tracks = [low, other, high, tied]
        library._rebuild_display()
        self.assertEqual(library.tracks, [high, other])

    def test_library_discovery_filters_extensions_and_overlapping_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "album"
            nested.mkdir()
            supported = nested / "song.FLAC"
            supported.touch()
            (nested / "notes.txt").touch()

            files = _discover_audio_files([str(root), str(nested)])
            self.assertEqual(files, [str(supported)])

    def test_cached_metadata_conversion_keeps_all_persisted_fields(self) -> None:
        metadata = _metadata_from_cache(
            "song.flac",
            {
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "duration_ms": 1234,
                "sample_rate": 96000,
                "bits_per_sample": 24,
                "track_number": 7,
            },
        )
        self.assertEqual(metadata.title, "Song")
        self.assertEqual(metadata.track_number, 7)
        self.assertTrue(metadata.is_high_res())

    def test_playlist_store_keeps_default_precedence_and_ignores_non_playlists(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default = root / "default"
            extra = root / "extra"
            default.mkdir()
            extra.mkdir()
            (default / "A.m3u8").write_text("#EXTM3U\na.flac\n", encoding="utf-8")
            (extra / "A.m3u8").write_text("#EXTM3U\nother.flac\n", encoding="utf-8")
            (extra / "B.m3u").write_text("#EXTM3U\nb.flac\n", encoding="utf-8")
            (extra / "ignored.txt").touch()

            store = PlaylistStore(str(default))
            store.set_locations([str(extra)])
            self.assertEqual(store.list_names(), ["A", "B"])
            self.assertEqual(store.file_path("A"), os.path.abspath(default / "A.m3u8"))

    def test_m3u_and_lrc_parsers_keep_existing_formats(self) -> None:
        playlist = m3u.parse("#EXTM3U\nrelative/song.flac\nD:/music/a.mp3\n", "C:/base")
        self.assertEqual(playlist[0], os.path.normpath("C:/base/relative/song.flac"))
        self.assertEqual(playlist[1], "D:/music/a.mp3")

        lyrics = lrc.parse("[offset:100]\n[00:01.50][00:02.500]Line\nPlain")
        self.assertEqual([line.time_ms for line in lyrics.lines], [0, 1500, 2500])
        self.assertEqual(lyrics.index_at(1600), 1)


if __name__ == "__main__":
    unittest.main()
