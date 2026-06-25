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
from collections import defaultdict, deque
from urllib.parse import quote_plus, urlparse
import requests
from datetime import datetime, timedelta

from music_library import AUDIO_EXTENSIONS, scan_albums_in_dir


class StreamingSearcher:
    """Search for albums across multiple streaming services with rate limit handling."""

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
        
        # Rate limit tracking
        self.service_timeouts: Dict[str, datetime] = {}
        self.retry_queues: Dict[str, deque] = defaultdict(deque)
        self.rate_limit_delays = {
            'spotify': 60,      # 1 minute timeout on rate limit
            'deezer': 60,
            'apple_music': 0,   # No API, just URL generation
            'tidal': 0,
            'qobuz': 0,
            'amazon_music': 0
        }

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
    
    @staticmethod
    def is_direct_link(url: str, service: str) -> bool:
        """
        Determine if a URL is a direct link or a search URL.
        
        Args:
            url: The URL to check
            service: The service name
            
        Returns:
            True if it's a direct link, False if it's a search URL
        """
        if not url:
            return False
        
        # Parse URL
        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parsed.query.lower()
        
        # Service-specific detection
        if service == 'spotify':
            # Direct: /album/ID or /artist/ID
            # Search: /search/... or has 'q=' parameter
            return '/album/' in path or '/artist/' in path
        
        elif service == 'deezer':
            # Direct: /album/ID or /artist/ID
            # Search: /search/...
            return ('/album/' in path or '/artist/' in path) and '/search' not in path
        
        elif service in ['apple_music', 'tidal', 'qobuz', 'amazon_music']:
            # These typically return search URLs
            # Direct links would have specific album/artist IDs in path
            return 'search' not in path and 'q=' not in query and 'term=' not in query
        
        return False
    
    def is_service_available(self, service: str) -> bool:
        """Check if a service is currently available (not timed out)."""
        if service not in self.service_timeouts:
            return True
        
        timeout_until = self.service_timeouts[service]
        if datetime.now() >= timeout_until:
            # Timeout expired, service is available again
            del self.service_timeouts[service]
            return True
        
        return False
    
    def set_service_timeout(self, service: str):
        """Set a timeout for a service after rate limit."""
        delay = self.rate_limit_delays.get(service, 60)
        self.service_timeouts[service] = datetime.now() + timedelta(seconds=delay)
        print(f"  ⚠️  {service.capitalize()} rate limited, timeout for {delay}s")
    
    def handle_rate_limit(self, service: str, artist: str, album: str):
        """Add a request to the retry queue for later."""
        self.retry_queues[service].append((artist, album))
        self.set_service_timeout(service)

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

                    # Check for rate limiting
                    if response.status_code == 429:
                        self.handle_rate_limit('spotify', album_artist, album)
                        return None
                    
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

                print(f"  ⚠️  Spotify API search failed")

            except Exception as e:
                print(f"  ❌  Spotify API search error: {e}")
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

            # Check for rate limiting
            if response.status_code == 429:
                self.handle_rate_limit('deezer', album_artist, album)
                return None

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

        artist_set: Set[str] = set()
        for artist_name, album_name, _ in scan_albums_in_dir(self.music_dir):
            self.albums.add((artist_name, album_name))
            artist_set.add(artist_name)

        print(f"  ✓ Found {len(self.albums)} unique albums from {len(artist_set)} album artists")
        return self.albums


