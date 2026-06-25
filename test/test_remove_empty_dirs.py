#!/usr/bin/env python3
"""
Unit tests for remove_empty_dirs.py
"""

import sys
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import remove_empty_dirs as red


class TestRemoveEmptyDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        # Cleanup whatever is left (test may have removed it)
        if self.tmp.exists():
            shutil.rmtree(self.tmp)

    # ------------------------------------------------------------------
    # Basic removal
    # ------------------------------------------------------------------

    def test_removes_single_empty_subdir(self):
        empty = self.tmp / "empty_dir"
        empty.mkdir()
        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertEqual(count, 1)
        self.assertFalse(empty.exists())

    def test_does_not_remove_dir_with_files(self):
        d = self.tmp / "has_file"
        d.mkdir()
        (d / "file.txt").touch()
        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertEqual(count, 0)
        self.assertTrue(d.exists())

    def test_removes_nested_empty_dirs(self):
        deep = self.tmp / "a" / "b" / "c"
        deep.mkdir(parents=True)
        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        # a, b, c should all be removed
        self.assertEqual(count, 3)
        self.assertFalse((self.tmp / "a").exists())

    def test_removes_only_empty_leaves(self):
        # Structure: root/kept/ (has file), root/gone/ (empty)
        kept = self.tmp / "kept"
        kept.mkdir()
        (kept / "track.flac").touch()

        gone = self.tmp / "gone"
        gone.mkdir()

        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertEqual(count, 1)
        self.assertTrue(kept.exists())
        self.assertFalse(gone.exists())

    def test_partial_tree_removal(self):
        """
        root/
          artist/
            has_album/     <- has a file
            empty_album/   <- empty
        Only empty_album should be removed; artist stays (has_album remains).
        """
        has_album = self.tmp / "artist" / "has_album"
        has_album.mkdir(parents=True)
        (has_album / "track.flac").touch()

        empty_album = self.tmp / "artist" / "empty_album"
        empty_album.mkdir(parents=True)

        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertEqual(count, 1)
        self.assertFalse(empty_album.exists())
        self.assertTrue(has_album.exists())
        self.assertTrue((self.tmp / "artist").exists())

    # ------------------------------------------------------------------
    # keep_root behaviour
    # ------------------------------------------------------------------

    def test_removes_root_when_empty_and_keep_root_false(self):
        empty_sub = self.tmp / "sub"
        empty_sub.mkdir()
        count = red.remove_empty_dirs(self.tmp, keep_root=False)
        # sub removed, then root removed
        self.assertFalse(self.tmp.exists())
        self.assertEqual(count, 2)

    def test_keep_root_preserves_root_even_when_empty(self):
        empty_sub = self.tmp / "sub"
        empty_sub.mkdir()
        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertTrue(self.tmp.exists())
        self.assertFalse(empty_sub.exists())
        self.assertEqual(count, 1)

    # ------------------------------------------------------------------
    # Dry-run
    # ------------------------------------------------------------------

    def test_dry_run_does_not_delete(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        count = red.remove_empty_dirs(self.tmp, dry_run=True, keep_root=True)
        self.assertEqual(count, 1)
        self.assertTrue(empty.exists())  # still there

    def test_dry_run_counts_correctly(self):
        for name in ("a", "b", "c"):
            (self.tmp / name).mkdir()
        count = red.remove_empty_dirs(self.tmp, dry_run=True, keep_root=True)
        self.assertEqual(count, 3)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_nonexistent_root_returns_zero(self):
        count = red.remove_empty_dirs(Path("/nonexistent_xyz_abc"), keep_root=True)
        self.assertEqual(count, 0)

    def test_file_as_root_returns_zero(self):
        f = self.tmp / "file.txt"
        f.touch()
        count = red.remove_empty_dirs(f, keep_root=True)
        self.assertEqual(count, 0)

    def test_already_clean_tree(self):
        d = self.tmp / "artist" / "album"
        d.mkdir(parents=True)
        (d / "track.flac").touch()
        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertEqual(count, 0)

    def test_returns_integer(self):
        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertIsInstance(count, int)

    def test_deeply_nested_empty_then_file_at_top(self):
        """
        root/
          artist/
            album/
              deep_empty/    <- empty
            track.flac       <- prevents album from being removed
        Only deep_empty is removed.
        """
        deep = self.tmp / "artist" / "album" / "deep_empty"
        deep.mkdir(parents=True)
        (self.tmp / "artist" / "album" / "track.flac").touch()

        count = red.remove_empty_dirs(self.tmp, keep_root=True)
        self.assertEqual(count, 1)
        self.assertFalse(deep.exists())
        self.assertTrue((self.tmp / "artist" / "album").exists())


if __name__ == '__main__':
    unittest.main()
