#!/usr/bin/env python3
"""
Unit tests for album_overlap.py
"""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import album_overlap as ao

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audio_file(parent: Path, name: str) -> Path:
    """Touch a dummy .flac file."""
    p = parent / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p


def _make_album(root: Path, artist: str, album: str, tracks: int = 3) -> Path:
    """Create album_dir with *tracks* dummy .flac files named 01 - Track N.flac"""
    d = root / artist / album
    d.mkdir(parents=True, exist_ok=True)
    for i in range(1, tracks + 1):
        (d / f"{i:02d} - Track {i}.flac").touch()
    return d


def _fp(title: str, artist: str = "", dur: float = 0.0, bucket: int = 5) -> str:
    """Compute the expected fingerprint the same way album_overlap does."""
    return ao.make_track_fingerprint(title, artist, dur, bucket=bucket)


# Fake metadata dict (as stored in MusicLibraryCache.cache)
def _cached_meta(title: str, artist: str = "Test Artist") -> dict:
    title_norm  = title.lower().strip()
    artist_norm = artist.lower().strip()
    return {
        'title': title,
        'artist': artist,
        'title_norm': title_norm,
        'artist_norm': artist_norm,
    }


# ---------------------------------------------------------------------------
# _bucket
# ---------------------------------------------------------------------------

class TestBucket(unittest.TestCase):
    def test_exact_multiple(self):
        self.assertEqual(ao._bucket(10.0, 5), 10)

    def test_rounds_down(self):
        self.assertEqual(ao._bucket(12.0, 5), 10)

    def test_rounds_up(self):
        self.assertEqual(ao._bucket(13.0, 5), 15)

    def test_none_returns_zero(self):
        self.assertEqual(ao._bucket(None, 5), 0)

    def test_custom_bucket(self):
        self.assertEqual(ao._bucket(9.0, 3), 9)
        self.assertEqual(ao._bucket(10.0, 3), 9)


# ---------------------------------------------------------------------------
# make_track_fingerprint
# ---------------------------------------------------------------------------

class TestMakeTrackFingerprint(unittest.TestCase):
    def test_returns_eight_char_hex(self):
        fp = ao.make_track_fingerprint("Song", "Artist", 120.0)
        self.assertEqual(len(fp), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in fp))

    def test_same_inputs_same_hash(self):
        a = ao.make_track_fingerprint("Song", "Artist", 120.0)
        b = ao.make_track_fingerprint("Song", "Artist", 120.0)
        self.assertEqual(a, b)

    def test_different_title_different_hash(self):
        a = ao.make_track_fingerprint("Song A", "Artist", 120.0)
        b = ao.make_track_fingerprint("Song B", "Artist", 120.0)
        self.assertNotEqual(a, b)

    def test_duration_bucket_tolerance(self):
        """Durations within the same 5-second bucket hash identically."""
        a = ao.make_track_fingerprint("Song", "Artist", 120.0)
        b = ao.make_track_fingerprint("Song", "Artist", 121.9)  # same bucket
        self.assertEqual(a, b)

    def test_duration_bucket_boundary(self):
        """Durations in different buckets hash differently."""
        a = ao.make_track_fingerprint("Song", "Artist", 120.0)  # bucket 120
        b = ao.make_track_fingerprint("Song", "Artist", 123.0)  # bucket 125
        self.assertNotEqual(a, b)

    def test_empty_title_falls_back_to_filename_stem(self):
        """When title is empty the filename stem is used as identity."""
        a = ao.make_track_fingerprint("", "", 0.0, filename_stem="03 - my track")
        b = ao.make_track_fingerprint("", "", 0.0, filename_stem="03 - my track")
        self.assertEqual(a, b)

    def test_empty_title_different_stems_differ(self):
        a = ao.make_track_fingerprint("", "", 0.0, filename_stem="track_a")
        b = ao.make_track_fingerprint("", "", 0.0, filename_stem="track_b")
        self.assertNotEqual(a, b)


# ---------------------------------------------------------------------------
# jaccard
# ---------------------------------------------------------------------------

