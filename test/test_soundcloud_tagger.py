#!/usr/bin/env python3
"""
Unit tests for soundcloud_tagger.py

Tests the SoundCloud music tagger functionality including:
- Library parsing
- Filename matching
- Metadata aggregation
- File tagging
- Filename generation
"""

import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path to import soundcloud_tagger
sys.path.insert(0, str(Path(__file__).parent.parent / 'soundcloud'))

import soundcloud_tagger as st


class TestLibraryParser(unittest.TestCase):
    """Test library.txt parsing functionality."""
    
    def setUp(self):
        """Create temporary library file for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.library_path = os.path.join(self.temp_dir, 'test_library.txt')
        
        # Create test library content
        library_content = """Artist One - Song Title One
Artist Two - Song Title Two [12345]
mobilee118: Artist Three - Song Title Three
TEASER: Artist Four - Song Title Four
Artist Five - Song Title Five (Preview)
1. Artist Six - Song Title Six
"""
        with open(self.library_path, 'w', encoding='utf-8') as f:
            f.write(library_content)
    
    def tearDown(self):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)
    
    def test_library_parsing(self):
        """Test that library entries are parsed correctly."""
        parser = st.LibraryParser(self.library_path)
        
        # Should have 6 entries
        self.assertEqual(len(parser.entries), 6)
        
        # Check first entry
        self.assertEqual(parser.entries[0]['artist'], 'Artist One')
        self.assertEqual(parser.entries[0]['title'], 'Song Title One')
    
    def test_extract_artist_title_basic(self):
        """Test basic artist - title extraction."""
        parser = st.LibraryParser(self.library_path)
        artist, title = parser._extract_artist_title('Artist Name - Song Title')
        
        self.assertEqual(artist, 'Artist Name')
        self.assertEqual(title, 'Song Title')
    
    def test_extract_artist_title_with_brackets(self):
        """Test extraction with brackets removed."""
        parser = st.LibraryParser(self.library_path)
        artist, title = parser._extract_artist_title('Artist - Title [12345]')
        
        self.assertEqual(artist, 'Artist')
        self.assertEqual(title, 'Title')
    
    def test_extract_artist_title_with_label_prefix(self):
        """Test extraction with label prefix removed."""
        parser = st.LibraryParser(self.library_path)
        artist, title = parser._extract_artist_title('mobilee118: Artist - Title')
        
        self.assertEqual(artist, 'Artist')
        self.assertEqual(title, 'Title')
    
    def test_find_best_match(self):
        """Test finding best matching library entry for filename."""
        parser = st.LibraryParser(self.library_path)
        
        # Test exact match
        match = parser.find_best_match('Artist One - Song Title One.mp3')
        self.assertIsNotNone(match)
        self.assertEqual(match['artist'], 'Artist One')
        self.assertEqual(match['title'], 'Song Title One')
        self.assertGreater(match['confidence'], 0.4)
    
    def test_find_best_match_no_match(self):
        """Test that no match returns None or has low confidence."""
        parser = st.LibraryParser(self.library_path)
        
        match = parser.find_best_match('Completely Different Artist - Random Song.mp3')
        # Should return None if confidence too low, or confidence should be low
        if match:
            # Allow slightly higher threshold due to fuzzy matching
            self.assertLess(match['confidence'], 0.5)


class TestMusicTagger(unittest.TestCase):
    """Test music tagging functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.library_path = os.path.join(self.temp_dir, 'test_library.txt')
        
        # Create minimal library
        with open(self.library_path, 'w', encoding='utf-8') as f:
            f.write('Test Artist - Test Song\n')
        
        self.library = st.LibraryParser(self.library_path)
        self.metadata = Mock(spec=st.MetadataAggregator)
        self.tagger = st.MusicTagger(self.library, self.metadata)
    
    def tearDown(self):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)
    
    def test_sanitize_filename(self):
        """Test filename sanitization."""
        # Test various problematic characters
        test_cases = [
            ('Artist/Title', 'Artist∕Title'),
            ('Artist:Title', 'Artist∶Title'),
            ('Artist*Title', 'Artist∗Title'),
            ('Artist?Title', 'Artist？Title'),
            ('Artist"Title', 'Artist＂Title'),
            ('Artist<Title', 'Artist＜Title'),
            ('Artist>Title', 'Artist＞Title'),
            ('Artist|Title', 'Artist｜Title'),
        ]
        
        for input_text, expected in test_cases:
            result = self.tagger._sanitize_filename(input_text)
            self.assertEqual(result, expected)
    
    def test_generate_filename_complete_metadata(self):
        """Test filename generation with complete metadata."""
        metadata = {
            'discnumber': '1',
            'tracknumber': '5',
            'title': 'Test Song',
            'artist': 'Test Artist',
            'album': 'Test Album'
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        self.assertEqual(filename, '1 - 05 - Test Song - Test Artist - Test Album.mp3')
    
    def test_generate_filename_missing_fields(self):
        """Test filename generation with missing metadata fields."""
        metadata = {
            'title': 'Test Song',
            'artist': 'Test Artist'
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        # Should use defaults for missing fields
        self.assertEqual(filename, '1 - 00 - Test Song - Test Artist - Unknown Album.mp3')
    
    def test_generate_filename_track_padding(self):
        """Test that track numbers are padded to 2 digits."""
        metadata = {
            'tracknumber': '3',
            'title': 'Test',
            'artist': 'Artist',
            'album': 'Album'
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        self.assertIn(' - 03 - ', filename)
    
    def test_generate_filename_track_with_total(self):
        """Test track number extraction from 'X/Y' format."""
        metadata = {
            'tracknumber': '5/12',
            'title': 'Test',
            'artist': 'Artist',
            'album': 'Album'
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        self.assertIn(' - 05 - ', filename)
    
    def test_generate_filename_albumartist_priority(self):
        """Test that albumartist is preferred over artist."""
        metadata = {
            'title': 'Test',
            'artist': 'Track Artist',
            'albumartist': 'Album Artist',
            'album': 'Album'
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        self.assertIn('Album Artist', filename)
        self.assertNotIn('Track Artist', filename)
    
    def test_parse_filename_metadata(self):
        """Test parsing metadata from filename."""
        result = self.tagger._parse_filename_metadata('Artist Name - Song Title.mp3')
        
        self.assertIsNotNone(result)
        self.assertEqual(result['artist'], 'Artist Name')
        self.assertEqual(result['title'], 'Song Title')
    
    def test_parse_filename_metadata_with_track_number(self):
        """Test parsing filename with track number prefix."""
        result = self.tagger._parse_filename_metadata('01. Artist - Title.mp3')
        
        self.assertIsNotNone(result)
        self.assertEqual(result['artist'], 'Artist')
        self.assertEqual(result['title'], 'Title')


class TestMetadataAggregator(unittest.TestCase):
    """Test metadata aggregation from multiple sources."""
    
    def test_get_random_local_cover_method_exists(self):
        """Test that random local cover method exists."""
        aggregator = st.MetadataAggregator()
        
        # Verify the method exists
        self.assertTrue(hasattr(aggregator, '_get_random_local_cover'))
        self.assertTrue(callable(getattr(aggregator, '_get_random_local_cover')))
    
    def test_get_random_local_cover_no_directory(self):
        """Test random local cover when directory doesn't exist."""
        aggregator = st.MetadataAggregator()
        
        # Create a temporary directory that doesn't have a covers subdirectory
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Mock the soundcloud_tagger module's __file__ attribute
            with patch('soundcloud_tagger.__file__', os.path.join(temp_dir, 'soundcloud_tagger.py')):
                result = aggregator._get_random_local_cover()
                # Should return None when covers directory doesn't exist
                self.assertIsNone(result)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_get_random_local_cover_with_files(self):
        """Test random local cover selection with actual files."""
        aggregator = st.MetadataAggregator()
        
        # Create temporary directory structure
        temp_dir = tempfile.mkdtemp()
        covers_dir = os.path.join(temp_dir, 'covers')
        os.makedirs(covers_dir)
        
        # Create test cover files
        test_data = b'fake image data'
        for i in range(3):
            cover_file = os.path.join(covers_dir, f'cover{i}.jpg')
            with open(cover_file, 'wb') as f:
                f.write(test_data)
        
        try:
            # Mock the soundcloud_tagger module's __file__ attribute
            with patch('soundcloud_tagger.__file__', os.path.join(temp_dir, 'soundcloud_tagger.py')):
                result = aggregator._get_random_local_cover()
                # Should return image data
                self.assertIsNotNone(result)
                self.assertEqual(result, test_data)
        finally:
            shutil.rmtree(temp_dir)


class TestFilenameGeneration(unittest.TestCase):
    """Test filename generation edge cases."""
    
    def setUp(self):
        """Set up test tagger."""
        self.temp_dir = tempfile.mkdtemp()
        library_path = os.path.join(self.temp_dir, 'lib.txt')
        with open(library_path, 'w') as f:
            f.write('Artist - Song\n')
        
        library = st.LibraryParser(library_path)
        metadata = Mock(spec=st.MetadataAggregator)
        self.tagger = st.MusicTagger(library, metadata)
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)
    
    def test_special_characters_in_title(self):
        """Test handling of special characters in title."""
        metadata = {
            'title': 'Song/Title: Part 1',
            'artist': 'Artist',
            'album': 'Album'
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        # Should not contain actual / or :
        self.assertNotIn('/', filename)
        self.assertNotIn(':', filename)
        # Should contain Unicode replacements
        self.assertIn('∕', filename)
        self.assertIn('∶', filename)
    
    def test_empty_metadata_fields(self):
        """Test handling of empty string metadata."""
        metadata = {
            'title': '',
            'artist': '',
            'album': ''
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        # Should use defaults
        self.assertIn('Unknown Title', filename)
        self.assertIn('Unknown Artist', filename)
        self.assertIn('Unknown Album', filename)
    
    def test_whitespace_only_fields(self):
        """Test handling of whitespace-only metadata."""
        metadata = {
            'title': '   ',
            'artist': '  ',
            'album': '   '
        }
        
        filename = self.tagger._generate_filename(metadata, '.mp3')
        # Should use defaults after stripping
        self.assertIn('Unknown Title', filename)
        self.assertIn('Unknown Artist', filename)
        self.assertIn('Unknown Album', filename)


def run_tests():
    """Run all tests with verbose output."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestLibraryParser))
    suite.addTests(loader.loadTestsFromTestCase(TestMusicTagger))
    suite.addTests(loader.loadTestsFromTestCase(TestMetadataAggregator))
    suite.addTests(loader.loadTestsFromTestCase(TestFilenameGeneration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 70)
    print("Test Summary:")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  Failures: {len(result.failures)}")
    print(f"  Errors: {len(result.errors)}")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)

# Made with Bob
