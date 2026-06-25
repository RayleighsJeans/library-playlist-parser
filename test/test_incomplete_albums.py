#!/usr/bin/env python3
"""
Unit tests for incomplete_albums.py
"""

import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import incomplete_albums as ia
from music_library import AUDIO_EXTENSIONS, scan_albums_in_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _touch(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _make_flac(album_dir: Path, track_num: int, total: int = 0,
               name: str | None = None) -> Path:
    """Create a dummy .flac file whose name encodes the track number."""
    filename = name or f"{track_num:02d} - Track {track_num}.flac"
    p = album_dir / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p


# ---------------------------------------------------------------------------
# _parse_track_num / _parse_total_tracks
# ---------------------------------------------------------------------------

class TestParseHelpers(unittest.TestCase):
    def test_plain_int(self):
        self.assertEqual(ia._parse_track_num("3"), 3)

    def test_zero_padded(self):
        self.assertEqual(ia._parse_track_num("03"), 3)

    def test_slash_format(self):
        self.assertEqual(ia._parse_track_num("3/12"), 3)

    def test_empty_returns_none(self):
        self.assertIsNone(ia._parse_track_num(""))
        self.assertIsNone(ia._parse_track_num(None))

    def test_parse_total_from_slash(self):
        self.assertEqual(ia._parse_total_tracks("3/12"), 12)

    def test_parse_total_plain_int(self):
        self.assertEqual(ia._parse_total_tracks("12"), 12)

    def test_parse_total_no_slash(self):
        # "3" alone is treated as the total itself
        self.assertEqual(ia._parse_total_tracks("3"), 3)

    def test_parse_total_empty(self):
        self.assertIsNone(ia._parse_total_tracks(""))


class TestTrackNumFromFilename(unittest.TestCase):
    def test_dash_separator(self):
        self.assertEqual(ia._track_num_from_filename("01 - Song Title.flac"), 1)

    def test_no_leading_number(self):
        self.assertIsNone(ia._track_num_from_filename("Song Title.flac"))

    def test_three_digit_number(self):
        self.assertEqual(ia._track_num_from_filename("101 - Track.flac"), 101)

    def test_dot_separator(self):
        self.assertEqual(ia._track_num_from_filename("05. Song.flac"), 5)


# ---------------------------------------------------------------------------
# check_local_completeness
# ---------------------------------------------------------------------------

class TestMusicLibraryHelpers(unittest.TestCase):
    """Verify that AUDIO_EXTENSIONS and scan_albums_in_dir work as expected."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_audio_extensions_contains_flac(self):
        self.assertIn('.flac', AUDIO_EXTENSIONS)

    def test_scan_albums_in_dir_yields_correct_tuple(self):
        d = self.tmp / "My Artist" / "My Album"
        d.mkdir(parents=True)
        (d / "01 - Track.flac").touch()
        results = list(scan_albums_in_dir(self.tmp))
        self.assertEqual(len(results), 1)
        artist, album, path = results[0]
        self.assertEqual(artist, "My Artist")
        self.assertEqual(album, "My Album")
        self.assertEqual(path, d)

    def test_scan_albums_in_dir_skips_non_audio(self):
        d = self.tmp / "Artist" / "Album"
        d.mkdir(parents=True)
        (d / "cover.jpg").touch()
        results = list(scan_albums_in_dir(self.tmp))
        self.assertEqual(results, [])


class TestCheckLocalCompleteness(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _album(self, name="Test Album"):
        d = self.tmp / "Artist" / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_no_audio_files(self):
        d = self._album()
        ok, reason, nums, total = ia.check_local_completeness(d)
        self.assertFalse(ok)
        self.assertIn("No audio files", reason)

    def test_complete_sequence(self):
        d = self._album()
        for i in (1, 2, 3):
            _make_flac(d, i)
        ok, reason, nums, _ = ia.check_local_completeness(d)
        # No tags, falls back to filename; sequence 1-3 is complete
        self.assertTrue(ok)
        self.assertEqual(sorted(nums), [1, 2, 3])

    def test_gap_detected(self):
        d = self._album()
        for i in (1, 2, 4):  # gap at 3
            _make_flac(d, i)
        ok, reason, nums, _ = ia.check_local_completeness(d)
        self.assertFalse(ok)
        self.assertIn("3", reason)

    def test_no_track_numbers_in_filename(self):
        d = self._album()
        (d / "Song A.flac").touch()
        (d / "Song B.flac").touch()
        ok, reason, nums, _ = ia.check_local_completeness(d)
        # Cannot determine numbers — treated as OK
        self.assertTrue(ok)
        self.assertEqual(nums, [])

    def test_duplicate_track_numbers_not_flagged(self):
        """Multi-format copies sharing a track number should not be a gap."""
        d = self._album()
        for i in (1, 2, 3):
            _make_flac(d, i, name=f"{i:02d} - Track.flac")
        # Add a second copy of track 2 with different extension
        (d / "02 - Track.mp3").touch()
        ok, reason, nums, _ = ia.check_local_completeness(d)
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# MusicBrainz helpers (mocked)
# ---------------------------------------------------------------------------

class TestMBHelpers(unittest.TestCase):
    def _mock_session(self, json_data, status=200):
        session = MagicMock()
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = json_data
        resp.raise_for_status = MagicMock()
        session.get.return_value = resp
        return session

    def test_mb_search_release_found(self):
        session = self._mock_session({
            "releases": [{"id": "abc-123", "title": "OK Computer"}]
        })
        with patch("time.sleep"):
            result = ia._mb_search_release("Radiohead", "OK Computer", session)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "abc-123")

    def test_mb_search_release_empty(self):
        session = self._mock_session({"releases": []})
        with patch("time.sleep"):
            result = ia._mb_search_release("Unknown", "Unknown Album", session)
        self.assertIsNone(result)

    def test_mb_search_release_exception(self):
        session = MagicMock()
        session.get.side_effect = Exception("network error")
        with patch("time.sleep"):
            result = ia._mb_search_release("A", "B", session)
        self.assertIsNone(result)

    def test_mb_track_count(self):
        session = self._mock_session({
            "media": [{"track-count": 8}, {"track-count": 4}]
        })
        with patch("time.sleep"):
            count = ia._mb_track_count("abc-123", session)
        self.assertEqual(count, 12)

    def test_mb_track_count_empty_media(self):
        session = self._mock_session({"media": []})
        with patch("time.sleep"):
            count = ia._mb_track_count("abc-123", session)
        self.assertIsNone(count)


# ---------------------------------------------------------------------------
# check_online_completeness
# ---------------------------------------------------------------------------

class TestCheckOnlineCompleteness(unittest.TestCase):
    def _session_returning(self, release, track_count):
        """Build a mock session that returns a given release + track count."""
        session = MagicMock()

        def _get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if "release/" in url and "search" not in url:
                # release detail
                resp.json.return_value = {
                    "media": [{"track-count": track_count}]
                }
            else:
                # search
                resp.json.return_value = {
                    "releases": [release] if release else []
                }
            return resp

        session.get.side_effect = _get
        return session

    def test_incomplete_online(self):
        session = self._session_returning({"id": "abc"}, track_count=12)
        with patch("time.sleep"):
            ok, reason, mb_total = ia.check_online_completeness(
                "Radiohead", "OK Computer", local_track_count=10, session=session
            )
        self.assertFalse(ok)
        self.assertEqual(mb_total, 12)
        self.assertIn("12", reason)

    def test_complete_online(self):
        session = self._session_returning({"id": "abc"}, track_count=10)
        with patch("time.sleep"):
            ok, reason, mb_total = ia.check_online_completeness(
                "Radiohead", "OK Computer", local_track_count=10, session=session
            )
        self.assertTrue(ok)
        self.assertEqual(mb_total, 10)

    def test_not_found_on_mb(self):
        session = self._session_returning(None, track_count=0)
        with patch("time.sleep"):
            ok, reason, mb_total = ia.check_online_completeness(
                "Unknown", "Unknown", local_track_count=5, session=session
            )
        self.assertTrue(ok)
        self.assertIsNone(mb_total)


# ---------------------------------------------------------------------------
# scan_library_for_incomplete (end-to-end with mocked online)
# ---------------------------------------------------------------------------

class TestScanLibraryForIncomplete(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _album_dir(self, artist, album):
        d = self.tmp / artist / album
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_complete_album_not_flagged(self):
        d = self._album_dir("Artist", "Complete Album")
        for i in (1, 2, 3):
            _make_flac(d, i)
        result = ia.scan_library_for_incomplete(self.tmp, online=False)
        self.assertEqual(result, [])

    def test_incomplete_album_flagged(self):
        d = self._album_dir("Artist", "Incomplete Album")
        for i in (1, 2, 4):  # gap at 3
            _make_flac(d, i)
        result = ia.scan_library_for_incomplete(self.tmp, online=False)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["album"], "Incomplete Album")
        self.assertIn("3", result[0]["reason"])

    def test_limit_respected(self):
        for i in range(5):
            d = self._album_dir(f"Artist{i}", "Album")
            for t in (1, 3):  # gap at 2 each
                _make_flac(d, t)
        result = ia.scan_library_for_incomplete(self.tmp, online=False, limit=2)
        self.assertLessEqual(len(result), 2)

    def test_empty_library(self):
        result = ia.scan_library_for_incomplete(self.tmp, online=False)
        self.assertEqual(result, [])

    def test_nonexistent_dir(self):
        result = ia.scan_library_for_incomplete(
            Path("/nonexistent_xyz"), online=False
        )
        self.assertEqual(result, [])

    def test_online_disabled_when_requests_unavailable(self):
        with patch.object(ia, 'REQUESTS_AVAILABLE', False):
            d = self._album_dir("Artist", "Album")
            for i in (1, 2, 3):
                _make_flac(d, i)
            result = ia.scan_library_for_incomplete(self.tmp, online=True)
        self.assertEqual(result, [])

    def test_result_structure(self):
        d = self._album_dir("My Artist", "Partial Album")
        for i in (1, 3):
            _make_flac(d, i)
        result = ia.scan_library_for_incomplete(self.tmp, online=False)
        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertIn("album_artist", entry)
        self.assertIn("album", entry)
        self.assertIn("reason", entry)
        self.assertIn("local_tracks", entry)
        self.assertIn("check_source", entry)
        self.assertEqual(entry["album_artist"], "My Artist")


if __name__ == '__main__':
    unittest.main()