class TestJaccard(unittest.TestCase):
    def test_identical_sets(self):
        s = frozenset({"a", "b", "c"})
        self.assertAlmostEqual(ao.jaccard(s, s), 1.0)

    def test_disjoint_sets(self):
        a = frozenset({"a", "b"})
        b = frozenset({"c", "d"})
        self.assertAlmostEqual(ao.jaccard(a, b), 0.0)

    def test_partial_overlap(self):
        a = frozenset({"a", "b", "c"})  # 3 elements
        b = frozenset({"b", "c", "d"})  # 3 elements, 2 common
        # |A ∩ B| = 2, |A ∪ B| = 4
        self.assertAlmostEqual(ao.jaccard(a, b), 2 / 4)

    def test_empty_both(self):
        self.assertAlmostEqual(ao.jaccard(frozenset(), frozenset()), 0.0)

    def test_one_empty(self):
        a = frozenset({"x"})
        self.assertAlmostEqual(ao.jaccard(a, frozenset()), 0.0)

    def test_subset(self):
        a = frozenset({"a", "b", "c", "d"})
        b = frozenset({"a", "b"})
        # |A ∩ B| = 2, |A ∪ B| = 4
        self.assertAlmostEqual(ao.jaccard(a, b), 0.5)


# ---------------------------------------------------------------------------
# build_track_fingerprints
# ---------------------------------------------------------------------------

