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

from find_albums_on_streaming import StreamingSearcher, MusicLibraryScanner, StreamingServiceFinder


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

    def test_is_direct_link_spotify(self):
        """Test URL type detection for Spotify."""
        # Direct link
        self.assertTrue(self.searcher.is_direct_link(
            'https://open.spotify.com/album/2ANVost0y2y52ema1E9xAZ', 'spotify'))
        # Search link
        self.assertFalse(self.searcher.is_direct_link(
            'https://open.spotify.com/search/Michael+Jackson+Thriller/albums', 'spotify'))

    def test_is_direct_link_deezer(self):
        """Test URL type detection for Deezer."""
        # Direct link
        self.assertTrue(self.searcher.is_direct_link(
            'https://www.deezer.com/album/72819', 'deezer'))
        # Search link
        self.assertFalse(self.searcher.is_direct_link(
            'https://www.deezer.com/search/Michael+Jackson+Thriller/album', 'deezer'))

    def test_is_direct_link_apple_music(self):
        """Test URL type detection for Apple Music."""
        # Direct link
        self.assertTrue(self.searcher.is_direct_link(
            'https://music.apple.com/us/album/thriller/1234567', 'apple_music'))
        # Search link
        self.assertFalse(self.searcher.is_direct_link(
            'https://music.apple.com/us/search?term=Michael+Jackson+Thriller', 'apple_music'))

    def test_is_direct_link_other_services(self):
        """Test URL type detection for other services (all search URLs)."""
        # Tidal, Qobuz, Amazon Music only return search URLs
        self.assertFalse(self.searcher.is_direct_link(
            'https://listen.tidal.com/search?q=test', 'tidal'))
        self.assertFalse(self.searcher.is_direct_link(
            'https://www.qobuz.com/us-en/search?q=test', 'qobuz'))
        self.assertFalse(self.searcher.is_direct_link(
            'https://music.amazon.com/search/test', 'amazon_music'))

    def test_is_service_available_no_timeout(self):
        """Test service availability when no timeout is set."""
        self.assertTrue(self.searcher.is_service_available('spotify'))
        self.assertTrue(self.searcher.is_service_available('deezer'))

    def test_is_service_available_with_timeout(self):
        """Test service availability when timeout is active."""
        from datetime import datetime, timedelta
        
        # Set timeout for 1 second in the future
        self.searcher.service_timeouts['spotify'] = datetime.now() + timedelta(seconds=1)
        self.assertFalse(self.searcher.is_service_available('spotify'))
        
        # Set timeout in the past (expired)
        self.searcher.service_timeouts['deezer'] = datetime.now() - timedelta(seconds=1)
        self.assertTrue(self.searcher.is_service_available('deezer'))

    def test_set_service_timeout(self):
        """Test setting service timeout."""
        from datetime import datetime
        
        self.searcher.set_service_timeout('spotify')
        self.assertIn('spotify', self.searcher.service_timeouts)
        
        # Check timeout is in the future
        timeout = self.searcher.service_timeouts['spotify']
        self.assertGreater(timeout, datetime.now())

    def test_handle_rate_limit(self):
        """Test rate limit handling."""
        from collections import deque
        
        self.searcher.handle_rate_limit('spotify', 'Test Artist', 'Test Album')
        
        # Check timeout was set
        self.assertIn('spotify', self.searcher.service_timeouts)
        
        # Check item was queued
        self.assertIn('spotify', self.searcher.retry_queues)
        self.assertEqual(len(self.searcher.retry_queues['spotify']), 1)
        
        # Check queued item
        queued_item = self.searcher.retry_queues['spotify'][0]
        self.assertEqual(queued_item, ('Test Artist', 'Test Album'))

    @patch('find_albums_on_streaming.requests.Session.get')
    def test_search_spotify_rate_limit(self, mock_get):
        """Test Spotify search handles rate limiting."""
        # Set up mock response with 429 status
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        # Set token to enable API search
        self.searcher.spotify_token = 'test_token'
        
        url = self.searcher.search_spotify('Test Artist', 'Test Album')
        
        # Should return None when rate limited
        self.assertIsNone(url)
        
        # Check timeout was set
        self.assertIn('spotify', self.searcher.service_timeouts)

    @patch('find_albums_on_streaming.requests.Session.get')
    def test_search_deezer_rate_limit(self, mock_get):
        """Test Deezer search handles rate limiting."""
        # Set up mock response with 429 status
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        url = self.searcher.search_deezer('Test Artist', 'Test Album')
        
        # Should return None when rate limited
        self.assertIsNone(url)
        
        # Check timeout was set
        self.assertIn('deezer', self.searcher.service_timeouts)


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


