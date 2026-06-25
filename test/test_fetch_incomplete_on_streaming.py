#!/usr/bin/env python3
"""
Unit tests for fetch_incomplete_on_streaming.py
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import fetch_incomplete_on_streaming as fis


# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------

SAMPLE_INCOMPLETE = [
    {
        "album_artist": "Radiohead",
        "album": "OK Computer",
        "album_dir": "/Music/Radiohead/OK Computer",
        "reason": "Gap(s) in track sequence: missing [3]",
        "local_tracks": 9,
        "declared_total": None,
        "mb_total": 12,
        "check_source": "local",
    },
    {
        "album_artist": "The Beatles",
        "album": "Abbey Road",
        "album_dir": "/Music/The Beatles/Abbey Road",
        "reason": "MusicBrainz expects 17 tracks; have 14 (3 missing)",
        "local_tracks": 14,
        "declared_total": None,
        "mb_total": 17,
        "check_source": "online",
    },
]

SAMPLE_STREAMING = {
    "deezer":       "https://www.deezer.com/album/12345",
    "spotify":      "https://open.spotify.com/album/abc",
    "apple_music":  None,
    "tidal":        None,
    "qobuz":        None,
    "amazon_music": None,
}


# ---------------------------------------------------------------------------
# load_incomplete_albums
# ---------------------------------------------------------------------------

class TestLoadIncompleteAlbums(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_loads_valid_json(self):
        p = self.tmp / "incomplete.json"
        p.write_text(json.dumps(SAMPLE_INCOMPLETE), encoding='utf-8')
        result = fis.load_incomplete_albums(p)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["album_artist"], "Radiohead")

    def test_returns_empty_for_missing_file(self):
        result = fis.load_incomplete_albums(Path("/nonexistent_xyz.json"))
        self.assertEqual(result, [])

    def test_returns_empty_list_for_empty_json(self):
        p = self.tmp / "empty.json"
        p.write_text("[]", encoding='utf-8')
        result = fis.load_incomplete_albums(p)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# search_albums_on_streaming
# ---------------------------------------------------------------------------

def _mock_searcher():
    """Return a mock StreamingSearcher whose search_all_services returns SAMPLE_STREAMING."""
    s = MagicMock()
    s.search_all_services.return_value = SAMPLE_STREAMING
    return s


class TestSearchAlbumsOnStreaming(unittest.TestCase):
    def test_calls_search_for_each_album(self):
        searcher = _mock_searcher()
        results = fis.search_albums_on_streaming(SAMPLE_INCOMPLETE, searcher=searcher)
        self.assertEqual(searcher.search_all_services.call_count, 2)
        self.assertEqual(len(results), 2)

    def test_result_contains_streaming_key(self):
        searcher = _mock_searcher()
        results = fis.search_albums_on_streaming(
            SAMPLE_INCOMPLETE[:1], searcher=searcher
        )
        self.assertIn("streaming", results[0])
        self.assertEqual(
            results[0]["streaming"]["deezer"], SAMPLE_STREAMING["deezer"]
        )

    def test_result_preserves_album_metadata(self):
        searcher = _mock_searcher()
        results = fis.search_albums_on_streaming(
            SAMPLE_INCOMPLETE[:1], searcher=searcher
        )
        r = results[0]
        self.assertEqual(r["album_artist"], "Radiohead")
        self.assertEqual(r["album"], "OK Computer")
        self.assertEqual(r["local_tracks"], 9)
        self.assertEqual(r["mb_total"], 12)

    def test_limit_is_respected(self):
        searcher = _mock_searcher()
        results = fis.search_albums_on_streaming(
            SAMPLE_INCOMPLETE, searcher=searcher, limit=1
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(searcher.search_all_services.call_count, 1)

    def test_empty_input(self):
        searcher = _mock_searcher()
        results = fis.search_albums_on_streaming([], searcher=searcher)
        self.assertEqual(results, [])
        searcher.search_all_services.assert_not_called()

    def test_creates_default_searcher_when_none(self):
        """When searcher=None a StreamingSearcher is instantiated internally."""
        with patch('fetch_incomplete_on_streaming.StreamingSearcher') as MockCls:
            instance = MockCls.return_value
            instance.search_all_services.return_value = SAMPLE_STREAMING
            results = fis.search_albums_on_streaming(SAMPLE_INCOMPLETE[:1])
        MockCls.assert_called_once()
        self.assertEqual(len(results), 1)


# ---------------------------------------------------------------------------
# write_text_report / write_json_report
# ---------------------------------------------------------------------------

def _make_result(**overrides):
    base = {
        "album_artist":   "Radiohead",
        "album":          "OK Computer",
        "reason":         "Gap at track 3",
        "local_tracks":   9,
        "declared_total": None,
        "mb_total":       12,
        "check_source":   "local",
        "streaming":      SAMPLE_STREAMING,
    }
    base.update(overrides)
    return base


class TestWriteReports(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_text_report_created(self):
        p = self.tmp / "report.txt"
        fis.write_text_report([_make_result()], p)
        self.assertTrue(p.exists())
        content = p.read_text(encoding='utf-8')
        self.assertIn("Radiohead", content)
        self.assertIn("OK Computer", content)
        self.assertIn("deezer", content)

    def test_json_report_created(self):
        p = self.tmp / "report.json"
        fis.write_json_report([_make_result()], p)
        self.assertTrue(p.exists())
        data = json.loads(p.read_text(encoding='utf-8'))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["album_artist"], "Radiohead")

    def test_text_report_shows_no_links_message(self):
        no_links = _make_result(streaming={k: None for k in SAMPLE_STREAMING})
        p = self.tmp / "no_links.txt"
        fis.write_text_report([no_links], p)
        self.assertIn("no streaming links found", p.read_text(encoding='utf-8'))

    def test_text_report_shows_mb_total(self):
        p = self.tmp / "mb.txt"
        fis.write_text_report([_make_result()], p)
        self.assertIn("12", p.read_text(encoding='utf-8'))

    def test_text_report_falls_back_to_declared_total(self):
        r = _make_result(mb_total=None, declared_total=11)
        p = self.tmp / "declared.txt"
        fis.write_text_report([r], p)
        self.assertIn("11", p.read_text(encoding='utf-8'))

    def test_json_report_is_valid_json(self):
        p = self.tmp / "valid.json"
        fis.write_json_report([_make_result()], p)
        data = json.loads(p.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)


if __name__ == '__main__':
    unittest.main()