class TestBuildTrackFingerprints(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_cache(self, file_meta: dict) -> MagicMock:
        """
        Return a mock MusicLibraryCache whose .cache attribute contains
        the given mapping and whose .extract_metadata returns None for
        anything not in the map.
        """
        mock = MagicMock()
        mock.cache = file_meta
        mock.extract_metadata.return_value = None
        return mock

    def test_empty_dir_returns_empty_frozenset(self):
        d = self.tmp / "empty_album"
        d.mkdir()
        cache = self._make_cache({})
        result = ao.build_track_fingerprints(d, cache)
        self.assertEqual(result, frozenset())

    def test_non_audio_files_ignored(self):
        d = self.tmp / "album"
        d.mkdir()
        (d / "cover.jpg").touch()
        (d / "info.txt").touch()
        cache = self._make_cache({})
        result = ao.build_track_fingerprints(d, cache)
        self.assertEqual(result, frozenset())

    def test_uses_cached_metadata(self):
        d = self.tmp / "album"
        d.mkdir()
        f = d / "01 - Song.flac"
        f.touch()
        file_meta = {str(f): _cached_meta("Song", "Artist")}
        cache = self._make_cache(file_meta)

        with patch.object(ao, 'get_duration', return_value=120.0):
            result = ao.build_track_fingerprints(d, cache)

        expected_fp = ao.make_track_fingerprint("song", "artist", 120.0)
        self.assertIn(expected_fp, result)
        self.assertEqual(len(result), 1)

    def test_falls_back_to_extract_metadata_when_not_cached(self):
        d = self.tmp / "album"
        d.mkdir()
        f = d / "01 - Song.flac"
        f.touch()

        meta = _cached_meta("Uncached Song", "Artist")
        cache = self._make_cache({})          # empty cache
        cache.extract_metadata.return_value = meta

        with patch.object(ao, 'get_duration', return_value=90.0):
            result = ao.build_track_fingerprints(d, cache)

        expected = ao.make_track_fingerprint("uncached song", "artist", 90.0)
        self.assertIn(expected, result)

    def test_multiple_tracks_produce_multiple_hashes(self):
        d = self.tmp / "album"
        d.mkdir()
        files_meta = {}
        for i in range(1, 4):
            f = d / f"{i:02d} - Track {i}.flac"
            f.touch()
            files_meta[str(f)] = _cached_meta(f"Track {i}")
        cache = self._make_cache(files_meta)

        with patch.object(ao, 'get_duration', return_value=float(i * 30)):
            result = ao.build_track_fingerprints(d, cache)

        self.assertEqual(len(result), 3)

    def test_duplicate_tracks_deduplicated(self):
        """Two files with identical fingerprint → only one hash in the set."""
        d = self.tmp / "album"
        d.mkdir()
        f1 = d / "01 - Song.flac"
        f2 = d / "01 - Song (bonus).flac"
        f1.touch()
        f2.touch()
        # Both share same normalised title + artist + duration → same hash
        meta = _cached_meta("Song", "Artist")
        cache = self._make_cache({str(f1): meta, str(f2): meta})

        with patch.object(ao, 'get_duration', return_value=120.0):
            result = ao.build_track_fingerprints(d, cache)

        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# find_overlapping_albums  (integration — mocks the cache layer)
# ---------------------------------------------------------------------------

class TestFindOverlappingAlbums(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _full_cache(self, dir_structure: dict) -> MagicMock:
        """
        dir_structure: { str(file_path): (title, artist) }
        Returns a mock MusicLibraryCache.
        """
        mock = MagicMock()
        mock.load_cache.return_value = True
        mock.cache = {
            path: _cached_meta(title, artist)
            for path, (title, artist) in dir_structure.items()
        }
        mock.extract_metadata.return_value = None
        mock.normalize_string.side_effect = lambda s: s.lower().strip()
        return mock

    def _make_library(self, structure: dict) -> dict:
        """
        structure: { artist -> { album -> [title, ...] } }
        Creates files in self.tmp and returns cache file map.
        """
        cache_map = {}
        for artist, albums in structure.items():
            for album, titles in albums.items():
                d = self.tmp / artist / album
                d.mkdir(parents=True, exist_ok=True)
                for i, title in enumerate(titles, 1):
                    f = d / f"{i:02d} - {title}.flac"
                    f.touch()
                    cache_map[str(f)] = (title, artist)
        return cache_map

    def test_identical_albums_detected(self):
        """Two albums with the same tracks should report 100% overlap."""
        titles = ["Song A", "Song B", "Song C"]
        cache_map = self._make_library({
            "Artist": {
                "Album 1": titles,
                "Album 2": titles,
            }
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=120.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.9,
                    use_cache=True, force_rebuild=False,
                )

        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["overlap"], 1.0)
        self.assertEqual(results[0]["album_artist"], "Artist")
        # new fields must be present
        self.assertIn("keep",       results[0])
        self.assertIn("path_a",     results[0])
        self.assertIn("path_b",     results[0])
        self.assertIn("year_a",     results[0])
        self.assertIn("year_b",     results[0])
        self.assertIn("duration_a", results[0])
        self.assertIn("duration_b", results[0])

    def test_no_overlap_not_reported(self):
        """Albums with completely different tracks produce no results."""
        cache_map = self._make_library({
            "Artist": {
                "Album 1": ["Song A", "Song B"],
                "Album 2": ["Song C", "Song D"],
            }
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=120.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.5,
                    use_cache=True, force_rebuild=False,
                )

        self.assertEqual(results, [])

    def test_partial_overlap_above_threshold_reported(self):
        """3 shared / 4 unique = 0.75 Jaccard → above 0.5 threshold."""
        cache_map = self._make_library({
            "Artist": {
                "Album 1": ["A", "B", "C"],
                "Album 2": ["A", "B", "C", "D"],
            }
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=120.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.5,
                    use_cache=True, force_rebuild=False,
                )

        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0]["overlap"], 3 / 4)

    def test_partial_overlap_below_threshold_not_reported(self):
        """Same data but threshold raised above the score."""
        cache_map = self._make_library({
            "Artist": {
                "Album 1": ["A", "B", "C"],
                "Album 2": ["A", "B", "C", "D"],
            }
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=120.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.9,
                    use_cache=True, force_rebuild=False,
                )

        self.assertEqual(results, [])

    def test_no_cross_artist_comparison(self):
        """Overlap is never computed across different artists."""
        # Both artists have the same track titles — must not be paired
        cache_map = self._make_library({
            "Artist A": {"Album 1": ["Song X", "Song Y"]},
            "Artist B": {"Album 1": ["Song X", "Song Y"]},
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=120.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.0,
                    use_cache=True, force_rebuild=False,
                )

        # Each artist only has one album → no pairs within any artist
        self.assertEqual(results, [])

    def test_results_sorted_descending(self):
        """Results must come back in descending order of overlap."""
        cache_map = self._make_library({
            "Artist": {
                "Album 1": ["A", "B", "C"],
                "Album 2": ["A", "B", "C", "D"],  # 3/4 = 0.75
                "Album 3": ["A", "B"],             # 2/3 = 0.67 vs Album 1
            }
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=120.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.0,
                    use_cache=True, force_rebuild=False,
                )

        scores = [r["overlap"] for r in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_result_dict_keys(self):
        """Each result dict must contain all required keys."""
        cache_map = self._make_library({
            "Artist": {
                "Album 1": ["A", "B"],
                "Album 2": ["A", "B"],
            }
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=60.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.0,
                    use_cache=True, force_rebuild=False,
                )

        required = {
            "album_artist", "album_a", "album_b",
            "overlap", "common_tracks", "total_tracks",
            "tracks_a", "tracks_b",
            # new fields
            "path_a", "path_b", "year_a", "year_b",
            "duration_a", "duration_b", "keep",
        }
        self.assertTrue(required.issubset(results[0].keys()))

    def test_single_album_per_artist_skipped(self):
        """An artist with only one album cannot form a pair."""
        cache_map = self._make_library({
            "Solo Artist": {"Only Album": ["A", "B", "C"]},
        })

        with patch('album_overlap.MusicLibraryCache') as MockCache:
            inst = self._full_cache(cache_map)
            MockCache.return_value = inst
            with patch.object(ao, 'get_duration', return_value=120.0):
                results = ao.find_overlapping_albums(
                    self.tmp, threshold=0.0,
                    use_cache=True, force_rebuild=False,
                )

        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

class TestReportWriters(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample = [
            {
                "album_artist":  "Radiohead",
                "album_a":       "OK Computer",
                "album_b":       "OK Computer OKNOTOK",
                "overlap":       0.75,
                "common_tracks": 9,
                "total_tracks":  12,
                "tracks_a":      12,
                "tracks_b":      15,
                "path_a":        "/Music/Radiohead/OK Computer",
                "path_b":        "/Music/Radiohead/OK Computer OKNOTOK",
                "year_a":        1997,
                "year_b":        2017,
                "duration_a":    2580.0,
                "duration_b":    3120.0,
                "keep":          "b",
            }
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_text_report_created(self):
        p = self.tmp / "report.txt"
        ao.write_text_report(self.sample, p)
        self.assertTrue(p.exists())
        content = p.read_text(encoding='utf-8')
        self.assertIn("Radiohead", content)
        self.assertIn("75%", content)
        self.assertIn("9 common", content)

    def test_text_report_shows_paths(self):
        p = self.tmp / "paths.txt"
        ao.write_text_report(self.sample, p)
        content = p.read_text(encoding='utf-8')
        self.assertIn("/Music/Radiohead/OK Computer", content)
        self.assertIn("/Music/Radiohead/OK Computer OKNOTOK", content)

    def test_text_report_shows_years(self):
        p = self.tmp / "years.txt"
        ao.write_text_report(self.sample, p)
        content = p.read_text(encoding='utf-8')
        self.assertIn("1997", content)
        self.assertIn("2017", content)

    def test_text_report_shows_keep_label(self):
        p = self.tmp / "keep.txt"
        ao.write_text_report(self.sample, p)
        content = p.read_text(encoding='utf-8')
        # keep='b' → label should mention album_b name
        self.assertIn("OK Computer OKNOTOK", content)
        self.assertIn("keep", content.lower())

    def test_text_report_keep_a(self):
        sample = [{**self.sample[0], "keep": "a"}]
        p = self.tmp / "keep_a.txt"
        ao.write_text_report(sample, p)
        content = p.read_text(encoding='utf-8')
        self.assertIn("→ keep: 'OK Computer'", content)

    def test_text_report_keep_either(self):
        sample = [{**self.sample[0], "keep": "either"}]
        p = self.tmp / "either.txt"
        ao.write_text_report(sample, p)
        content = p.read_text(encoding='utf-8')
        self.assertIn("either", content)

    def test_text_report_unknown_year_shown_as_question_mark(self):
        sample = [{**self.sample[0], "year_a": 0, "year_b": 0}]
        p = self.tmp / "unknown_year.txt"
        ao.write_text_report(sample, p)
        content = p.read_text(encoding='utf-8')
        self.assertIn("year=?", content)

    def test_json_report_created(self):
        p = self.tmp / "report.json"
        ao.write_json_report(self.sample, p)
        self.assertTrue(p.exists())
        data = json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["album_artist"], "Radiohead")

    def test_json_report_is_valid_json(self):
        p = self.tmp / "valid.json"
        ao.write_json_report(self.sample, p)
        data = json.loads(p.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)

    def test_text_report_empty_results(self):
        p = self.tmp / "empty.txt"
        ao.write_text_report([], p)
        self.assertTrue(p.exists())
        content = p.read_text(encoding='utf-8')
        self.assertIn("Album Overlap Report", content)


# ---------------------------------------------------------------------------
# get_album_stats
# ---------------------------------------------------------------------------

class TestGetAlbumStats(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make_cache(self, file_meta: dict) -> MagicMock:
        mock = MagicMock()
        mock.cache = file_meta
        mock.extract_metadata.return_value = None
        return mock

    def test_empty_dir_returns_zero_stats(self):
        d = self.tmp / "empty"
        d.mkdir()
        cache = self._make_cache({})
        with patch.object(ao, 'get_duration', return_value=None):
            stats = ao.get_album_stats(d, cache)
        self.assertEqual(stats["track_count"],    0)
        self.assertEqual(stats["total_duration"], 0.0)
        self.assertEqual(stats["year"],           0)
        self.assertEqual(stats["path"],           str(d))

    def test_counts_audio_files_only(self):
        d = self.tmp / "album"
        d.mkdir()
        (d / "01 - track.flac").touch()
        (d / "02 - track.flac").touch()
        (d / "cover.jpg").touch()
        cache = self._make_cache({})
        with patch.object(ao, 'get_duration', return_value=200.0):
            stats = ao.get_album_stats(d, cache)
        self.assertEqual(stats["track_count"], 2)

    def test_sums_durations(self):
        d = self.tmp / "album"
        d.mkdir()
        for i in (1, 2, 3):
            (d / f"{i:02d} - track.flac").touch()
        cache = self._make_cache({})
        with patch.object(ao, 'get_duration', return_value=100.0):
            stats = ao.get_album_stats(d, cache)
        self.assertAlmostEqual(stats["total_duration"], 300.0, places=0)

    def test_year_from_cached_date_tag(self):
        d = self.tmp / "album"
        d.mkdir()
        f = d / "01 - track.flac"
        f.touch()
        cache = self._make_cache({str(f): {**_cached_meta("T"), "date": "2001"}})
        with patch.object(ao, 'get_duration', return_value=0.0):
            stats = ao.get_album_stats(d, cache)
        self.assertEqual(stats["year"], 2001)

    def test_year_from_album_dir_name_fallback(self):
        """When no date tag exists, parse year from the directory name."""
        d = self.tmp / "OK Computer (1997 Remaster)"
        d.mkdir()
        f = d / "01 - track.flac"
        f.touch()
        cache = self._make_cache({})   # no tags cached
        with patch.object(ao, 'get_duration', return_value=0.0):
            with patch.object(ao, 'MutagenFile', return_value=None):
                stats = ao.get_album_stats(d, cache)
        self.assertEqual(stats["year"], 1997)

    def test_year_is_minimum_across_tracks(self):
        """If tracks have different years (edge case), take the minimum."""
        d = self.tmp / "album"
        d.mkdir()
        f1 = d / "01 - t.flac"
        f2 = d / "02 - t.flac"
        f1.touch(); f2.touch()
        cache = self._make_cache({
            str(f1): {**_cached_meta("T"), "date": "2005"},
            str(f2): {**_cached_meta("T2"), "date": "1997"},
        })
        with patch.object(ao, 'get_duration', return_value=0.0):
            stats = ao.get_album_stats(d, cache)
        self.assertEqual(stats["year"], 1997)


# ---------------------------------------------------------------------------
# _keep_recommendation
# ---------------------------------------------------------------------------

class TestKeepRecommendation(unittest.TestCase):
    def _s(self, tracks=10, year=2000, duration=3000.0) -> dict:
        return {"track_count": tracks, "year": year, "total_duration": duration}

    def test_more_tracks_wins(self):
        self.assertEqual(ao._keep_recommendation(self._s(12), self._s(10)), 'a')
        self.assertEqual(ao._keep_recommendation(self._s(10), self._s(12)), 'b')

    def test_newer_year_breaks_track_tie(self):
        self.assertEqual(ao._keep_recommendation(self._s(10, 2020), self._s(10, 1997)), 'a')
        self.assertEqual(ao._keep_recommendation(self._s(10, 1997), self._s(10, 2020)), 'b')

    def test_unknown_year_loses_to_known(self):
        self.assertEqual(ao._keep_recommendation(self._s(10, 1997), self._s(10, 0)),   'a')
        self.assertEqual(ao._keep_recommendation(self._s(10, 0),    self._s(10, 1997)), 'b')

    def test_longer_duration_breaks_full_tie(self):
        self.assertEqual(ao._keep_recommendation(
            self._s(10, 2000, 4000.0), self._s(10, 2000, 2000.0)
        ), 'a')

    def test_exact_tie_returns_either(self):
        self.assertEqual(ao._keep_recommendation(self._s(), self._s()), 'either')

    def test_duration_tolerance_one_second(self):
        """Differences ≤ 1 second are treated as ties."""
        self.assertEqual(ao._keep_recommendation(
            self._s(10, 2000, 3000.5), self._s(10, 2000, 3000.0)
        ), 'either')


# ---------------------------------------------------------------------------
# _fmt_duration
# ---------------------------------------------------------------------------

class TestFmtDuration(unittest.TestCase):
    def test_minutes_seconds(self):
        self.assertEqual(ao._fmt_duration(185.0), "3:05")

    def test_hours_minutes_seconds(self):
        self.assertEqual(ao._fmt_duration(3661.0), "1:01:01")

    def test_zero(self):
        self.assertEqual(ao._fmt_duration(0.0), "0:00")

    def test_exactly_one_hour(self):
        self.assertEqual(ao._fmt_duration(3600.0), "1:00:00")


if __name__ == '__main__':
    unittest.main()
