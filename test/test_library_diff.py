#!/usr/bin/env python3
"""
Unit tests for library_diff.py
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import library_diff as ld
from music_library import normalise


def _make_album(root: Path, artist: str, album: str, tracks: int = 1) -> Path:
    """Create a minimal album directory with dummy audio files."""
    album_dir = root / artist / album
    album_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, tracks + 1):
        (album_dir / f"{i:02d} - Track {i}.flac").touch()
    return album_dir


class TestNormalise(unittest.TestCase):
    """music_library.normalise() (used internally by scan_album_dirs)."""

    def test_strips_and_lowercases(self):
        self.assertEqual(normalise("  The Beatles  "), "the beatles")

    def test_already_lower(self):
        self.assertEqual(normalise("radiohead"), "radiohead")


class TestScanLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_returns_empty_for_missing_dir(self):
        result = ld.scan_library(Path("/nonexistent_path_xyz"))
        self.assertEqual(result, {})

    def test_ignores_non_audio_dirs(self):
        artist_dir = self.tmp / "Artist"
        album_dir = artist_dir / "Album"
        album_dir.mkdir(parents=True)
        (album_dir / "cover.jpg").touch()           # no audio
        result = ld.scan_library(self.tmp)
        self.assertEqual(sum(len(v) for v in result.values()), 0)

    def test_finds_albums_with_audio(self):
        _make_album(self.tmp, "Radiohead", "OK Computer")
        _make_album(self.tmp, "Radiohead", "Kid A")
        result = ld.scan_library(self.tmp)
        self.assertIn("radiohead", result)
        self.assertEqual(len(result["radiohead"]), 2)

    def test_case_insensitive_keys(self):
        _make_album(self.tmp, "THE BEATLES", "Abbey Road")
        result = ld.scan_library(self.tmp)
        self.assertIn("the beatles", result)
        self.assertIn("abbey road", result["the beatles"])

    def test_multiple_artists(self):
        _make_album(self.tmp, "Artist A", "Album 1")
        _make_album(self.tmp, "Artist B", "Album 2")
        result = ld.scan_library(self.tmp)
        self.assertEqual(len(result), 2)

    def test_ignores_files_at_root(self):
        (self.tmp / "some_file.flac").touch()
        result = ld.scan_library(self.tmp)
        self.assertEqual(result, {})


class TestFindSurplus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "source"
        self.ref = self.tmp / "reference"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_no_surplus_when_identical(self):
        _make_album(self.src, "Artist", "Album")
        _make_album(self.ref, "Artist", "Album")
        surplus = ld.find_surplus(
            ld.scan_library(self.src), ld.scan_library(self.ref)
        )
        self.assertEqual(surplus, [])

    def test_detects_extra_album(self):
        _make_album(self.src, "Artist", "Album A")
        _make_album(self.src, "Artist", "Album B")   # only in source
        _make_album(self.ref, "Artist", "Album A")
        surplus = ld.find_surplus(
            ld.scan_library(self.src), ld.scan_library(self.ref)
        )
        self.assertEqual(len(surplus), 1)
        self.assertIn("Album B", str(surplus[0]))

    def test_detects_entirely_new_artist(self):
        _make_album(self.src, "New Artist", "Album")
        surplus = ld.find_surplus(ld.scan_library(self.src), {})
        self.assertEqual(len(surplus), 1)

    def test_case_insensitive_match_suppresses_surplus(self):
        _make_album(self.src, "THE BEATLES", "Abbey Road")
        _make_album(self.ref, "The Beatles", "abbey road")
        surplus = ld.find_surplus(
            ld.scan_library(self.src), ld.scan_library(self.ref)
        )
        self.assertEqual(surplus, [])

    def test_surplus_is_sorted(self):
        _make_album(self.src, "Artist", "Z Album")
        _make_album(self.src, "Artist", "A Album")
        surplus = ld.find_surplus(ld.scan_library(self.src), {})
        paths_lower = [str(p).lower() for p in surplus]
        self.assertEqual(paths_lower, sorted(paths_lower))


class TestTransferSurplus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "source"
        self.dest = self.tmp / "dest"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_copy_preserves_structure(self):
        album_dir = _make_album(self.src, "Artist", "Album", tracks=2)
        ok, fail = ld.transfer_surplus([album_dir], self.src, self.dest, move=False)
        self.assertEqual((ok, fail), (1, 0))
        self.assertTrue((self.dest / "Artist" / "Album").exists())
        self.assertTrue(album_dir.exists())     # source untouched

    def test_move_removes_source(self):
        album_dir = _make_album(self.src, "Artist", "Album", tracks=1)
        ok, fail = ld.transfer_surplus([album_dir], self.src, self.dest, move=True)
        self.assertEqual((ok, fail), (1, 0))
        self.assertFalse(album_dir.exists())
        self.assertTrue((self.dest / "Artist" / "Album").exists())

    def test_dry_run_does_not_transfer(self):
        album_dir = _make_album(self.src, "Artist", "Album")
        ok, fail = ld.transfer_surplus(
            [album_dir], self.src, self.dest, move=True, dry_run=True
        )
        self.assertEqual((ok, fail), (1, 0))
        self.assertTrue(album_dir.exists())     # not touched
        self.assertFalse((self.dest / "Artist" / "Album").exists())

    def test_invalid_path_counts_as_failure(self):
        outside = Path("/tmp_nonexistent_xyz/Artist/Album")
        ok, fail = ld.transfer_surplus([outside], self.src, self.dest)
        self.assertEqual((ok, fail), (0, 1))

    def test_copy_multiple_albums(self):
        a1 = _make_album(self.src, "Artist", "Album 1")
        a2 = _make_album(self.src, "Artist", "Album 2")
        ok, fail = ld.transfer_surplus([a1, a2], self.src, self.dest, move=False)
        self.assertEqual((ok, fail), (2, 0))


class TestBuildDiffReport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "source"
        self.ref = self.tmp / "reference"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_report_structure(self):
        album_dir = _make_album(self.src, "Artist", "Album")
        report = ld.build_diff_report(
            [album_dir], self.src, self.ref,
            destination=self.tmp / "out",
            move=True,
            dry_run=False,
        )
        self.assertEqual(report["surplus_count"], 1)
        self.assertIn("Artist/Album", report["surplus_albums"][0])
        self.assertEqual(report["action"], "move")
        self.assertFalse(report["dry_run"])

    def test_empty_surplus(self):
        report = ld.build_diff_report(
            [], self.src, self.ref, destination=None,
            move=False, dry_run=False,
        )
        self.assertEqual(report["surplus_count"], 0)
        self.assertEqual(report["surplus_albums"], [])

    def test_write_report_to_file(self):
        album_dir = _make_album(self.src, "Artist", "Album")
        report_file = self.tmp / "report.json"
        ld.write_report(
            [album_dir], self.src, self.ref,
            destination=self.tmp / "out",
            move=True, dry_run=False,
            report_file=report_file,
        )
        self.assertTrue(report_file.exists())
        with open(report_file) as f:
            data = json.load(f)
        self.assertEqual(data["surplus_count"], 1)


if __name__ == '__main__':
    unittest.main()
