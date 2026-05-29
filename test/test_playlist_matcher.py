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


if __name__ == '__main__':
    unittest.main()

# Made with Bob
