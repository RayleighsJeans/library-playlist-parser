#!/usr/bin/env python3
"""
Unit tests for playlist_matcher.py

Converts the test_playlist_matcher.ipynb notebook into a proper unit test suite.
"""

import os
import sys
import shutil
import unittest
from pathlib import Path

# Add parent directory to path to import playlist_matcher
sys.path.insert(0, str(Path(__file__).parent.parent))

import playlist_matcher as pm
from playlist_matcher import MusicLibraryCache, PlaylistMatcher
from mutagen.flac import FLAC


class TestHelpers:
    """Helper functions for testing"""
    
    @staticmethod
    def sanitize_filename(name):
        """Sanitize a string for use in filenames by replacing problematic characters"""
        # Replace forward slash with unicode division slash
        name = name.replace('/', '∕')  # Unicode division slash U+2215
        
        # Replace other problematic characters
        replacements = {
            '\\': '∖',  # Backslash
            ':': '∶',   # Colon  
            '*': '∗',   # Asterisk
            '?': '？',  # Question mark
            '"': '＂',  # Quote
            '<': '＜',  # Less than
            '>': '＞',  # Greater than
            '|': '｜',  # Pipe
        }
        
        for old, new in replacements.items():
            name = name.replace(old, new)
        
        return name
    
    @staticmethod
    def sanitize_path_component(name):
        """Sanitize directory/album names"""
        return TestHelpers.sanitize_filename(name)


