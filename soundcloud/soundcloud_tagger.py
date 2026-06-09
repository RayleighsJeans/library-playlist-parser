#!/usr/bin/env python3
"""
SoundCloud Music Tagger
Automatically tags music files using library.txt reference and online databases.
"""

import os
import re
import shutil
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher
import requests
from mutagen.mp4 import MP4, MP4Cover
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TDRC, APIC
import time

class LibraryParser:
    """Parse library.txt to extract artist and title information."""

    def __init__(self, library_path: str):
        self.library_path = library_path
        self.entries = []
        self._parse_library()

    def _parse_library(self):
        """Parse library.txt and extract artist/title pairs."""
        with open(self.library_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Parse various formats in library.txt
                artist, title = self._extract_artist_title(line)
                if artist and title:
                    self.entries.append({
                        'artist': artist,
                        'title': title,
                        'original': line
                    })

    def _extract_artist_title(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract artist and title from various line formats."""

        # Remove common prefixes/suffixes
        line = re.sub(r'\[.*?\]', '', line)  # Remove [brackets]
        line = re.sub(r'\(.*?[Pp]review.*?\)', '', line)  # Remove (preview)
        line = re.sub(r'\(.*?[Ss]nippet.*?\)', '', line)  # Remove (snippet)
        line = re.sub(r'TEASER:\s*', '', line, flags=re.IGNORECASE)
        line = line.strip()

        # Pattern 1: "Artist - Title"
        if ' - ' in line:
            parts = line.split(' - ', 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                title = parts[1].strip()

                # Clean up artist (remove label prefixes like "mobilee118")
                artist = re.sub(r'^[\w\s]+\d+[:\s]+', '', artist)
                artist = re.sub(r'^\d+\.\s+', '', artist)  # Remove track numbers

                # Clean up title (remove extra info)
                title = re.sub(r'\s*\(.*?[Mm]ix\).*$', '', title)  # Keep remix info
                title = re.sub(r'\s*\[.*?\].*$', '', title)

                return artist.strip(), title.strip()

        return None, None

    def find_best_match(self, filename: str) -> Optional[Dict]:
        """Find best matching library entry for a filename."""
        filename_clean = self._clean_filename(filename)

        best_match = None
        best_score = 0.0

        for entry in self.entries:
            # Create searchable strings
            entry_str = f"{entry['artist']} {entry['title']}".lower()

            # Calculate similarity
            score = SequenceMatcher(None, filename_clean, entry_str).ratio()

            # Boost score if artist name appears in filename
            if entry['artist'].lower() in filename_clean:
                score += 0.2

            # Boost score if title appears in filename
            if entry['title'].lower() in filename_clean:
                score += 0.2

            if score > best_score:
                best_score = score
                best_match = entry

        # Return match if confidence is high enough
        if best_score > 0.4:
            return {**best_match, 'confidence': best_score}

        return None

    def _clean_filename(self, filename: str) -> str:
        """Clean filename for matching."""
        # Remove extension
        name = os.path.splitext(filename)[0]
        # Remove special characters
        name = re.sub(r'[_\-\[\]\(\)]', ' ', name)
        # Remove numbers at start
        name = re.sub(r'^\d+\s*', '', name)
        # Normalize whitespace
        name = ' '.join(name.split())
        return name.lower()


class LastFmAPI:
    """Interface to Last.fm API for metadata retrieval."""

    BASE_URL = "http://ws.audioscrobbler.com/2.0/"
    API_KEY = "b25b959554ed76058ac220b7b2e0a026"  # Public API key

    def __init__(self):
        self.session = requests.Session()

    def search_track(self, artist: str, title: str) -> Optional[Dict]:
        """Search for a track by artist and title."""
        try:
            time.sleep(0.3)  # Rate limiting

            params = {
                'method': 'track.getInfo',
                'api_key': self.API_KEY,
                'artist': artist,
                'track': title,
                'format': 'json'
            }

            response = self.session.get(self.BASE_URL, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('track'):
                    return self._parse_track(data['track'])

        except Exception as e:
            print(f"  Last.fm API error: {e}")

        return None

    def _parse_track(self, track: Dict) -> Dict:
        """Parse Last.fm track data."""
        result = {
            'title': track.get('name', ''),
            'artist': '',
            'album': '',
            'date': '',
            'genre': '',
            'artwork_url': ''
        }

        # Extract artist
        if track.get('artist'):
            if isinstance(track['artist'], dict):
                result['artist'] = track['artist'].get('name', '')
            else:
                result['artist'] = str(track['artist'])

        # Extract album and artwork
        if track.get('album'):
            result['album'] = track['album'].get('title', '')
            # Get album artwork from Last.fm
            if track['album'].get('image'):
                images = track['album']['image']
                # Get the largest image
                for img in reversed(images):
                    if img.get('#text'):
                        result['artwork_url'] = img['#text']
                        break

        # Extract genre from tags
        if track.get('toptags') and track['toptags'].get('tag'):
            tags = track['toptags']['tag']
            if isinstance(tags, list):
                genres = [tag['name'] for tag in tags[:3] if 'name' in tag]
                result['genre'] = ', '.join(genres)

        return result

    def get_artwork(self, artwork_url: str) -> Optional[bytes]:
        """Download artwork from URL."""
        try:
            if artwork_url:
                response = self.session.get(artwork_url, timeout=10)
                if response.status_code == 200:
                    return response.content
        except Exception as e:
            print(f"  Last.fm artwork download error: {e}")
        return None


class DiscogsAPI:
    """Interface to Discogs API for metadata retrieval."""

    BASE_URL = "https://api.discogs.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SoundCloudTagger/1.0'
        })

    def search_release(self, artist: str, title: str) -> Optional[Dict]:
        """Search for a release by artist and title."""
        try:
            time.sleep(1.1)  # Rate limiting

            params = {
                'q': f'{artist} {title}',
                'type': 'release',
                'per_page': 1
            }

            response = self.session.get(
                f"{self.BASE_URL}/database/search",
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('results'):
                    return self._parse_release(data['results'][0])

        except Exception as e:
            print(f"  Discogs API error: {e}")

        return None

    def _parse_release(self, release: Dict) -> Dict:
        """Parse Discogs release data."""
        result = {
            'title': release.get('title', ''),
            'artist': '',
            'album': release.get('title', ''),
            'date': str(release.get('year', '')),
            'genre': ''
        }

        # Extract artist - Discogs often has "Artist - Title" format
        title_parts = release.get('title', '').split(' - ', 1)
        if len(title_parts) == 2:
            result['artist'] = title_parts[0]
            result['title'] = title_parts[1]

        # Extract genre
        if release.get('genre'):
            result['genre'] = ', '.join(release['genre'][:3])
        elif release.get('style'):
            result['genre'] = ', '.join(release['style'][:3])

        return result


class MusicBrainzAPI:
    """Interface to MusicBrainz API for metadata retrieval."""

    BASE_URL = "https://musicbrainz.org/ws/2"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SoundCloudTagger/1.0 (https://github.com/user/soundcloud-tagger)'
        })

    def search_recording(self, artist: str, title: str) -> Optional[Dict]:
        """Search for a recording by artist and title."""
        try:
            # Rate limiting
            time.sleep(1.1)  # MusicBrainz requires 1 request per second

            query = f'artist:"{artist}" AND recording:"{title}"'
            params = {
                'query': query,
                'fmt': 'json',
                'limit': 1
            }

            response = self.session.get(
                f"{self.BASE_URL}/recording",
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('recordings'):
                    recording = data['recordings'][0]
                    return self._parse_recording(recording)

        except Exception as e:
            print(f"  MusicBrainz API error: {e}")

        return None

    def _parse_recording(self, recording: Dict) -> Dict:
        """Parse MusicBrainz recording data."""
        result = {
            'title': recording.get('title', ''),
            'artist': '',
            'album': '',
            'date': '',
            'genre': ''
        }

        # Extract artist
        if recording.get('artist-credit'):
            artists = [ac['name'] for ac in recording['artist-credit'] if 'name' in ac]
            result['artist'] = ', '.join(artists)

        # Extract album and date from releases
        if recording.get('releases'):
            release = recording['releases'][0]
            result['album'] = release.get('title', '')
            result['date'] = release.get('date', '')

        # Extract genre from tags
        if recording.get('tags'):
            genres = [tag['name'] for tag in recording['tags'][:3]]
            result['genre'] = ', '.join(genres)

        return result

    def get_cover_art(self, artist: str, album: str) -> Optional[bytes]:
        """Get cover art from Cover Art Archive."""
        if not album:
            return None

        try:
            time.sleep(1.1)

            # Search for release
            query = f'artist:"{artist}" AND release:"{album}"'
            params = {
                'query': query,
                'fmt': 'json',
                'limit': 1
            }

            response = self.session.get(
                f"{self.BASE_URL}/release",
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('releases'):
                    release_id = data['releases'][0]['id']

                    # Get cover art
                    cover_url = f"https://coverartarchive.org/release/{release_id}/front-250"
                    cover_response = self.session.get(cover_url, timeout=10)

                    if cover_response.status_code == 200:
                        return cover_response.content

        except Exception as e:
            print(f"Cover art error: {e}")

        return None


class SoundCloudAPI:
    """Interface to SoundCloud API for artwork."""

    def __init__(self, client_id: Optional[str] = None, oauth_token: Optional[str] = None):
        self.session = requests.Session()
        self.client_id = client_id
        self.oauth_token = oauth_token

        # Load from config file if not provided
        if not self.client_id:
            self._load_config()

    def _load_config(self):
        """Load SoundCloud credentials from config file."""
        config_paths = [
            'soundcloud_config.json',
            os.path.expanduser('~/.soundcloud_config.json')
        ]

        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        self.client_id = config.get('soundcloud', {}).get('client_id')
                        self.oauth_token = config.get('soundcloud', {}).get('oauth_token')
                        if self.client_id:
                            print(f"  ℹ️  Loaded SoundCloud credentials from {config_path}")
                            return
                except Exception as e:
                    print(f"  ⚠️  Error loading config from {config_path}: {e}")

    def search_track_artwork(self, artist: str, title: str) -> Optional[bytes]:
        """Search SoundCloud API for track artwork."""
        if not self.client_id:
            return None

        try:
            time.sleep(0.5)  # Rate limiting

            # Search using SoundCloud API
            search_query = f"{artist} {title}"
            params = {
                'q': search_query,
                'client_id': self.client_id,
                'limit': 1
            }

            # Add OAuth token if available
            headers = {}
            if self.oauth_token:
                headers['Authorization'] = f'OAuth {self.oauth_token}'

            response = self.session.get(
                'https://api-v2.soundcloud.com/search/tracks',
                params=params,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('collection') and len(data['collection']) > 0:
                    track = data['collection'][0]

                    # Get artwork URL
                    artwork_url = track.get('artwork_url')
                    if not artwork_url and track.get('user'):
                        # Fallback to user avatar
                        artwork_url = track['user'].get('avatar_url')

                    if artwork_url:
                        # Replace size parameter for higher quality (500x500)
                        artwork_url = artwork_url.replace('large', 't500x500')

                        artwork_response = self.session.get(artwork_url, timeout=10)
                        if artwork_response.status_code == 200:
                            return artwork_response.content

        except Exception as e:
            print(f"  SoundCloud API error: {e}")

        return None


class MetadataAggregator:
    """Aggregate metadata from multiple sources with fallback."""

    def __init__(self):
        self.musicbrainz = MusicBrainzAPI()
        self.lastfm = LastFmAPI()
        self.discogs = DiscogsAPI()
        self.soundcloud = SoundCloudAPI()

    def get_metadata(self, artist: str, title: str) -> Optional[Dict]:
        """Try multiple sources in order: MusicBrainz -> Last.fm -> Discogs."""

        # Try MusicBrainz first
        print(f"  🔍 Searching MusicBrainz...")
        metadata = self.musicbrainz.search_recording(artist, title)
        if metadata and metadata.get('album'):
            print(f"  ✓ MusicBrainz: {metadata.get('album', 'N/A')}")
            metadata['source'] = 'MusicBrainz'
            return metadata

        # Try Last.fm second
        print(f"  🔍 Searching Last.fm...")
        metadata = self.lastfm.search_track(artist, title)
        if metadata and (metadata.get('album') or metadata.get('genre')):
            print(f"  ✓ Last.fm: {metadata.get('album', 'N/A')}")
            metadata['source'] = 'Last.fm'
            return metadata

        # Try Discogs third
        print(f"  🔍 Searching Discogs...")
        metadata = self.discogs.search_release(artist, title)
        if metadata and metadata.get('album'):
            print(f"  ✓ Discogs: {metadata.get('album', 'N/A')}")
            metadata['source'] = 'Discogs'
            return metadata

        return None

    def get_cover_art(self, artist: str, album: str, title: str = '', metadata_source: str = '') -> Optional[bytes]:
        """Get cover art with fallback: MusicBrainz -> Last.fm -> SoundCloud -> Random local cover."""
        # Try MusicBrainz Cover Art Archive first
        if album:
            cover_art = self.musicbrainz.get_cover_art(artist, album)
            if cover_art:
                return cover_art

        # Fallback to Last.fm artwork if it was the metadata source
        if metadata_source == 'Last.fm' and title:
            print(f"  🔍 Trying Last.fm for artwork...")
            # Re-fetch track info to get artwork URL
            track_info = self.lastfm.search_track(artist, title)
            if track_info and track_info.get('artwork_url'):
                cover_art = self.lastfm.get_artwork(track_info['artwork_url'])
                if cover_art:
                    print(f"  ✓ Last.fm artwork found")
                    return cover_art

        # Final fallback to SoundCloud if configured
        if title and self.soundcloud.client_id:
            print(f"  🔍 Trying SoundCloud for artwork...")
            cover_art = self.soundcloud.search_track_artwork(artist, title)
            if cover_art:
                print(f"  ✓ SoundCloud artwork found")
                return cover_art

        # Last resort: use random cover from local covers directory
        cover_art = self._get_random_local_cover()
        if cover_art:
            print(f"  🎲 Using random local cover")
            return cover_art

        return None

    def _get_random_local_cover(self) -> Optional[bytes]:
        """Get a random cover image from the soundcloud/covers/ directory."""
        try:
            # Get the covers directory path (relative to script location)
            script_dir = Path(__file__).parent
            covers_dir = script_dir / 'covers'
            
            if not covers_dir.exists():
                return None
            
            # Get all image files
            image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.avif'}
            cover_files = [f for f in covers_dir.iterdir()
                          if f.is_file() and f.suffix.lower() in image_extensions]
            
            if not cover_files:
                return None
            
            # Select random cover
            selected_cover = random.choice(cover_files)
            
            # Read and return the image data
            with open(selected_cover, 'rb') as f:
                return f.read()
                
        except Exception as e:
            print(f"  ⚠️  Error loading random cover: {e}")
            return None


class MusicTagger:
    """Tag music files with metadata."""

    def __init__(self, library_parser: LibraryParser, metadata_aggregator: MetadataAggregator):
        self.library = library_parser
        self.metadata = metadata_aggregator

    def _extract_existing_tags(self, filepath: str) -> Dict:
        """Extract existing tags from file."""
        try:
            ext = os.path.splitext(filepath)[1].lower()

            if ext == '.m4a':
                audio = MP4(filepath)
                if audio.tags:
                    return {
                        'artist': audio.tags.get('©ART', [''])[0],
                        'title': audio.tags.get('©nam', [''])[0],
                        'album': audio.tags.get('©alb', [''])[0],
                        'date': audio.tags.get('©day', [''])[0],
                    }
            elif ext == '.mp3':
                try:
                    audio = MP3(filepath, ID3=ID3)
                    if audio.tags:
                        return {
                            'artist': str(audio.tags.get('TPE1', '')),
                            'title': str(audio.tags.get('TIT2', '')),
                            'album': str(audio.tags.get('TALB', '')),
                            'date': str(audio.tags.get('TDRC', '')),
                        }
                except:
                    pass
        except Exception as e:
            print(f"  ⚠️  Could not read existing tags: {e}")

        return {}

    def _parse_filename_metadata(self, filename: str) -> Optional[Dict]:
        """Parse artist and title from filename as fallback."""
        # Remove extension and common suffixes
        name = os.path.splitext(filename)[0]
        name = re.sub(r'\[.*?\]', '', name)  # Remove [brackets]
        name = re.sub(r'\(.*?\)', '', name)  # Remove (parentheses)
        name = name.strip()

        # Try pattern: "Artist - Title"
        if ' - ' in name:
            parts = name.split(' - ')
            if len(parts) >= 2:
                artist = parts[0].strip()
                title = parts[1].strip()

                # Clean up
                artist = re.sub(r'^\d+[\.\s]+', '', artist)  # Remove track numbers

                if artist and title:
                    return {
                        'artist': artist,
                        'title': title,
                        'album': '',
                        'date': '',
                        'genre': ''
                    }

        return None

    def _sanitize_filename(self, text: str) -> str:
        """
        Sanitize text for use in filenames.
        Replaces problematic characters with safe alternatives.
        """
        if not text:
            return text
        
        # Replace filesystem-unsafe characters
        replacements = {
            '/': '∕',   # Division slash (U+2215)
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
            text = text.replace(old, new)
        
        return text.strip()

    def _generate_filename(self, metadata: Dict, original_ext: str) -> str:
        """
        Generate new filename from metadata.
        Format: discnumber - tracknumber - title - artist - album.ext
        Uses placeholders for missing fields.
        """
        # Extract metadata with defaults
        disc = metadata.get('discnumber', '').strip() or '1'
        track = metadata.get('tracknumber', '').strip() or '00'
        title = metadata.get('title', '').strip() or 'Unknown Title'
        
        # Prefer albumartist, fallback to artist
        artist = metadata.get('albumartist', '').strip()
        if not artist:
            artist = metadata.get('artist', '').strip() or 'Unknown Artist'
        
        album = metadata.get('album', '').strip() or 'Unknown Album'
        
        # Clean track number (remove any non-numeric parts like "1/12")
        if '/' in track:
            track = track.split('/')[0]
        track = ''.join(c for c in track if c.isdigit())
        if not track:
            track = '00'
        
        # Pad track number to 2 digits
        track = track.zfill(2)
        
        # Clean disc number
        if '/' in disc:
            disc = disc.split('/')[0]
        disc = ''.join(c for c in disc if c.isdigit())
        if not disc:
            disc = '1'
        
        # Sanitize all components
        disc = self._sanitize_filename(disc)
        track = self._sanitize_filename(track)
        title = self._sanitize_filename(title)
        artist = self._sanitize_filename(artist)
        album = self._sanitize_filename(album)
        
        # Build filename: disc - track - title - artist - album.ext
        filename = f"{disc} - {track} - {title} - {artist} - {album}{original_ext}"
        
        return filename

    def tag_file(self, filepath: str, output_dir: str) -> bool:
        """Tag a music file and copy to output directory if successful."""
        # Check if file exists
        if not os.path.exists(filepath):
            print(f"  ❌ File not found: {filepath}")
            return False

        filename = os.path.basename(filepath)
        original_ext = os.path.splitext(filename)[1]
        print(f"\nProcessing: {filename}")

        # First, try to read existing tags
        existing_tags = self._extract_existing_tags(filepath)
        if existing_tags.get('artist') and existing_tags.get('title'):
            print(f"  📋 Existing tags: {existing_tags['artist']} - {existing_tags['title']}")

        # Find matching library entry
        match = self.library.find_best_match(filename)

        # If no library match, try parsing filename
        if not match:
            print(f"  ⚠️  No library match found, trying filename parsing...")
            metadata = self._parse_filename_metadata(filename)
            if not metadata:
                print(f"  ❌ Could not extract metadata from filename")
                return False
            print(f"  📝 Parsed from filename: {metadata['artist']} - {metadata['title']}")
        else:
            print(f"  📚 Library match: {match['artist']} - {match['title']} (confidence: {match['confidence']:.2f})")

            # Get metadata from multiple sources
            metadata = self.metadata.get_metadata(match['artist'], match['title'])
            if not metadata:
                print(f"  ⚠️  No online metadata found, using library data only")
                metadata = {
                    'artist': match['artist'],
                    'title': match['title'],
                    'album': '',
                    'date': '',
                    'genre': '',
                    'source': 'library'
                }

        # Get cover art (with Last.fm fallback)
        cover_art = None
        if metadata.get('album') or metadata.get('title'):
            cover_art = self.metadata.get_cover_art(
                metadata['artist'],
                metadata.get('album', ''),
                metadata.get('title', ''),
                metadata.get('source', '')
            )
            if cover_art:
                print(f"  🖼️  Cover art downloaded")

        # Apply tags (this will also add disc/track numbers to metadata if available)
        success = self._apply_tags(filepath, metadata, cover_art)

        if success:
            # Generate new filename from metadata
            new_filename = self._generate_filename(metadata, original_ext)
            
            # Copy to tagged directory with new filename
            os.makedirs(output_dir, exist_ok=True)
            dest_path = os.path.join(output_dir, new_filename)
            
            # Handle filename conflicts
            if os.path.exists(dest_path):
                base = os.path.splitext(new_filename)[0]
                ext = os.path.splitext(new_filename)[1]
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = os.path.join(output_dir, f"{base}_{counter}{ext}")
                    counter += 1
            
            shutil.copy2(filepath, dest_path)
            print(f"  📝 New filename: {os.path.basename(dest_path)}")
            print(f"  ✅ Tagged and copied to {output_dir}")
            return True
        else:
            print(f"  ❌ Failed to apply tags")
            return False

    def _apply_tags(self, filepath: str, metadata: Dict, cover_art: Optional[bytes]) -> bool:
        """Apply metadata tags to file."""
        try:
            ext = os.path.splitext(filepath)[1].lower()

            if ext == '.m4a':
                return self._tag_m4a(filepath, metadata, cover_art)
            elif ext == '.mp3':
                return self._tag_mp3(filepath, metadata, cover_art)
            else:
                print(f"  ⚠️  Unsupported format: {ext}")
                return False

        except Exception as e:
            print(f"  ❌ Tagging error: {e}")
            return False

    def _tag_m4a(self, filepath: str, metadata: Dict, cover_art: Optional[bytes]) -> bool:
        """Tag M4A file."""
        audio = MP4(filepath)

        # Set basic tags
        audio.tags['©nam'] = [metadata['title']]  # Title
        audio.tags['©ART'] = [metadata['artist']]  # Artist
        audio.tags['aART'] = [metadata['artist']]  # Album Artist

        if metadata.get('album'):
            audio.tags['©alb'] = [metadata['album']]  # Album

        if metadata.get('date'):
            year = metadata['date'][:4] if len(metadata['date']) >= 4 else metadata['date']
            audio.tags['©day'] = [year]  # Year

        if metadata.get('genre'):
            audio.tags['©gen'] = [metadata['genre']]  # Genre

        # Add cover art
        if cover_art:
            audio.tags['covr'] = [MP4Cover(cover_art, imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()
        
        # Extract disc/track numbers from file for filename generation
        # Store them back in metadata dict for use by _generate_filename
        if audio.tags:
            # Track number
            if 'trkn' in audio.tags:
                track_info = audio.tags['trkn'][0]
                if isinstance(track_info, tuple) and len(track_info) >= 1:
                    metadata['tracknumber'] = str(track_info[0])
            
            # Disc number
            if 'disk' in audio.tags:
                disc_info = audio.tags['disk'][0]
                if isinstance(disc_info, tuple) and len(disc_info) >= 1:
                    metadata['discnumber'] = str(disc_info[0])
        
        return True

    def _tag_mp3(self, filepath: str, metadata: Dict, cover_art: Optional[bytes]) -> bool:
        """Tag MP3 file."""
        try:
            audio = MP3(filepath, ID3=ID3)
        except:
            audio = MP3(filepath)
            audio.add_tags()

        # Set basic tags
        audio.tags.add(TIT2(encoding=3, text=metadata['title']))  # Title
        audio.tags.add(TPE1(encoding=3, text=metadata['artist']))  # Artist
        audio.tags.add(TPE2(encoding=3, text=metadata['artist']))  # Album Artist

        if metadata.get('album'):
            audio.tags.add(TALB(encoding=3, text=metadata['album']))  # Album

        if metadata.get('date'):
            year = metadata['date'][:4] if len(metadata['date']) >= 4 else metadata['date']
            audio.tags.add(TDRC(encoding=3, text=year))  # Year

        # Add cover art
        if cover_art:
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=cover_art
                )
            )

        audio.save()
        
        # Extract disc/track numbers from file for filename generation
        # Store them back in metadata dict for use by _generate_filename
        if audio.tags:
            # Track number (TRCK frame)
            if 'TRCK' in audio.tags:
                track_text = str(audio.tags['TRCK'])
                if '/' in track_text:
                    metadata['tracknumber'] = track_text.split('/')[0]
                else:
                    metadata['tracknumber'] = track_text
            
            # Disc number (TPOS frame)
            if 'TPOS' in audio.tags:
                disc_text = str(audio.tags['TPOS'])
                if '/' in disc_text:
                    metadata['discnumber'] = disc_text.split('/')[0]
                else:
                    metadata['discnumber'] = disc_text
        
        return True


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description='Tag SoundCloud music files')
    parser.add_argument('--library', default='sorted/library.txt', help='Path to library.txt')
    parser.add_argument('--input-dir', default='sorted/', help='Input directory with music files')
    parser.add_argument('--output-dir', default='tagged/', help='Output directory for tagged files')
    parser.add_argument('--limit', type=int, help='Limit number of files to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')

    args = parser.parse_args()

    print("🎵 SoundCloud Music Tagger")
    print("=" * 50)

    # Initialize components
    print(f"\n📖 Loading library from {args.library}...")
    library = LibraryParser(args.library)
    print(f"   Found {len(library.entries)} library entries")

    metadata = MetadataAggregator()
    tagger = MusicTagger(library, metadata)

    # Get music files
    music_files = []
    for ext in ['.m4a', '.mp3']:
        music_files.extend(Path(args.input_dir).glob(f'*{ext}'))

    print(f"\n🎼 Found {len(music_files)} music files to process")

    if args.limit:
        music_files = music_files[:args.limit]
        print(f"   Limited to {args.limit} files")

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No files will be modified")

    # Process files
    success_count = 0
    failed_count = 0

    for i, filepath in enumerate(music_files, 1):
        print(f"\n[{i}/{len(music_files)}]", end=' ')

        if args.dry_run:
            match = library.find_best_match(filepath.name)
            if match:
                print(f"Would tag: {filepath.name}")
                print(f"  Match: {match['artist']} - {match['title']} ({match['confidence']:.2f})")
            else:
                print(f"Would skip: {filepath.name} (no match)")
        else:
            if tagger.tag_file(str(filepath), args.output_dir):
                success_count += 1
            else:
                failed_count += 1

    # Summary
    print("\n" + "=" * 50)
    print("📊 Summary:")
    print(f"   ✅ Successfully tagged: {success_count}")
    print(f"   ❌ Failed: {failed_count}")
    print(f"   📁 Output directory: {args.output_dir}")


if __name__ == '__main__':
    main()
