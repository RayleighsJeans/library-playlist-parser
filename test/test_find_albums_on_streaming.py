#!/usr/bin/env python3
"""
Unit tests for find_albums_on_streaming.py

Tests the streaming service search functionality including:
- Spotify search (API and web fallback)
- Deezer search
- Apple Music, Tidal, Qobuz, Amazon Music search URLs
- Music library scanning
- Integration with Wikipedia best-selling albums dataset
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import os
import sys
from pathlib import Path
import tempfile
import shutil

# Add parent directory to path to import the module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from find_albums_on_streaming import StreamingSearcher, MusicLibraryScanner


class TestStreamingSearcher(unittest.TestCase):
    """Test StreamingSearcher class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create searcher without credentials (will use web fallback)
        self.searcher = StreamingSearcher()

    def test_init_without_credentials(self):
        """Test initialization without Spotify credentials."""
        searcher = StreamingSearcher()
        self.assertIsNone(searcher.spotify_token)
        self.assertIsNotNone(searcher.session)

    def test_init_with_credentials(self):
        """Test initialization with Spotify credentials."""
        with patch('find_albums_on_streaming.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'access_token': 'test_token'}
            mock_post.return_value = mock_response

            searcher = StreamingSearcher(
                spotify_client_id='test_id',
                spotify_client_secret='test_secret'
            )
            self.assertEqual(searcher.spotify_token, 'test_token')

    def test_search_spotify_web(self):
        """Test Spotify web search URL generation."""
        url = self.searcher.search_spotify_web('Michael Jackson', 'Thriller')
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('open.spotify.com/search', url)
            self.assertIn('Michael', url)
            self.assertIn('Thriller', url)

    @patch('find_albums_on_streaming.requests.Session.get')
    def test_search_spotify_api_success(self, mock_get):
        """Test Spotify API search with successful response."""
        # Set up mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'albums': {
                'items': [
                    {
                        'external_urls': {
                            'spotify': 'https://open.spotify.com/album/test123'
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        # Set token to enable API search
        self.searcher.spotify_token = 'test_token'

        url = self.searcher.search_spotify('Michael Jackson', 'Thriller')
        self.assertEqual(url, 'https://open.spotify.com/album/test123')

    @patch('find_albums_on_streaming.requests.Session.get')
    def test_search_spotify_api_no_results(self, mock_get):
        """Test Spotify API search with no results falls back to web search."""
        # Set up mock response with no results
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'albums': {'items': []}}
        mock_get.return_value = mock_response

        # Set token to enable API search
        self.searcher.spotify_token = 'test_token'

        url = self.searcher.search_spotify('Unknown Artist', 'Unknown Album')
        # Should fall back to web search
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('open.spotify.com/search', url)

    @patch('find_albums_on_streaming.requests.Session.get')
    def test_search_deezer_success(self, mock_get):
        """Test Deezer API search with successful response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {'id': '12345'}
            ]
        }
        mock_get.return_value = mock_response

        url = self.searcher.search_deezer('AC/DC', 'Back in Black')
        self.assertEqual(url, 'https://www.deezer.com/album/12345')

    @patch('find_albums_on_streaming.requests.Session.get')
    def test_search_deezer_no_results(self, mock_get):
        """Test Deezer search with no results falls back to web search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}
        mock_get.return_value = mock_response

        url = self.searcher.search_deezer('Unknown Artist', 'Unknown Album')
        # Should fall back to web search
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('deezer.com/search', url)

    def test_search_apple_music(self):
        """Test Apple Music search URL generation."""
        url = self.searcher.search_apple_music('Pink Floyd', 'The Dark Side of the Moon')
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('music.apple.com', url)
            self.assertIn('search', url)

    def test_search_tidal(self):
        """Test Tidal search URL generation."""
        url = self.searcher.search_tidal('Eagles', 'Hotel California')
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('listen.tidal.com/search', url)

    def test_search_qobuz(self):
        """Test Qobuz search URL generation."""
        url = self.searcher.search_qobuz('Fleetwood Mac', 'Rumours')
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('qobuz.com', url)
            self.assertIn('search', url)

    def test_search_amazon_music(self):
        """Test Amazon Music search URL generation."""
        url = self.searcher.search_amazon_music('Led Zeppelin', 'Led Zeppelin IV')
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('music.amazon.com/search', url)

    def test_search_all_services(self):
        """Test searching all services returns expected structure."""
        results = self.searcher.search_all_services('Test Artist', 'Test Album')

        # Check all expected services are present
        expected_services = ['deezer', 'spotify', 'apple_music', 'tidal', 'qobuz', 'amazon_music']
        for service in expected_services:
            self.assertIn(service, results)

        # Check that at least some services return URLs
        urls_found = sum(1 for url in results.values() if url is not None)
        self.assertGreater(urls_found, 0)

    def test_special_characters_in_search(self):
        """Test that special characters in artist/album names are handled."""
        # Test with special characters
        url = self.searcher.search_spotify_web('AC/DC', 'Back in Black')
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('open.spotify.com', url)

        url = self.searcher.search_apple_music('Guns N\' Roses', 'Appetite for Destruction')
        self.assertIsNotNone(url)
        if url:  # Type guard for type checker
            self.assertIn('music.apple.com', url)


class TestMusicLibraryScanner(unittest.TestCase):
    """Test MusicLibraryScanner class."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.test_dir = tempfile.mkdtemp()
        self.scanner = MusicLibraryScanner(self.test_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init(self):
        """Test scanner initialization."""
        self.assertEqual(self.scanner.music_dir, Path(self.test_dir))
        self.assertEqual(len(self.scanner.albums), 0)

    def test_scan_empty_directory(self):
        """Test scanning an empty directory."""
        albums = self.scanner.scan_library()
        self.assertEqual(len(albums), 0)

    def test_scan_nonexistent_directory(self):
        """Test scanning a non-existent directory."""
        scanner = MusicLibraryScanner('/nonexistent/path')
        albums = scanner.scan_library()
        self.assertEqual(len(albums), 0)

    def test_scan_library_with_albums(self):
        """Test scanning a library with album structure."""
        # Create test structure: album_artist/album/files
        artist_dir = Path(self.test_dir) / 'Michael Jackson'
        album_dir = artist_dir / 'Thriller'
        album_dir.mkdir(parents=True)

        # Create a test audio file
        (album_dir / '01 - 01 - Wanna Be Startin Somethin - Michael Jackson - Thriller.flac').touch()

        albums = self.scanner.scan_library()
        self.assertEqual(len(albums), 1)
        self.assertIn(('Michael Jackson', 'Thriller'), albums)

    def test_scan_library_multiple_albums(self):
        """Test scanning a library with multiple albums."""
        # Create multiple artists and albums
        test_albums = [
            ('Michael Jackson', 'Thriller'),
            ('Michael Jackson', 'Bad'),
            ('Eagles', 'Hotel California'),
            ('Pink Floyd', 'The Dark Side of the Moon')
        ]

        for artist, album in test_albums:
            artist_dir = Path(self.test_dir) / artist
            album_dir = artist_dir / album
            album_dir.mkdir(parents=True)
            (album_dir / '01 - 01 - Track - Artist - Album.mp3').touch()

        albums = self.scanner.scan_library()
        self.assertEqual(len(albums), 4)
        for album_tuple in test_albums:
            self.assertIn(album_tuple, albums)

    def test_scan_library_ignores_non_audio_files(self):
        """Test that scanner ignores directories without audio files."""
        # Create directory with only non-audio files
        artist_dir = Path(self.test_dir) / 'Test Artist'
        album_dir = artist_dir / 'Test Album'
        album_dir.mkdir(parents=True)
        (album_dir / 'cover.jpg').touch()
        (album_dir / 'info.txt').touch()

        albums = self.scanner.scan_library()
        self.assertEqual(len(albums), 0)

    def test_scan_library_various_audio_formats(self):
        """Test that scanner recognizes various audio formats."""
        audio_formats = ['.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wma', '.aac', '.wav']

        for i, ext in enumerate(audio_formats):
            artist_dir = Path(self.test_dir) / f'Artist{i}'
            album_dir = artist_dir / f'Album{i}'
            album_dir.mkdir(parents=True)
            (album_dir / f'track{ext}').touch()

        albums = self.scanner.scan_library()
        self.assertEqual(len(albums), len(audio_formats))


class TestWikipediaBestsellingAlbums(unittest.TestCase):
    """Component tests using Wikipedia best-selling albums dataset."""

    @classmethod
    def setUpClass(cls):
        """Load Wikipedia best-selling albums dataset."""
        dataset_path = Path(__file__).parent / 'wikipedia_bestselling_albums.json'
        with open(dataset_path, 'r') as f:
            cls.albums = json.load(f)

    def setUp(self):
        """Set up test fixtures."""
        self.searcher = StreamingSearcher()

    def test_wikipedia_dataset_loaded(self):
        """Test that Wikipedia dataset is loaded correctly."""
        self.assertGreater(len(self.albums), 0)
        # Check first album is Thriller
        self.assertEqual(self.albums[0]['artist'], 'Michael Jackson')
        self.assertEqual(self.albums[0]['album'], 'Thriller')

    def test_search_thriller(self):
        """Test searching for Michael Jackson's Thriller."""
        results = self.searcher.search_all_services('Michael Jackson', 'Thriller')

        # Should have results for multiple services
        self.assertIsNotNone(results['spotify'])
        self.assertIsNotNone(results['apple_music'])
        self.assertIsNotNone(results['tidal'])

    def test_search_back_in_black(self):
        """Test searching for AC/DC's Back in Black."""
        results = self.searcher.search_all_services('AC/DC', 'Back in Black')

        # Should handle special characters in artist name
        self.assertIsNotNone(results['spotify'])
        self.assertIsNotNone(results['deezer'])

    def test_search_all_wikipedia_albums(self):
        """Component test: Search for all Wikipedia best-selling albums."""
        success_count = 0
        total_count = len(self.albums)

        for album_data in self.albums:
            artist = album_data['artist']
            album = album_data['album']

            results = self.searcher.search_all_services(artist, album)

            # Count as success if at least one service returns a URL
            if any(url is not None for url in results.values()):
                success_count += 1

        # Should successfully find most albums (at least 80%)
        success_rate = success_count / total_count
        self.assertGreater(success_rate, 0.8,
                          f"Only found {success_count}/{total_count} albums ({success_rate:.1%})")

    def test_wikipedia_albums_url_format(self):
        """Test that URLs returned for Wikipedia albums are properly formatted."""
        # Test a few albums
        test_albums = self.albums[:3]

        for album_data in test_albums:
            results = self.searcher.search_all_services(
                album_data['artist'],
                album_data['album']
            )

            for service, url in results.items():
                if url:
                    # Check URL is properly formatted
                    self.assertTrue(url.startswith('http'),
                                   f"{service} URL doesn't start with http: {url}")
                    self.assertNotIn(' ', url,
                                    f"{service} URL contains spaces: {url}")


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete workflow."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_scan_and_search_workflow(self):
        """Test complete workflow: scan library and search for albums."""
        # Create test library with a few albums
        test_albums = [
            ('Michael Jackson', 'Thriller'),
            ('Pink Floyd', 'The Dark Side of the Moon')
        ]

        for artist, album in test_albums:
            artist_dir = Path(self.test_dir) / artist
            album_dir = artist_dir / album
            album_dir.mkdir(parents=True)
            (album_dir / '01 - 01 - Track - Artist - Album.flac').touch()

        # Scan library
        scanner = MusicLibraryScanner(self.test_dir)
        albums = scanner.scan_library()
        self.assertEqual(len(albums), 2)

        # Search for albums
        searcher = StreamingSearcher()
        results = []

        for album_artist, album in albums:
            service_results = searcher.search_all_services(album_artist, album)
            if any(url is not None for url in service_results.values()):
                results.append({
                    'album_artist': album_artist,
                    'album': album,
                    'services': service_results
                })

        # Should find both albums
        self.assertEqual(len(results), 2)


if __name__ == '__main__':
    unittest.main()