class TestPlaylistMatcher(unittest.TestCase):
    """Test suite for playlist_matcher.py"""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures once for all tests"""
        cls.test_dir = Path(__file__).parent
        cls.template_path = cls.test_dir / 'example.flac'
        cls.music_dir = cls.test_dir / 'test_music_library'
        cls.test_playlist = cls.test_dir / 'test_playlist.m3u8'
        cls.test_text_playlist = cls.test_dir / 'test_text_playlist.txt'
        cls.output_playlist = cls.test_dir / 'test_output.m3u8'
        cls.output_log = cls.test_dir / 'test_unmatched.log'
        cls.text_output_playlist = cls.test_dir / 'test_text_output.m3u8'
        cls.text_output_log = cls.test_dir / 'test_text_unmatched.log'
        
        # Test data: First 10 songs from Favourites.m3u8
        cls.test_entries = [
            {
                'artist': 'The Offspring',
                'title': "(Can't Get My) Head Around You",
                'album': 'Splinter',
                'disc': '1',
                'track': '164',
                'ext': 'flac',
                'duration': '135'
            },
            {
                'artist': 'Santana',
                'title': '(Da Le) Yaleo',
                'album': 'Supernatural (Remastered)',
                'disc': '1',
                'track': '208',
                'ext': 'flac',
                'duration': '352'
            },
            {
                'artist': 'Jamiroquai',
                'title': "(Don't) Give Hate a Chance",
                'album': 'Dynamite',
                'disc': '1',
                'track': '247',
                'ext': 'flac',
                'duration': '300'
            },
            {
                'artist': 'The Rolling Stones',
                'title': '(I Can\'t Get No) Satisfaction - Mono',
                'album': 'Out Of Our Heads',
                'disc': '1',
                'track': '458',
                'ext': 'flac',
                'duration': '223'
            },
            {
                'artist': 'JAY-Z, Beyoncé',
                'title': "03' Bonnie & Clyde",
                'album': 'The Blueprint 2 The Gift & The Curse',
                'disc': '1',
                'track': '1',
                'ext': 'flac',
                'duration': '206'
            },
            {
                'artist': 'Die Ärzte',
                'title': '1/2 Lovesong',  # Note: / in title
                'album': '13',
                'disc': '1',
                'track': '2',
                'ext': 'flac',
                'duration': '235'
            },
            {
                'artist': 'Ciara, Missy Elliott',
                'title': '1, 2 Step (feat. Missy Elliott)',
                'album': 'Goodies',
                'disc': '1',
                'track': '3',
                'ext': 'flac',
                'duration': '204'
            },
            {
                'artist': 'Gorillaz',
                'title': '19-2000 - Soulchild Remix',
                'album': 'Gorillaz',
                'disc': '1',
                'track': '4',
                'ext': 'flac',
                'duration': '209'
            },
            {
                'artist': 'A Tribe Called Quest',
                'title': '1nce again',
                'album': 'From NYC',
                'disc': '1',
                'track': '5',
                'ext': 'flac',
                'duration': '233'
            },
            {
                'artist': '2Pac, Snoop Dogg',
                'title': '2 Of Amerikaz Most Wanted (ft. Snoop Doggy Dogg)',
                'album': 'All Eyez On Me',
                'disc': '1',
                'track': '8',
                'ext': 'flac',
                'duration': '247'
            }
        ]
    
    def setUp(self):
        """Set up before each test"""
        # Clean up any existing test files
        self._cleanup_test_files()
    
    def tearDown(self):
        """Clean up after each test"""
        self._cleanup_test_files()
    
    def _cleanup_test_files(self):
        """Remove test files and directories"""
        if self.music_dir.exists():
            shutil.rmtree(self.music_dir)
        
        for file_path in [self.test_playlist, self.test_text_playlist, 
                         self.output_playlist, self.output_log,
                         self.text_output_playlist, self.text_output_log]:
            if file_path.exists():
                file_path.unlink()
    
    def _create_mock_library(self, entries):
        """Create mock music library by copying template and modifying metadata"""
        if not self.template_path.exists():
            self.skipTest(f"Template file {self.template_path} not found")
        
        self.music_dir.mkdir(parents=True, exist_ok=True)
        created_files = []
        
        for entry in entries:
            # Use artist as album artist for directory structure
            album_artist = entry['artist']
            album = entry['album']
            
            # Sanitize directory names
            safe_artist = TestHelpers.sanitize_path_component(album_artist)
            safe_album = TestHelpers.sanitize_path_component(album)
            
            # Create directory structure
            album_dir = self.music_dir / safe_artist / safe_album
            album_dir.mkdir(parents=True, exist_ok=True)
            
            # Create filename with sanitized components
            safe_title = TestHelpers.sanitize_filename(entry['title'])
            safe_artist_name = TestHelpers.sanitize_filename(entry['artist'])
            safe_album_name = TestHelpers.sanitize_filename(entry['album'])
            
            filename = f"{entry['disc']} - {entry['track']} - {safe_title} - {safe_artist_name} - {safe_album_name}.{entry['ext']}"
            file_path = album_dir / filename
            
            # Copy template file
            shutil.copy2(self.template_path, file_path)
            
            # Modify metadata - use ORIGINAL unsanitized values
            audio = FLAC(str(file_path))
            audio['title'] = entry['title']  # Original with /
            audio['artist'] = entry['artist']
            audio['album'] = entry['album']
            audio['albumartist'] = album_artist
            audio['tracknumber'] = entry['track']
            audio['discnumber'] = entry['disc']
            audio.save()
            
            created_files.append(str(file_path))
        
        return created_files
    
    def _create_m3u8_playlist(self, entries, output_path):
        """Create M3U8 playlist from entries"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for entry in entries:
                # Create path in playlist format
                safe_artist = TestHelpers.sanitize_path_component(entry['artist'])
                safe_album = TestHelpers.sanitize_path_component(entry['album'])
                safe_title = TestHelpers.sanitize_filename(entry['title'])
                safe_artist_name = TestHelpers.sanitize_filename(entry['artist'])
                safe_album_name = TestHelpers.sanitize_filename(entry['album'])
                
                filename = f"{entry['disc']} - {entry['track']} - {safe_title} - {safe_artist_name} - {safe_album_name}.{entry['ext']}"
                path = f"..\\{safe_artist}\\{safe_album}\\{filename}"
                
                f.write(f"#EXTINF:{entry['duration']},{entry['artist']} - {entry['title']}\n")
                f.write(f"{path}\n")
    
    def _create_text_playlist(self, entries, output_path):
        """Create simple text playlist (Artist - Title format)"""
        with open(output_path, 'w', encoding='utf-8') as f:
            for entry in entries:
                f.write(f"{entry['artist']} - {entry['title']}\n")
    
    def test_mock_library_creation(self):
        """Test that mock library is created correctly"""
        created_files = self._create_mock_library(self.test_entries)
        
        self.assertEqual(len(created_files), 10, "Should create 10 files")
        
        # Verify all files exist
        for file_path in created_files:
            self.assertTrue(Path(file_path).exists(), f"File should exist: {file_path}")
        
        # Verify metadata for a file with special characters
        die_arzte_file = [f for f in created_files if 'Die Ärzte' in f][0]
        audio = FLAC(die_arzte_file)
        
        # Metadata should have original / character
        self.assertEqual(audio.get('title', [''])[0], '1/2 Lovesong')
        self.assertEqual(audio.get('artist', [''])[0], 'Die Ärzte')
        
        # Filename should have sanitized ∕ character
        self.assertIn('1∕2 Lovesong', die_arzte_file)
    
    def test_m3u8_playlist_matching(self):
        """Test M3U8 playlist format matching"""
        # Create mock library
        created_files = self._create_mock_library(self.test_entries)
        
        # Create test playlist
        self._create_m3u8_playlist(self.test_entries, self.test_playlist)
        
        # Run matcher
        matcher = pm.PlaylistMatcher(
            str(self.test_playlist),
            str(self.music_dir),
            str(self.output_playlist),
            str(self.output_log),
            path_format='artist_album'
        )
        matcher.process_playlist()
        
        # Verify output
        self.assertTrue(self.output_playlist.exists(), "Output playlist should exist")
        self.assertTrue(self.output_log.exists(), "Output log should exist")
        
        # Check match rate
        with open(self.output_playlist, 'r', encoding='utf-8') as f:
            content = f.read()
            match_count = content.count('#EXTINF')
        
        self.assertEqual(match_count, 10, "Should match all 10 songs")
        
        # Verify no unmatched songs
        with open(self.output_log, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        self.assertIn('Matched: 10', log_content)
        self.assertIn('Unmatched: 0', log_content)
    
    def test_text_playlist_matching(self):
        """Test simple text playlist format matching"""
        # Create mock library
        created_files = self._create_mock_library(self.test_entries)
        
        # Create text playlist
        self._create_text_playlist(self.test_entries, self.test_text_playlist)
        
        # Run matcher
        matcher = pm.PlaylistMatcher(
            str(self.test_text_playlist),
            str(self.music_dir),
            str(self.text_output_playlist),
            str(self.text_output_log),
            path_format='artist_album'
        )
        matcher.process_playlist()
        
        # Verify output
        self.assertTrue(self.text_output_playlist.exists(), "Output playlist should exist")
        
        # Check that text format was converted to M3U8
        with open(self.text_output_playlist, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('#EXTM3U', content, "Should have M3U8 header")
        self.assertEqual(content.count('#EXTINF'), 10, "Should have 10 entries")
        
        # Verify all songs matched
        with open(self.text_output_log, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        self.assertIn('Matched: 10', log_content)
        self.assertIn('Unmatched: 0', log_content)
    
    def test_special_character_handling(self):
        """Test that special characters are handled correctly"""
        # Create mock library with just the Die Ärzte song
        die_arzte_entry = [e for e in self.test_entries if e['artist'] == 'Die Ärzte'][0]
        created_files = self._create_mock_library([die_arzte_entry])
        
        # Verify file was created with sanitized filename
        self.assertEqual(len(created_files), 1)
        file_path = Path(created_files[0])
        
        # Filename should have ∕ (Unicode division slash)
        self.assertIn('1∕2 Lovesong', file_path.name)
        
        # Metadata should have original /
        audio = FLAC(str(file_path))
        self.assertEqual(audio.get('title', [''])[0], '1/2 Lovesong')
    
    def test_playlist_format_detection(self):
        """Test automatic playlist format detection"""
        # Create mock library
        self._create_mock_library(self.test_entries)
        
        # Create M3U8 playlist
        self._create_m3u8_playlist(self.test_entries, self.test_playlist)
        
        # Create text playlist
        self._create_text_playlist(self.test_entries, self.test_text_playlist)
        
        # Read and detect formats
        with open(self.test_playlist, 'r', encoding='utf-8-sig') as f:
            m3u8_lines = [line.rstrip('\n\r') for line in f.readlines()]
        
        with open(self.test_text_playlist, 'r', encoding='utf-8-sig') as f:
            text_lines = [line.rstrip('\n\r') for line in f.readlines()]
        
        matcher = pm.PlaylistMatcher(
            str(self.test_playlist),
            str(self.music_dir),
            str(self.output_playlist),
            str(self.output_log)
        )
        
        m3u8_format = matcher.detect_playlist_format(m3u8_lines)
        text_format = matcher.detect_playlist_format(text_lines)
        
        self.assertEqual(m3u8_format, 'm3u8', "Should detect M3U8 format")
        self.assertEqual(text_format, 'text', "Should detect text format")
    
    def test_advanced_matching_strategies(self):
        """Test advanced matching strategies (album artist, fuzzy, similarity)"""
        # Create mock library
        created_files = self._create_mock_library(self.test_entries)
        
        # Create cache
        cache = pm.MusicLibraryCache(str(self.music_dir))
        cache.build_cache()
        
        # Test Strategy 3: Album artist matching
        # Search with artist that matches albumartist
        matched_path, reason = cache.find_match(
            "1/2 Lovesong",
            "Die Ärzte",  # This is the albumartist
            "13"
        )
        self.assertIsNotNone(matched_path, "Should match using album artist")
        
        # Test Strategy 4: Fuzzy matching (substring)
        # Search with partial artist name
        matched_path, reason = cache.find_match(
            "(Can't Get My) Head Around You",
            "Offspring",  # Partial artist name
            ""
        )
        self.assertIsNotNone(matched_path, "Should match with substring artist")
        
        # Test unmatched song with detailed failure reason
        matched_path, reason = cache.find_match(
            "Nonexistent Song",
            "Nonexistent Artist",
            "Nonexistent Album"
        )
        self.assertIsNone(matched_path, "Should not match nonexistent song")
        self.assertIsNotNone(reason, "Should provide failure reason")
        self.assertIn("No files found with title", reason)
    
    def test_build_cache_from_paths(self):
        """Test building cache from file path list"""
        # Create mock library
        created_files = self._create_mock_library(self.test_entries)
        
        # Build cache from file paths
        cache = pm.MusicLibraryCache(str(self.music_dir))
        cache.build_cache(file_paths=created_files)
        
        # Verify cache was built
        self.assertEqual(len(cache.cache), 10, "Should cache all 10 files")
        self.assertEqual(len(cache.album_artist_index), 10, "Should index 10 album artists")
        
        # Test with non-existent file in list
        fake_files = created_files + ['/nonexistent/file.flac']
        cache2 = pm.MusicLibraryCache(str(self.music_dir))
        cache2.build_cache(file_paths=fake_files)
        
        # Should still cache the valid files
        self.assertEqual(len(cache2.cache), 10, "Should cache only valid files")
    
    def test_error_handling(self):
        """Test error handling for invalid inputs"""
        # Test with non-existent music directory
        cache = pm.MusicLibraryCache('/nonexistent/directory')
        cache.build_cache()
        
        self.assertEqual(len(cache.cache), 0, "Should have empty cache for invalid directory")
        
        # Test with invalid playlist file
        matcher = pm.PlaylistMatcher(
            '/nonexistent/playlist.m3u8',
            str(self.music_dir),
            str(self.output_playlist),
            str(self.output_log)
        )
        
        lines = matcher.read_old_playlist()
        self.assertEqual(len(lines), 0, "Should return empty list for nonexistent playlist")
    
    def test_invalid_parser_format(self):
        """Test parser with invalid format name"""
        with self.assertRaises(ValueError):
            pm.PlaylistPathParser('invalid_format')
    
    def test_empty_playlist(self):
        """Test handling of empty playlist"""
        # Create empty playlist
        empty_playlist = self.test_dir / 'empty.m3u8'
        with open(empty_playlist, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
        
        # Create mock library
        self._create_mock_library(self.test_entries)
        
        # Run matcher
        matcher = pm.PlaylistMatcher(
            str(empty_playlist),
            str(self.music_dir),
            str(self.output_playlist),
            str(self.output_log)
        )
        matcher.process_playlist()
        
        # Verify output
        with open(self.output_playlist, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertEqual(content.count('#EXTINF'), 0, "Should have no entries")
        
        # Cleanup
        empty_playlist.unlink()
    
    def test_malformed_playlist_entries(self):
        """Test handling of malformed playlist entries"""
        # Create playlist with malformed entries
        malformed_playlist = self.test_dir / 'malformed.m3u8'
        with open(malformed_playlist, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            f.write('#EXTINF:invalid,No Separator\n')  # Missing ' - '
            f.write('path/to/file.flac\n')
            f.write('#EXTINF:123,Artist - Title\n')
            f.write('valid/path.flac\n')
        
        # Create mock library
        self._create_mock_library(self.test_entries)
        
        # Run matcher
        matcher = pm.PlaylistMatcher(
            str(malformed_playlist),
            str(self.music_dir),
            str(self.output_playlist),
            str(self.output_log)
        )
        
        lines = matcher.read_old_playlist()
        matched, unmatched = matcher.find_matches(lines)
        
        # Should handle malformed entries gracefully
        self.assertIsInstance(matched, list)
        self.assertIsInstance(unmatched, list)
        
        # Cleanup
        malformed_playlist.unlink()

    def test_cache_save_and_load(self):
        """Test cache saving and loading functionality"""
        import tempfile
        import json
        
        # Create test library first
        self._create_mock_library(self.test_entries)
        
        # Create temporary cache file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            cache_file = f.name
        
        try:
            # Build cache and save
            cache = MusicLibraryCache(str(self.music_dir), cache_file)
            cache.build_cache()
            
            # Verify cache has data
            self.assertGreater(len(cache.cache), 0)
            original_count = len(cache.cache)
            
            # Save cache
            success = cache.save_cache()
            self.assertTrue(success)
            self.assertTrue(Path(cache_file).exists())
            
            # Verify cache file structure
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            self.assertIn('metadata', cache_data)
            self.assertIn('cache', cache_data)
            self.assertIn('album_artist_index', cache_data)
            self.assertEqual(cache_data['metadata']['version'], MusicLibraryCache.CACHE_VERSION)
            self.assertEqual(cache_data['metadata']['file_count'], original_count)
            
            # Create new cache instance and load
            cache2 = MusicLibraryCache(str(self.music_dir), cache_file)
            loaded = cache2.load_cache()
            
            self.assertTrue(loaded)
            self.assertEqual(len(cache2.cache), original_count)
            self.assertEqual(len(cache2.album_artist_index), len(cache.album_artist_index))
            
        finally:
            # Cleanup
            if Path(cache_file).exists():
                Path(cache_file).unlink()
    
    def test_cache_version_mismatch(self):
        """Test cache version validation"""
        import tempfile
        import json
        
        # Create test library first
        self._create_mock_library(self.test_entries)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            cache_file = f.name
        
        try:
            # Create cache with wrong version
            cache_data = {
                'metadata': {
                    'version': '0.0.0',  # Wrong version
                    'music_dir': str(self.music_dir),
                    'file_count': 0
                },
                'cache': {},
                'album_artist_index': {}
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            
            # Try to load cache
            cache = MusicLibraryCache(str(self.music_dir), cache_file)
            loaded = cache.load_cache()
            
            # Should fail due to version mismatch
            self.assertFalse(loaded)
            
        finally:
            if Path(cache_file).exists():
                Path(cache_file).unlink()
    
    def test_cache_directory_change_detection(self):
        """Test cache invalidation when directory changes"""
        import tempfile
        import json
        import time
        
        # Create test library first
        self._create_mock_library(self.test_entries)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            cache_file = f.name
        
        try:
            # Build and save cache
            cache = MusicLibraryCache(str(self.music_dir), cache_file)
            cache.build_cache()
            cache.save_cache()
            
            # Load cache - should succeed
            cache2 = MusicLibraryCache(str(self.music_dir), cache_file)
            loaded = cache2.load_cache()
            self.assertTrue(loaded)
            
            # Modify a file in the test library
            test_file = list(self.music_dir.rglob('*.flac'))[0]
            time.sleep(0.1)  # Ensure different mtime
            test_file.touch()
            
            # Try to load cache again - should fail due to directory hash change
            cache3 = MusicLibraryCache(str(self.music_dir), cache_file)
            loaded = cache3.load_cache()
            self.assertFalse(loaded)
            
        finally:
            if Path(cache_file).exists():
                Path(cache_file).unlink()
    
    def test_cache_clear(self):
        """Test cache file deletion"""
        import tempfile
        
        # Create test library first
        self._create_mock_library(self.test_entries)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            cache_file = f.name
        
        try:
            # Create and save cache
            cache = MusicLibraryCache(str(self.music_dir), cache_file)
            cache.build_cache()
            cache.save_cache()
            
            self.assertTrue(Path(cache_file).exists())
            
            # Clear cache
            success = cache.clear_cache()
            self.assertTrue(success)
            self.assertFalse(Path(cache_file).exists())
            
            # Try to clear again - should return False
            success = cache.clear_cache()
            self.assertFalse(success)
            
        finally:
            if Path(cache_file).exists():
                Path(cache_file).unlink()
    
    def test_playlist_matcher_with_cache(self):
        """Test PlaylistMatcher with cache enabled"""
        import tempfile
        
        # Create test library and playlist first
        self._create_mock_library(self.test_entries)
        self._create_m3u8_playlist(self.test_entries, self.test_playlist)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            cache_file = f.name
        
        try:
            # First run - build cache
            matcher1 = PlaylistMatcher(
                str(self.test_playlist),
                str(self.music_dir),
                str(self.output_playlist),
                str(self.output_log),
                cache_file=cache_file,
                use_cache=True
            )
            matcher1.process_playlist()
            
            # Verify cache file was created
            self.assertTrue(Path(cache_file).exists())
            
            # Second run - should load from cache
            matcher2 = PlaylistMatcher(
                str(self.test_playlist),
                str(self.music_dir),
                str(self.output_playlist),
                str(self.output_log),
                cache_file=cache_file,
                use_cache=True
            )
            matcher2.process_playlist()
            
            # Both should produce same results
            self.assertTrue(self.output_playlist.exists())
            
        finally:
            if Path(cache_file).exists():
                Path(cache_file).unlink()
    
    def test_playlist_matcher_force_rebuild(self):
        """Test PlaylistMatcher with force rebuild"""
        import tempfile
        
        # Create test library and playlist first
        self._create_mock_library(self.test_entries)
        self._create_m3u8_playlist(self.test_entries, self.test_playlist)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            cache_file = f.name
        
        try:
            # Create initial cache
            matcher1 = PlaylistMatcher(
                str(self.test_playlist),
                str(self.music_dir),
                str(self.output_playlist),
                str(self.output_log),
                cache_file=cache_file,
                use_cache=True
            )
            matcher1.process_playlist()
            
            # Force rebuild
            matcher2 = PlaylistMatcher(
                str(self.test_playlist),
                str(self.music_dir),
                str(self.output_playlist),
                str(self.output_log),
                cache_file=cache_file,
                use_cache=True,
                force_rebuild=True
            )
            matcher2.process_playlist()
            
            # Should still work
            self.assertTrue(self.output_playlist.exists())
            
        finally:
            if Path(cache_file).exists():
                Path(cache_file).unlink()
    
    def test_cache_incremental_update(self):
        """Test incremental cache update with new/modified/deleted files"""
        import tempfile
        import time
        
        # Create test library first
        self._create_mock_library(self.test_entries)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            cache_file = f.name
        
        try:
            # Build initial cache
            cache = MusicLibraryCache(str(self.music_dir), cache_file)
            cache.build_cache()
            cache.save_cache()
            
            initial_count = len(cache.cache)
            self.assertEqual(initial_count, 10)
            
            # Simulate changes:
            # 1. Add a new file
            new_entry = {
                'artist': 'Test Artist',
                'title': 'New Song',
                'album': 'New Album',
                'disc': '1',
                'track': '999',
                'ext': 'flac',
                'duration': '180'
            }
            new_files = self._create_mock_library([new_entry])
            
            # 2. Modify an existing file (touch to change mtime)
            existing_file = list(self.music_dir.rglob('*.flac'))[0]
            time.sleep(0.1)  # Ensure different mtime
            existing_file.touch()
            
            # 3. Delete a file
            file_to_delete = list(self.music_dir.rglob('*.flac'))[1]
            deleted_path = str(file_to_delete)
            file_to_delete.unlink()
            
            # Perform incremental update
            cache2 = MusicLibraryCache(str(self.music_dir), cache_file)
            success = cache2.update_cache()
            
            self.assertTrue(success)
            
            # Verify results
            # Should have: initial (10) + new (1) - deleted (1) = 10 files
            self.assertEqual(len(cache2.cache), 10)
            
            # Verify new file was added
            new_file_path = new_files[0]
            self.assertIn(new_file_path, cache2.cache)
            self.assertEqual(cache2.cache[new_file_path]['title'], 'New Song')
            
            # Verify deleted file was removed
            self.assertNotIn(deleted_path, cache2.cache)
            
            # Verify cache was saved
            cache3 = MusicLibraryCache(str(self.music_dir), cache_file)
            loaded = cache3.load_cache()
            self.assertTrue(loaded)
            self.assertEqual(len(cache3.cache), 10)
            
        finally:
            if Path(cache_file).exists():
                Path(cache_file).unlink()

if __name__ == '__main__':
    unittest.main()

