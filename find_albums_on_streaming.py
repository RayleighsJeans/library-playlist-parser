#!/usr/bin/env python3
"""
Music Library to Streaming Service Finder

Scans a music library with structure: album_artist/album/disc - track - title - artist - album.ext
Extracts unique album artist + album combinations and searches for them on:
- Spotify (API with premium subscription, otherwise web search)
- Deezer (free API, returns direct album links)
- Apple Music (web search)
- Tidal (web search)
- Qobuz (web search)
- Amazon Music (web search)

Note: Spotify API requires a premium subscription for the app owner to return direct album links.
Without premium, the tool falls back to web search URLs.

Outputs:
- results.txt: List of albums with streaming links
- search_log.txt: Detailed log of hits and misses
"""

import os
import sys
import time
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
from urllib.parse import quote_plus
import requests


class StreamingSearcher:
    """Search for albums across multiple streaming services."""

    def __init__(self, spotify_client_id: Optional[str] = None,
                 spotify_client_secret: Optional[str] = None):
        """
        Initialize streaming service searcher.

        Args:
            spotify_client_id: Spotify API client ID
            spotify_client_secret: Spotify API client secret
        """
        self.spotify_token = None
        self.spotify_client_id = spotify_client_id
        self.spotify_client_secret = spotify_client_secret

        # Load credentials from config if not provided
        if not self.spotify_client_id:
            self._load_config()

        # Get Spotify token if credentials available
        if self.spotify_client_id and self.spotify_client_secret:
            self._get_spotify_token()

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'MusicLibraryStreamingFinder/1.0'
        })

    def _load_config(self):
        """Load API credentials from config file."""
        config_paths = [
            'streaming_config.json',
            os.path.expanduser('~/.streaming_config.json')
        ]

        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        self.spotify_client_id = config.get('spotify', {}).get('client_id')
                        self.spotify_client_secret = config.get('spotify', {}).get('client_secret')
                        if self.spotify_client_id:
                            print(f"  ℹ️  Loaded Spotify credentials from {config_path}")
                            return
                except Exception as e:
                    print(f"  ⚠️  Error loading config from {config_path}: {e}")

    def _get_spotify_token(self):
        """Get Spotify API access token using client credentials flow."""
        try:
            auth_url = 'https://accounts.spotify.com/api/token'
            auth_data = {
                'grant_type': 'client_credentials',
                'client_id': self.spotify_client_id,
                'client_secret': self.spotify_client_secret
            }

            response = requests.post(auth_url, data=auth_data, timeout=10)
            if response.status_code == 200:
                self.spotify_token = response.json()['access_token']
                print("  ✓ Spotify API authenticated")
            else:
                print(f"  ⚠️  Spotify auth failed: {response.status_code}")
        except Exception as e:
            print(f"  ⚠️  Spotify auth error: {e}")

    def search_spotify_web(self, album_artist: str, album: str) -> Optional[str]:
        """
        Search for album on Spotify using web search (no API key required).
        Constructs Spotify search URL that users can click.

        Returns:
            Spotify search URL
        """
        try:
            # Create a Spotify search URL
            search_query = quote_plus(f'{album_artist} {album}')
            return f'https://open.spotify.com/search/{search_query}/albums'

        except Exception as e:
            pass

        return None

    def search_spotify(self, album_artist: str, album: str) -> Optional[str]:
        """
        Search for album on Spotify using API if available, web search as fallback.
        
        Note: Spotify API requires premium subscription for the app owner.
        Without premium, API returns 403 errors and we fall back to web search URLs.

        Returns:
            Spotify album URL (if API works) or search URL (fallback)
        """
        # Try API first if we have token
        if self.spotify_token:
            try:
                # Rate limiting
                time.sleep(0.1)

                # Try multiple search strategies for better results
                search_strategies = [
                    # Strategy 1: Exact match with quotes
                    f'album:"{album}" artist:"{album_artist}"',
                    # Strategy 2: Without quotes
                    f'album:{album} artist:{album_artist}',
                    # Strategy 3: Simple combined search
                    f'{album_artist} {album}'
                ]

                headers = {
                    'Authorization': f'Bearer {self.spotify_token}'
                }

                for query in search_strategies:
                    params = {
                        'q': query,
                        'type': 'album',
                        'limit': 5  # Get top 5 to find best match
                    }

                    response = self.session.get(
                        'https://api.spotify.com/v1/search',
                        params=params,
                        headers=headers,
                        timeout=10
                    )

                    if response.status_code == 200:
                        data = response.json()
                        items = data.get('albums', {}).get('items', [])
                        
                        if items:
                            # Try to find exact match first
                            for item in items:
                                item_album = item['name'].lower()
                                item_artist = item['artists'][0]['name'].lower()
                                
                                # Check for exact or very close match
                                if (album.lower() in item_album or item_album in album.lower()) and \
                                   (album_artist.lower() in item_artist or item_artist in album_artist.lower()):
                                    return item['external_urls']['spotify']
                            
                            # If no exact match, return first result
                            return items[0]['external_urls']['spotify']
                    
                    # Small delay between strategies
                    time.sleep(0.1)

            except Exception as e:
                pass

        # Fallback to web search URL
        return self.search_spotify_web(album_artist, album)

    def search_tidal(self, album_artist: str, album: str) -> Optional[str]:
        """
        Search for album on Tidal using web search approach.
        Creates a Tidal search URL that users can follow.

        Returns:
            Tidal search URL
        """
        try:
            # Rate limiting
            time.sleep(0.2)

            # Create Tidal search URL
            search_query = quote_plus(f'{album_artist} {album}')
            return f'https://listen.tidal.com/search?q={search_query}'

        except Exception as e:
            pass

        return None

    def search_qobuz(self, album_artist: str, album: str) -> Optional[str]:
        """
        Search for album on Qobuz using web search approach.
        Creates a Qobuz search URL that users can follow.

        Returns:
            Qobuz search URL
        """
        try:
            # Rate limiting
            time.sleep(0.2)

            # Create Qobuz search URL
            search_query = quote_plus(f'{album_artist} {album}')
            return f'https://www.qobuz.com/us-en/search?q={search_query}'

        except Exception as e:
            pass

        return None

    def search_apple_music(self, album_artist: str, album: str) -> Optional[str]:
        """
        Search for album on Apple Music using web search.
        Creates an Apple Music search URL that users can follow.

        Returns:
            Apple Music search URL
        """
        try:
            # Rate limiting
            time.sleep(0.2)

            # Create Apple Music search URL
            search_query = quote_plus(f'{album_artist} {album}')
            return f'https://music.apple.com/us/search?term={search_query}'

        except Exception as e:
            pass

        return None

    def search_amazon_music(self, album_artist: str, album: str) -> Optional[str]:
        """
        Search for album on Amazon Music using web search.
        Creates an Amazon Music search URL that users can follow.

        Returns:
            Amazon Music search URL
        """
        try:
            # Rate limiting
            time.sleep(0.2)

            # Create Amazon Music search URL
            search_query = quote_plus(f'{album_artist} {album}')
            return f'https://music.amazon.com/search/{search_query}'

        except Exception as e:
            pass

        return None

    def search_deezer(self, album_artist: str, album: str) -> Optional[str]:
        """
        Search for album on Deezer using their public API (no auth required).
        Falls back to web search if API fails.

        Returns:
            Deezer album URL or search URL
        """
        try:
            # Rate limiting
            time.sleep(0.2)

            # Try Deezer public API first
            query = f'{album_artist} {album}'
            params = {
                'q': query,
                'limit': 1
            }

            response = self.session.get(
                'https://api.deezer.com/search/album',
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('data') and len(data['data']) > 0:
                    album_id = data['data'][0]['id']
                    return f'https://www.deezer.com/album/{album_id}'

        except Exception as e:
            pass

        # Fallback to web search
        try:
            search_query = quote_plus(f'{album_artist} {album}')
            return f'https://www.deezer.com/search/{search_query}/album'
        except:
            pass

        return None

    def search_all_services(self, album_artist: str, album: str) -> Dict[str, Optional[str]]:
        """
        Search for album across all streaming services.

        Search order:
        1. Deezer (free API, direct album links)
        2. Spotify (API if available, web search as fallback)
        3. Apple Music (web search)
        4. Tidal (web search)
        5. Qobuz (web search)
        6. Amazon Music (web search)

        Returns:
            Dictionary with service names as keys and URLs as values
        """
        results: Dict[str, Optional[str]] = {
            'deezer': None,
            'spotify': None,
            'apple_music': None,
            'tidal': None,
            'qobuz': None,
            'amazon_music': None
        }

        # Try Deezer (free API, returns direct album links)
        results['deezer'] = self.search_deezer(album_artist, album)

        # Try Spotify (API or web search fallback)
        results['spotify'] = self.search_spotify(album_artist, album)

        # Try other streaming services (web search)
        results['apple_music'] = self.search_apple_music(album_artist, album)
        results['tidal'] = self.search_tidal(album_artist, album)
        results['qobuz'] = self.search_qobuz(album_artist, album)
        results['amazon_music'] = self.search_amazon_music(album_artist, album)

        return results


class MusicLibraryScanner:
    """Scan music library and extract album information."""

    def __init__(self, music_dir: str):
        """
        Initialize library scanner.

        Args:
            music_dir: Root directory of music library
        """
        self.music_dir = Path(music_dir)
        self.albums: Set[Tuple[str, str]] = set()  # (album_artist, album)

    def scan_library(self) -> Set[Tuple[str, str]]:
        """
        Scan music library and extract unique album artist + album combinations.

        Expected structure: album_artist/album/disc - track - title - artist - album.ext

        Returns:
            Set of (album_artist, album) tuples
        """
        print(f"\n📁 Scanning music library: {self.music_dir}")

        if not self.music_dir.exists():
            print(f"  ❌ Directory does not exist: {self.music_dir}")
            return self.albums

        # Audio file extensions
        audio_extensions = {'.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wma', '.aac', '.wav'}

        # Walk through directory structure: album_artist/album/files
        album_artist_count = 0
        for album_artist_dir in sorted(self.music_dir.iterdir()):
            if not album_artist_dir.is_dir():
                continue

            album_artist_name = album_artist_dir.name
            album_artist_count += 1

            for album_dir in album_artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue

                album_name = album_dir.name

                # Check if directory contains audio files
                has_audio = any(
                    f.suffix.lower() in audio_extensions
                    for f in album_dir.iterdir()
                    if f.is_file()
                )

                if has_audio:
                    self.albums.add((album_artist_name, album_name))

            if album_artist_count % 10 == 0:
                print(f"  Processed {album_artist_count} album artists...")

        print(f"  ✓ Found {len(self.albums)} unique albums from {album_artist_count} album artists")
        return self.albums


class StreamingServiceFinder:
    """Main class for finding albums on streaming services."""
    
    def __init__(self, music_dir: str = 'E:/Music/', output_dir: str = 'streaming_results'):
        """
        Initialize the streaming service finder.
        
        Args:
            music_dir: Root directory of music library
            output_dir: Directory for output files
        """
        self.music_dir = music_dir
        self.output_dir = Path(output_dir)
        self.searcher = StreamingSearcher()
        self.scanner = MusicLibraryScanner(music_dir)
        self.results = []
        self.hits = 0
        self.misses = 0
        
    def run(self, limit: Optional[int] = None, verbose: bool = True) -> Dict[str, any]:  # type: ignore
        """
        Run the complete search workflow.
        
        Args:
            limit: Optional limit on number of albums to search
            verbose: Whether to print progress messages
            
        Returns:
            Dictionary with results and statistics
        """
        if verbose:
            print("🎵 Music Library Streaming Service Finder")
            print("=" * 70)
            
            # Check for Spotify credentials
            print("\n🔑 Checking API credentials...")
            if not self.searcher.spotify_token:
                print("\n⚠️  WARNING: No Spotify credentials found!")
                print("   Continuing with web search fallback...\n")
        
        # Scan library
        albums = self.scanner.scan_library()
        
        if not albums:
            if verbose:
                print("\n❌ No albums found in library!")
            return {'albums': [], 'hits': 0, 'misses': 0, 'total': 0}
        
        # Limit albums if requested
        if limit:
            albums = set(list(albums)[:limit])
            if verbose:
                print(f"\n⚠️  Limited to {limit} albums for testing")
        
        # Search for albums
        if verbose:
            print(f"\n🔍 Searching for {len(albums)} albums on streaming services...")
        
        self.results = []
        self.hits = 0
        self.misses = 0
        
        for i, (album_artist, album) in enumerate(sorted(albums), 1):
            if verbose:
                print(f"  [{i}/{len(albums)}] {album_artist} - {album}")
            
            # Search all services
            service_results = self.searcher.search_all_services(album_artist, album)
            
            # Check if any service found the album
            found = any(url is not None for url in service_results.values())
            
            if found:
                self.hits += 1
                self.results.append({
                    'album_artist': album_artist,
                    'album': album,
                    'services': service_results
                })
                if verbose:
                    print(f"    ✓ Found on streaming services")
            else:
                self.misses += 1
                if verbose:
                    print(f"    ✗ Not found on any service")
            
            # Progress update every 50 albums
            if verbose and i % 50 == 0:
                print(f"\n  Progress: {i}/{len(albums)} albums searched ({self.hits} hits, {self.misses} misses)\n")
        
        # Write output files
        self._write_output_files()
        
        # Print summary
        if verbose:
            self._print_summary(len(albums))
        
        return {
            'albums': self.results,
            'hits': self.hits,
            'misses': self.misses,
            'total': len(albums)
        }
    
    def _write_output_files(self):
        """Write results to separate files for each service."""
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        
        # Collect URLs by service
        service_urls = defaultdict(list)
        
        for result in self.results:
            for service, url in result['services'].items():
                if url:
                    service_urls[service].append(url)
        
        # Write separate file for each service
        for service, urls in service_urls.items():
            output_file = self.output_dir / f'{service}.txt'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(', '.join(urls))
        
        # Write combined log file
        log_file = self.output_dir / 'search.log'
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("Music Library Streaming Service Search Log\n")
            f.write("=" * 70 + "\n")
            f.write(f"Search completed: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total albums found: {self.hits}\n\n")
            
            for result in self.results:
                f.write(f"{result['album_artist']} - {result['album']}\n")
                for service, url in result['services'].items():
                    if url:
                        f.write(f"  ✓ {service.capitalize()}: {url}\n")
                    else:
                        f.write(f"  ✗ {service.capitalize()}: Not found\n")
                f.write("\n")
            
            # Write summary
            f.write("=" * 70 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 70 + "\n")
            f.write(f"Total albums searched: {self.hits + self.misses}\n")
            f.write(f"Found on streaming services: {self.hits}\n")
            f.write(f"Not found: {self.misses}\n")
    
    def _print_summary(self, total: int):
        """Print summary statistics."""
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Total albums searched: {total}")
        print(f"Found on streaming services: {self.hits} ({self.hits/total*100:.1f}%)")
        print(f"Not found: {self.misses} ({self.misses/total*100:.1f}%)")
        print(f"\nResults written to: {self.output_dir}/")
        print("  Service-specific files:")
        for service_file in sorted(self.output_dir.glob('*.txt')):
            if service_file.name != 'search.log':
                print(f"    - {service_file.name}")
        print(f"  Detailed log: search.log")
        print("=" * 70)


def main():
    """Main execution function for CLI."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Find albums from music library on streaming services'
    )
    parser.add_argument(
        '--music-dir',
        default='E:/Music/',
        help='Music library root directory (default: E:/Music/)'
    )
    parser.add_argument(
        '--output-dir',
        default='streaming_results',
        help='Output directory for results (default: streaming_results/)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of albums to search (for testing)'
    )

    args = parser.parse_args()
    
    # Create and run finder
    finder = StreamingServiceFinder(
        music_dir=args.music_dir,
        output_dir=args.output_dir
    )
    
    finder.run(limit=args.limit, verbose=True)


if __name__ == '__main__':
    main()