class StreamingServiceFinder:
    """Main class for finding albums and artists on streaming services."""
    
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
        self.album_results = []
        self.artist_results = []
        self.album_hits = 0
        self.album_misses = 0
        self.artist_hits = 0
        self.artist_misses = 0
        
        # Cache for tracking already-fetched items per service
        self.cache_dir = self.output_dir / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.album_cache: Dict[str, Set[Tuple[str, str]]] = {}  # service -> set of (artist, album)
        self.artist_cache: Dict[str, Set[str]] = {}  # service -> set of artists
        self._load_caches()
        
    def _load_caches(self):
        """Load existing caches from disk."""
        services = ['spotify', 'deezer', 'apple_music', 'tidal', 'qobuz', 'amazon_music']
        
        for service in services:
            # Load album cache
            album_cache_file = self.cache_dir / f'{service}_albums.json'
            if album_cache_file.exists():
                try:
                    with open(album_cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.album_cache[service] = set(tuple(item) for item in data)
                except Exception:
                    self.album_cache[service] = set()
            else:
                self.album_cache[service] = set()
            
            # Load artist cache
            artist_cache_file = self.cache_dir / f'{service}_artists.json'
            if artist_cache_file.exists():
                try:
                    with open(artist_cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.artist_cache[service] = set(data)
                except Exception:
                    self.artist_cache[service] = set()
            else:
                self.artist_cache[service] = set()
    
    def _save_cache(self, service: str, item_type: str, item: any):  # type: ignore
        """
        Save a single item to cache immediately after successful fetch.
        
        Args:
            service: Service name
            item_type: 'album' or 'artist'
            item: Tuple of (artist, album) for albums, or artist string for artists
        """
        if item_type == 'album':
            self.album_cache[service].add(item)
            cache_file = self.cache_dir / f'{service}_albums.json'
            data = [list(t) for t in self.album_cache[service]]
        else:  # artist
            self.artist_cache[service].add(item)
            cache_file = self.cache_dir / f'{service}_artists.json'
            data = list(self.artist_cache[service])
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"  ⚠️  Failed to save cache for {service}: {e}")
    
    def _is_cached(self, service: str, item_type: str, item: any) -> bool:  # type: ignore
        """
        Check if an item is already cached for a service.
        
        Args:
            service: Service name
            item_type: 'album' or 'artist'
            item: Tuple of (artist, album) for albums, or artist string for artists
            
        Returns:
            True if item is cached, False otherwise
        """
        if item_type == 'album':
            return item in self.album_cache.get(service, set())
        else:  # artist
            return item in self.artist_cache.get(service, set())
    
    def _append_to_output_file(self, service: str, item_type: str, url: str):
        """
        Append a URL to the appropriate output file immediately.
        
        Args:
            service: Service name
            item_type: 'album' or 'artist'
            url: URL to append
        """
        # Only write direct links, not search URLs
        if not self.searcher.is_direct_link(url, service):
            return
        
        if item_type == 'album':
            output_dir = self.output_dir / 'albums'
        else:
            output_dir = self.output_dir / 'artists'
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f'{service}.txt'
        
        try:
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(url + '\n')
        except Exception as e:
            print(f"  ⚠️  Failed to write to {output_file}: {e}")
    
    def run(self, limit: Optional[int] = None, verbose: bool = True,
            search_albums: bool = True, search_artists: bool = True) -> Dict[str, any]:  # type: ignore
        """
        Run the complete search workflow for albums and/or artists.
        
        Args:
            limit: Optional limit on number of items to search
            verbose: Whether to print progress messages
            search_albums: Whether to search for albums
            search_artists: Whether to search for artists
            
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
            return {'albums': [], 'artists': [], 'album_hits': 0, 'album_misses': 0,
                    'artist_hits': 0, 'artist_misses': 0, 'total_albums': 0, 'total_artists': 0}
        
        # Extract unique artists
        unique_artists = set(album_artist for album_artist, _ in albums)
        
        # Apply limit
        if limit:
            albums = set(list(albums)[:limit])
            unique_artists = set(album_artist for album_artist, _ in albums)
            if verbose:
                print(f"\n⚠️  Limited to {limit} albums for testing")
        
        # Search for albums
        if search_albums:
            if verbose:
                print(f"\n🔍 Searching for {len(albums)} albums on streaming services...")
            
            self.album_results = []
            self.album_hits = 0
            self.album_misses = 0
            
            for i, (album_artist, album) in enumerate(sorted(albums), 1):
                if verbose:
                    print(f"  [{i}/{len(albums)}] {album_artist} - {album}")
                
                # Search all services
                service_results = {}
                item_tuple = (album_artist, album)
                found_any = False  # Track if found in any service (including cached)
                
                for service in ['deezer', 'spotify', 'apple_music', 'tidal', 'qobuz', 'amazon_music']:
                    # Skip if already cached
                    if self._is_cached(service, 'album', item_tuple):
                        if verbose:
                            print(f"    ⚡ {service}: cached")
                        service_results[service] = None  # Don't re-fetch
                        found_any = True  # Mark as found since it was cached
                        continue
                    
                    # Check if service is available (not timed out)
                    if not self.searcher.is_service_available(service):
                        if verbose:
                            print(f"    ⏸️  {service}: timed out, skipping")
                        service_results[service] = None
                        continue
                    
                    # Search this service
                    if service == 'deezer':
                        url = self.searcher.search_deezer(album_artist, album)
                    elif service == 'spotify':
                        url = self.searcher.search_spotify(album_artist, album)
                    elif service == 'apple_music':
                        url = self.searcher.search_apple_music(album_artist, album)
                    elif service == 'tidal':
                        url = self.searcher.search_tidal(album_artist, album)
                    elif service == 'qobuz':
                        url = self.searcher.search_qobuz(album_artist, album)
                    elif service == 'amazon_music':
                        url = self.searcher.search_amazon_music(album_artist, album)
                    else:
                        url = None
                    
                    service_results[service] = url
                    
                    # If found, save to cache and append to output file immediately
                    if url:
                        self._save_cache(service, 'album', item_tuple)
                        self._append_to_output_file(service, 'album', url)
                        found_any = True
                        if verbose:
                            is_direct = self.searcher.is_direct_link(url, service)
                            link_type = "direct" if is_direct else "search"
                            print(f"    ✓ {service}: {link_type} link")
                
                # Check if any service found the album (including cached)
                if found_any:
                    self.album_hits += 1
                    self.album_results.append({
                        'album_artist': album_artist,
                        'album': album,
                        'services': service_results
                    })
                else:
                    self.album_misses += 1
                    if verbose:
                        print(f"    ✗ Not found on any service")
                
                # Progress update every 50 albums
                if verbose and i % 50 == 0:
                    print(f"\n  Progress: {i}/{len(albums)} albums searched ({self.album_hits} hits, {self.album_misses} misses)\n")
        
        # Search for artists
        if search_artists:
            if verbose:
                print(f"\n🔍 Searching for {len(unique_artists)} artists on streaming services...")
            
            self.artist_results = []
            self.artist_hits = 0
            self.artist_misses = 0
            
            for i, artist in enumerate(sorted(unique_artists), 1):
                if verbose:
                    print(f"  [{i}/{len(unique_artists)}] {artist}")
                
                # Search all services for artist
                service_results = {}
                found_any = False  # Track if found in any service (including cached)
                
                for service in ['deezer', 'spotify', 'apple_music', 'tidal', 'qobuz', 'amazon_music']:
                    # Skip if already cached
                    if self._is_cached(service, 'artist', artist):
                        if verbose:
                            print(f"    ⚡ {service}: cached")
                        service_results[service] = None  # Don't re-fetch
                        found_any = True  # Mark as found since it was cached
                        continue
                    
                    # Check if service is available (not timed out)
                    if not self.searcher.is_service_available(service):
                        if verbose:
                            print(f"    ⏸️  {service}: timed out, skipping")
                        service_results[service] = None
                        continue
                    
                    # Search this service
                    if service == 'deezer':
                        url = self.searcher.search_deezer(artist, '')
                    elif service == 'spotify':
                        url = self.searcher.search_spotify(artist, '')
                    elif service == 'apple_music':
                        url = self.searcher.search_apple_music(artist, '')
                    elif service == 'tidal':
                        url = self.searcher.search_tidal(artist, '')
                    elif service == 'qobuz':
                        url = self.searcher.search_qobuz(artist, '')
                    elif service == 'amazon_music':
                        url = self.searcher.search_amazon_music(artist, '')
                    else:
                        url = None
                    
                    service_results[service] = url
                    
                    # If found, save to cache and append to output file immediately
                    if url:
                        self._save_cache(service, 'artist', artist)
                        self._append_to_output_file(service, 'artist', url)
                        found_any = True
                        if verbose:
                            is_direct = self.searcher.is_direct_link(url, service)
                            link_type = "direct" if is_direct else "search"
                            print(f"    ✓ {service}: {link_type} link")
                
                # Check if any service found the artist (including cached)
                if found_any:
                    self.artist_hits += 1
                    self.artist_results.append({
                        'artist': artist,
                        'services': service_results
                    })
                else:
                    self.artist_misses += 1
                    if verbose:
                        print(f"    ✗ Not found on any service")
                
                # Progress update every 50 artists
                if verbose and i % 50 == 0:
                    print(f"\n  Progress: {i}/{len(unique_artists)} artists searched ({self.artist_hits} hits, {self.artist_misses} misses)\n")
        
        # Write output files
        self._write_output_files(search_albums, search_artists)
        
        # Print summary
        if verbose:
            self._print_summary(len(albums) if search_albums else 0,
                              len(unique_artists) if search_artists else 0,
                              search_albums, search_artists)
        
        return {
            'albums': self.album_results,
            'artists': self.artist_results,
            'album_hits': self.album_hits,
            'album_misses': self.album_misses,
            'artist_hits': self.artist_hits,
            'artist_misses': self.artist_misses,
            'total_albums': len(albums) if search_albums else 0,
            'total_artists': len(unique_artists) if search_artists else 0
        }
    
    def _write_output_files(self, search_albums: bool = True, search_artists: bool = True):
        """Write log files with search results (URLs are written incrementally during search)."""
        # Create output directories
        self.output_dir.mkdir(exist_ok=True)
        
        if search_albums:
            albums_dir = self.output_dir / 'albums'
            albums_dir.mkdir(exist_ok=True)
            
            # Write combined log file for albums
            log_file = albums_dir / 'search.log'
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("Music Library Albums - Streaming Service Search Log\n")
                f.write("=" * 70 + "\n")
                f.write(f"Search completed: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total albums found: {self.album_hits}\n\n")
                
                for result in self.album_results:
                    f.write(f"{result['album_artist']} - {result['album']}\n")
                    for service, url in result['services'].items():
                        if url:
                            is_direct = self.searcher.is_direct_link(url, service)
                            link_type = " (direct)" if is_direct else " (search)"
                            f.write(f"  ✓ {service.capitalize()}: {url}{link_type}\n")
                        else:
                            f.write(f"  ✗ {service.capitalize()}: Not found\n")
                    f.write("\n")
                
                # Write summary
                f.write("=" * 70 + "\n")
                f.write("SUMMARY\n")
                f.write("=" * 70 + "\n")
                f.write(f"Total albums searched: {self.album_hits + self.album_misses}\n")
                f.write(f"Found on streaming services: {self.album_hits}\n")
                f.write(f"Not found: {self.album_misses}\n")
                f.write(f"\nNote: Only direct links are written to service-specific .txt files\n")
        
        if search_artists:
            artists_dir = self.output_dir / 'artists'
            artists_dir.mkdir(exist_ok=True)
            
            # Write combined log file for artists
            log_file = artists_dir / 'search.log'
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("Music Library Artists - Streaming Service Search Log\n")
                f.write("=" * 70 + "\n")
                f.write(f"Search completed: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total artists found: {self.artist_hits}\n\n")
                
                for result in self.artist_results:
                    f.write(f"{result['artist']}\n")
                    for service, url in result['services'].items():
                        if url:
                            is_direct = self.searcher.is_direct_link(url, service)
                            link_type = " (direct)" if is_direct else " (search)"
                            f.write(f"  ✓ {service.capitalize()}: {url}{link_type}\n")
                        else:
                            f.write(f"  ✗ {service.capitalize()}: Not found\n")
                    f.write("\n")
                
                # Write summary
                f.write("=" * 70 + "\n")
                f.write("SUMMARY\n")
                f.write("=" * 70 + "\n")
                f.write(f"Total artists searched: {self.artist_hits + self.artist_misses}\n")
                f.write(f"Found on streaming services: {self.artist_hits}\n")
                f.write(f"Not found: {self.artist_misses}\n")
                f.write(f"\nNote: Only direct links are written to service-specific .txt files\n")
    
    def _print_summary(self, total_albums: int, total_artists: int,
                      search_albums: bool, search_artists: bool):
        """Print summary statistics."""
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        
        if search_albums:
            print(f"\nAlbums:")
            print(f"  Total searched: {total_albums}")
            print(f"  Found: {self.album_hits} ({self.album_hits/total_albums*100:.1f}%)" if total_albums > 0 else "  Found: 0")
            print(f"  Not found: {self.album_misses}")
        
        if search_artists:
            print(f"\nArtists:")
            print(f"  Total searched: {total_artists}")
            print(f"  Found: {self.artist_hits} ({self.artist_hits/total_artists*100:.1f}%)" if total_artists > 0 else "  Found: 0")
            print(f"  Not found: {self.artist_misses}")
        
        print(f"\nResults written to: {self.output_dir}/")
        
        if search_albums:
            albums_dir = self.output_dir / 'albums'
            print("  Albums:")
            for service_file in sorted(albums_dir.glob('*.txt')):
                if service_file.name != 'search.log':
                    print(f"    - albums/{service_file.name}")
            print(f"    - albums/search.log")
        
        if search_artists:
            artists_dir = self.output_dir / 'artists'
            print("  Artists:")
            for service_file in sorted(artists_dir.glob('*.txt')):
                if service_file.name != 'search.log':
                    print(f"    - artists/{service_file.name}")
            print(f"    - artists/search.log")
        
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
    parser.add_argument(
        '--albums-only',
        action='store_true',
        help='Search only for albums (skip artists)'
    )
    parser.add_argument(
        '--artists-only',
        action='store_true',
        help='Search only for artists (skip albums)'
    )

    args = parser.parse_args()
    
    # Determine what to search
    search_albums = not args.artists_only
    search_artists = not args.albums_only
    
    # Create and run finder
    finder = StreamingServiceFinder(
        music_dir=args.music_dir,
        output_dir=args.output_dir
    )
    
    finder.run(limit=args.limit, verbose=True,
              search_albums=search_albums, search_artists=search_artists)


if __name__ == '__main__':
    main()