class TestStreamingServiceFinder(unittest.TestCase):
    """Test StreamingServiceFinder class with caching and incremental saving."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.output_dir = tempfile.mkdtemp()
        
        # Create test library structure
        test_albums = [
            ('Test Artist 1', 'Test Album 1'),
            ('Test Artist 2', 'Test Album 2')
        ]
        
        for artist, album in test_albums:
            artist_dir = Path(self.test_dir) / artist
            album_dir = artist_dir / album
            album_dir.mkdir(parents=True)
            (album_dir / '01 - 01 - Track - Artist - Album.flac').touch()

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def test_init(self):
        """Test StreamingServiceFinder initialization."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        self.assertEqual(finder.music_dir, self.test_dir)
        self.assertEqual(finder.output_dir, Path(self.output_dir))
        self.assertIsNotNone(finder.searcher)
        self.assertIsNotNone(finder.scanner)
        self.assertTrue(finder.cache_dir.exists())

    def test_cache_loading(self):
        """Test cache loading from disk."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        # Initially empty
        self.assertEqual(len(finder.album_cache.get('spotify', set())), 0)
        
        # Create a cache file
        cache_file = finder.cache_dir / 'spotify_albums.json'
        with open(cache_file, 'w') as f:
            json.dump([['Artist', 'Album']], f)
        
        # Reload
        finder._load_caches()
        self.assertEqual(len(finder.album_cache['spotify']), 1)
        self.assertIn(('Artist', 'Album'), finder.album_cache['spotify'])

    def test_save_cache(self):
        """Test saving cache to disk."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        # Save an album to cache
        finder._save_cache('spotify', 'album', ('Test Artist', 'Test Album'))
        
        # Check cache file was created
        cache_file = finder.cache_dir / 'spotify_albums.json'
        self.assertTrue(cache_file.exists())
        
        # Check content
        with open(cache_file, 'r') as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0], ['Test Artist', 'Test Album'])

    def test_is_cached(self):
        """Test cache checking."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        # Not cached initially
        self.assertFalse(finder._is_cached('spotify', 'album', ('Artist', 'Album')))
        
        # Add to cache
        finder._save_cache('spotify', 'album', ('Artist', 'Album'))
        
        # Should be cached now
        self.assertTrue(finder._is_cached('spotify', 'album', ('Artist', 'Album')))

    def test_append_to_output_file_direct_link(self):
        """Test appending direct links to output files."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        # Append a direct link
        direct_url = 'https://www.deezer.com/album/12345'
        finder._append_to_output_file('deezer', 'album', direct_url)
        
        # Check file was created and contains URL
        output_file = finder.output_dir / 'albums' / 'deezer.txt'
        self.assertTrue(output_file.exists())
        
        with open(output_file, 'r') as f:
            content = f.read()
        self.assertIn(direct_url, content)

    def test_append_to_output_file_search_link(self):
        """Test that search links are not written to output files."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        # Try to append a search link
        search_url = 'https://open.spotify.com/search/test/albums'
        finder._append_to_output_file('spotify', 'album', search_url)
        
        # Check file was not created (search links filtered out)
        output_file = finder.output_dir / 'albums' / 'spotify.txt'
        self.assertFalse(output_file.exists())

    @patch('find_albums_on_streaming.StreamingSearcher.search_deezer')
    def test_run_with_caching(self, mock_search):
        """Test that run() uses caching correctly."""
        # Mock search to return a direct link
        mock_search.return_value = 'https://www.deezer.com/album/12345'
        
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        # First run - should call search
        results1 = finder.run(limit=1, verbose=False, search_albums=True, search_artists=False)
        self.assertEqual(mock_search.call_count, 1)
        
        # Second run - should use cache, not call search again
        finder2 = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        results2 = finder2.run(limit=1, verbose=False, search_albums=True, search_artists=False)
        
        # Search should still only have been called once (from first run)
        self.assertEqual(mock_search.call_count, 1)
        
        # Both runs should report finding the album
        self.assertEqual(results1['album_hits'], 1)
        self.assertEqual(results2['album_hits'], 1)

    def test_run_albums_only(self):
        """Test running with albums only."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        results = finder.run(
            limit=1,
            verbose=False,
            search_albums=True,
            search_artists=False
        )
        
        self.assertGreater(results['total_albums'], 0)
        self.assertEqual(results['total_artists'], 0)

    def test_run_artists_only(self):
        """Test running with artists only."""
        finder = StreamingServiceFinder(
            music_dir=self.test_dir,
            output_dir=self.output_dir
        )
        
        results = finder.run(
            limit=1,
            verbose=False,
            search_albums=False,
            search_artists=True
        )
        
        self.assertEqual(results['total_albums'], 0)
        self.assertGreater(results['total_artists'], 0)


if __name__ == '__main__':
    unittest.main()
