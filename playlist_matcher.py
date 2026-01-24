#!/usr/bin/env python3
"""
Playlist Matcher Script
Matches songs from Favourites.m3u8 to the actual music library structure
and creates a new foobar.m3u8 playlist with corrected paths.
"""

import os
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import logging
import argparse

try:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4
    from mutagen.oggvorbis import OggVorbis
except ImportError:
    print("Error: mutagen library not found. Install it with: pip install mutagen")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MusicLibraryCache:
    """Cache for music library metadata"""

    def __init__(self, music_dir: str):
        self.music_dir = Path(music_dir)
        self.cache: Dict[str, Dict] = {}
        self.album_artist_index: Dict[str, List[str]] = defaultdict(list)

    def normalize_string(self, s: str) -> str:
        """Normalize string for comparison (lowercase, remove special chars)"""
        if not s:
            return ""
        # Remove common variations and normalize
        s = s.lower().strip()
        # Remove featuring variations
        s = re.sub(r'\s*[\(\[]?\s*ft\.?\s*', ' feat. ', s)
        s = re.sub(r'\s*[\(\[]?\s*feat\.?\s*', ' feat. ', s)
        s = re.sub(r'\s*[\(\[]?\s*featuring\s*', ' feat. ', s)
        # Remove extra whitespace
        s = re.sub(r'\s+', ' ', s)
        return s

    def extract_metadata(self, file_path: Path) -> Optional[Dict]:
        """Extract metadata from audio file"""
        try:
            audio = MutagenFile(str(file_path), easy=True)
            if audio is None:
                return None

            # Extract common tags
            metadata = {
                'path': str(file_path),
                'title': '',
                'artist': '',
                'album': '',
                'albumartist': '',
                'tracknumber': '',
                'discnumber': ''
            }

            # Get tags (handle both easy and regular tag formats)
            if hasattr(audio, 'tags') and audio.tags:
                # Try easy tags first
                for key in ['title', 'artist', 'album', 'albumartist', 'tracknumber', 'discnumber']:
                    value = audio.get(key, [''])
                    if isinstance(value, list):
                        metadata[key] = value[0] if value else ''
                    else:
                        metadata[key] = str(value) if value else ''

            # Normalize for comparison
            metadata['title_norm'] = self.normalize_string(metadata['title'])
            metadata['artist_norm'] = self.normalize_string(metadata['artist'])
            metadata['album_norm'] = self.normalize_string(metadata['album'])
            metadata['albumartist_norm'] = self.normalize_string(metadata['albumartist'])

            return metadata

        except Exception as e:
            logger.debug(f"Could not read metadata from {file_path}: {e}")
            return None

    def build_cache_from_paths(self, file_paths: List[str]):
        """Build cache from a list of file paths

        Args:
            file_paths: List of file paths to process
        """
        logger.info(f"Building cache from {len(file_paths)} file paths")

        file_count = 0
        for file_path_str in sorted(file_paths):
            file_path = Path(file_path_str)

            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                continue

            metadata = self.extract_metadata(file_path)
            if metadata:
                file_key = str(file_path)
                self.cache[file_key] = metadata

                # Index by album artist for faster lookup
                albumartist_norm = metadata['albumartist_norm']
                if albumartist_norm:
                    self.album_artist_index[albumartist_norm].append(file_key)

                file_count += 1
                if file_count % 100 == 0:
                    logger.info(f"Cached {file_count} files...")

        logger.info(f"Cache built: {file_count} files indexed")
        logger.info(f"Album artists found: {len(self.album_artist_index)}")

    def build_cache_from_directory(self, music_dir: Optional[Path] = None):
        """Build cache by scanning a directory structure

        Args:
            music_dir: Directory to scan. If None, uses self.music_dir
        """
        if music_dir is None:
            music_dir = self.music_dir

        logger.info(f"Scanning music library: {music_dir}")

        if not music_dir.exists():
            logger.error(f"Music directory does not exist: {music_dir}")
            return

        # Supported audio extensions
        audio_extensions = {'.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wma', '.aac'}

        file_count = 0
        # Walk through the directory structure: Album Artist / Album / files
        for album_artist_dir in sorted(music_dir.iterdir()):
            if not album_artist_dir.is_dir():
                continue

            album_artist_name = album_artist_dir.name
            logger.info(f"Processing album artist: {album_artist_name}")

            for album_dir in album_artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue

                for file_path in album_dir.iterdir():
                    if file_path.suffix.lower() in audio_extensions:
                        metadata = self.extract_metadata(file_path)
                        if metadata:
                            file_key = str(file_path)
                            self.cache[file_key] = metadata

                            # Index by album artist for faster lookup
                            albumartist_norm = metadata['albumartist_norm']
                            if albumartist_norm:
                                self.album_artist_index[albumartist_norm].append(file_key)

                            file_count += 1
                            if file_count % 100 == 0:
                                logger.info(f"Cached {file_count} files...")

        logger.info(f"Cache built: {file_count} files indexed")
        logger.info(f"Album artists found: {len(self.album_artist_index)}")

    def build_cache(self, file_paths: Optional[List[str]] = None):
        """Build cache of music files

        Args:
            file_paths: Optional list of file paths. If provided, builds cache from these paths.
                       If None, scans the music_dir directory structure.
        """
        if file_paths is not None:
            self.build_cache_from_paths(file_paths)
        else:
            self.build_cache_from_directory()

    def find_match(self, title: str, artist: str, album: str = "") -> Tuple[Optional[str], Optional[str]]:
        """Find matching file in cache based on metadata

        Returns:
            Tuple of (matched_file_path, None) if found, or (None, failure_reason) if not found
        """
        title_norm = self.normalize_string(title)
        artist_norm = self.normalize_string(artist)
        album_norm = self.normalize_string(album)

        # Collect diagnostic information
        title_matches = []
        artist_matches = []
        album_matches = []
        title_artist_album_matches = []  # Files matching artist and album

        # Strategy 1: Try exact match on title + artist + album
        for file_key, metadata in self.cache.items():
            if metadata['title_norm'] == title_norm:
                title_matches.append(file_key)
            if metadata['artist_norm'] == artist_norm or metadata['albumartist_norm'] == artist_norm:
                artist_matches.append(file_key)
            if metadata['album_norm'] == album_norm:
                album_matches.append(file_key)

            # Track files that match artist and album (for partial matching)
            if ((metadata['artist_norm'] == artist_norm or metadata['albumartist_norm'] == artist_norm) and
                metadata['album_norm'] == album_norm):
                title_artist_album_matches.append(file_key)

            if (metadata['title_norm'] == title_norm and
                metadata['artist_norm'] == artist_norm and
                metadata['album_norm'] == album_norm):
                return file_key, None

        # Strategy 2: Try match on title + artist (album might differ)
        for file_key, metadata in self.cache.items():
            if (metadata['title_norm'] == title_norm and
                metadata['artist_norm'] == artist_norm):
                return file_key, None

        # Strategy 3: Try matching with album artist instead
        for file_key, metadata in self.cache.items():
            if (metadata['title_norm'] == title_norm and
                metadata['albumartist_norm'] == artist_norm):
                return file_key, None

        # Strategy 4: Fuzzy match - title matches and artist is contained
        for file_key, metadata in self.cache.items():
            if metadata['title_norm'] == title_norm:
                # Check if artist is part of the metadata artist or vice versa
                if (artist_norm in metadata['artist_norm'] or
                    metadata['artist_norm'] in artist_norm or
                    artist_norm in metadata['albumartist_norm'] or
                    metadata['albumartist_norm'] in artist_norm):
                    return file_key, None

        # Strategy 5: Partial match - if artist matches, find best title match
        # Priority: titles in matching album > titles by same artist
        if artist_matches:
            logger.info(f"Attempting partial match for artist '{artist}'")

            # First, try to find similar titles in the matching album
            if title_artist_album_matches:
                logger.info(f"  Found {len(title_artist_album_matches)} tracks by artist in album '{album}'")
                # Use fuzzy string matching on titles
                best_match = None
                best_score = 0

                for file_key in title_artist_album_matches:
                    metadata = self.cache[file_key]
                    # Simple similarity: check for common words
                    title_words = set(title_norm.split())
                    meta_words = set(metadata['title_norm'].split())
                    if title_words and meta_words:
                        common = len(title_words & meta_words)
                        score = common / max(len(title_words), len(meta_words))
                        if score > best_score and score > 0.5:  # At least 50% similarity
                            best_score = score
                            best_match = file_key

                if best_match:
                    logger.info(f"  Partial match found in album (similarity: {best_score:.2f})")
                    return best_match, None

            # Second, try to find similar titles by the same artist (any album)
            logger.info(f"  Searching all tracks by artist '{artist}'")
            best_match = None
            best_score = 0

            for file_key in artist_matches:
                metadata = self.cache[file_key]
                # Simple similarity: check for common words
                title_words = set(title_norm.split())
                meta_words = set(metadata['title_norm'].split())
                if title_words and meta_words:
                    common = len(title_words & meta_words)
                    score = common / max(len(title_words), len(meta_words))
                    if score > best_score and score > 0.5:  # At least 50% similarity
                        best_score = score
                        best_match = file_key

            if best_match:
                logger.info(f"  Partial match found by artist (similarity: {best_score:.2f})")
                return best_match, None

        # No match found - generate detailed failure reason
        failure_parts = []

        if not title_matches:
            failure_parts.append(f"No files found with title '{title}'")
        else:
            failure_parts.append(f"Found {len(title_matches)} file(s) with matching title")

        if not artist_matches:
            failure_parts.append(f"No files found with artist '{artist}'")
        else:
            failure_parts.append(f"Found {len(artist_matches)} file(s) with matching artist")

        if album and not album_matches:
            failure_parts.append(f"No files found with album '{album}'")
        elif album:
            failure_parts.append(f"Found {len(album_matches)} file(s) with matching album")

        # Check for partial matches
        if title_matches and artist_matches:
            # We have both title and artist matches, but not in the same file
            failure_parts.append("Title and artist exist separately but not in the same file")
        elif title_matches:
            failure_parts.append("Title exists but with different artist")
        elif artist_matches:
            failure_parts.append("Artist exists but with different title")

        failure_reason = "; ".join(failure_parts)
        return None, failure_reason


class PlaylistPathParser:
    """Parse playlist paths based on configurable format patterns"""

    # Predefined format patterns
    FORMATS = {
        'artist_album': {
            'description': 'Artist(s)/Album/CD# - Track# - Artist(s) - Title - Album.ext',
            'path_parts': ['artist', 'album', 'filename'],
            # Pattern uses ' - ' (space-dash-space) as delimiter to allow '-' in names
            'filename_pattern': r'^(\d+) - (\d+) - (.+?) - (.+?) - (.+?)\.(\w+)$',
            'filename_groups': ['disc', 'track', 'artist', 'title', 'album', 'ext']
        },
        'albumartist_album': {
            'description': 'Album Artist/Album/CD# - Track# - Title - Artist(s) - Album.ext',
            'path_parts': ['albumartist', 'album', 'filename'],
            # Pattern uses ' - ' (space-dash-space) as delimiter to allow '-' in names
            'filename_pattern': r'^(\d+) - (\d+) - (.+?) - (.+?) - (.+?)\.(\w+)$',
            'filename_groups': ['disc', 'track', 'title', 'artist', 'album', 'ext']
        }
    }

    def __init__(self, format_name: str = 'artist_album'):
        """Initialize parser with specified format"""
        if format_name not in self.FORMATS:
            raise ValueError(f"Unknown format: {format_name}. Available: {list(self.FORMATS.keys())}")

        self.format = self.FORMATS[format_name]
        self.format_name = format_name
        logger.info(f"Using playlist path format: {format_name}")
        logger.info(f"Format description: {self.format['description']}")

    def parse_path(self, path_line: str) -> Dict[str, str]:
        """Parse a playlist path line and extract metadata"""
        result = {
            'artist': '',
            'title': '',
            'album': '',
            'albumartist': '',
            'disc': '',
            'track': ''
        }

        # Clean up path separators
        clean_path = path_line.replace('..\\', '').replace('../', '').replace('\\', '/')
        path_parts = clean_path.split('/')

        # Extract directory-level information
        for i, part_name in enumerate(self.format['path_parts'][:-1]):  # Exclude filename
            if i < len(path_parts) - 1:  # -1 because last part is filename
                result[part_name] = path_parts[i]

        # Parse filename
        if path_parts:
            filename = path_parts[-1]
            pattern = self.format['filename_pattern']
            match = re.match(pattern, filename)

            if match:
                groups = self.format['filename_groups']
                for i, group_name in enumerate(groups):
                    if group_name in result:  # Only store if it's a metadata field
                        result[group_name] = match.group(i + 1)

        return result


class PlaylistMatcher:
    """Match playlist entries to music library"""

    def __init__(self, playlist_path: str, music_dir: str, output_path: str, log_path: str,
                 path_format: str = 'artist_album'):
        self.playlist_path = Path(playlist_path)
        self.music_dir = Path(music_dir)
        self.output_path = Path(output_path)
        self.log_path = Path(log_path)
        self.cache = MusicLibraryCache(music_dir)
        self.path_parser = PlaylistPathParser(path_format)

    def detect_playlist_format(self, lines: List[str]) -> str:
        """Detect playlist format (m3u8 or text)
        
        Args:
            lines: Playlist file lines
            
        Returns:
            'm3u8' or 'text'
        """
        # Check first few non-empty lines
        for line in lines[:10]:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#EXTM3U') or line.startswith('#EXTINF'):
                return 'm3u8'
        
        # If no M3U8 markers found, assume simple text format
        return 'text'
    
    def parse_text_entry(self, line: str) -> Optional[Tuple[str, str, str]]:
        """Parse simple text playlist entry (Artist - Title format)
        
        Args:
            line: Text line in format "Artist - Title"
            
        Returns:
            Tuple of (artist, title, album) or None if parsing fails
        """
        line = line.strip()
        if not line or line.startswith('#'):
            return None
        
        # Split on ' - ' to get artist and title
        if ' - ' in line:
            parts = line.split(' - ', 1)
            artist = parts[0].strip()
            title = parts[1].strip()
            album = ''  # No album info in simple text format
            return artist, title, album
        
        return None

    def parse_playlist_entry(self, extinf_line: str, path_line: str) -> Optional[Tuple[str, str, str, str]]:
        """Parse EXTINF and path lines to extract metadata"""
        # Parse EXTINF line: #EXTINF:duration,Artist - Title
        extinf_match = re.match(r'#EXTINF:(\d+),(.+)', extinf_line)
        if not extinf_match:
            return None

        duration = extinf_match.group(1)
        artist_title = extinf_match.group(2)

        # Split artist and title from EXTINF
        if ' - ' in artist_title:
            extinf_artist, extinf_title = artist_title.split(' - ', 1)
        else:
            extinf_artist = ""
            extinf_title = artist_title

        # Parse path using configured format to get album
        path_metadata = self.path_parser.parse_path(path_line)

        # IMPORTANT: Prefer EXTINF metadata (correct, unescaped) over path metadata
        # The EXTINF line has the authoritative artist and title
        # Only use path for album since EXTINF doesn't contain it
        artist = extinf_artist.strip()
        title = extinf_title.strip()
        album = path_metadata.get('album', '').strip()

        # Fallback: if EXTINF didn't have artist/title, use path
        if not artist:
            artist = path_metadata.get('artist', '').strip()
        if not title:
            title = path_metadata.get('title', '').strip()

        return duration, artist, title, album

    def build_library_cache(self, file_paths: Optional[List[str]] = None):
        """Step 1: Build library cache

        Args:
            file_paths: Optional list of file paths. If None, scans music_dir
        """
        logger.info("Step 1: Building library cache")
        self.cache.build_cache(file_paths)

    def read_old_playlist(self) -> List[str]:
        """Step 2: Read and parse old playlist

        Returns:
            List of playlist lines
        """
        logger.info(f"Step 2: Reading playlist: {self.playlist_path}")

        if not self.playlist_path.exists():
            logger.error(f"Playlist file does not exist: {self.playlist_path}")
            return []

        with open(self.playlist_path, 'r', encoding='utf-8-sig') as f:
            lines = [line.rstrip('\n\r') for line in f.readlines()]

        logger.info(f"Read {len(lines)} lines from playlist")
        return lines

    def find_matches(self, playlist_lines: List[str]) -> Tuple[List[Tuple[str, str]], List[Dict]]:
        """Step 3: Find matches for playlist entries

        Args:
            playlist_lines: Lines from the playlist file

        Returns:
            Tuple of (matched_entries, unmatched_entries)
        """
        logger.info("Step 3: Finding matches for playlist entries")
        
        # Detect playlist format
        playlist_format = self.detect_playlist_format(playlist_lines)
        logger.info(f"Detected playlist format: {playlist_format}")

        matched_entries = []
        unmatched_entries = []

        if playlist_format == 'm3u8':
            # Process M3U8 format
            i = 0
            while i < len(playlist_lines):
                line = playlist_lines[i]

                if line.startswith('#EXTINF:'):
                    if i + 1 < len(playlist_lines):
                        extinf_line = line
                        path_line = playlist_lines[i + 1]

                        # Parse entry
                        parsed = self.parse_playlist_entry(extinf_line, path_line)
                        if parsed:
                            duration, artist, title, album = parsed

                            # Find match in library
                            matched_path, failure_reason = self.cache.find_match(title, artist, album)

                            if matched_path:
                                # Convert to relative path from music directory
                                rel_path = Path(matched_path).relative_to(self.music_dir)
                                matched_entries.append((extinf_line, str(rel_path)))
                                logger.debug(f"✓ Matched: {artist} - {title}")
                            else:
                                # Log detailed failure reason
                                logger.warning(f"✗ No match: {artist} - {title}")
                                logger.warning(f"  Reason: {failure_reason}")

                                unmatched_entries.append({
                                    'artist': artist,
                                    'title': title,
                                    'album': album,
                                    'original_path': path_line,
                                    'failure_reason': failure_reason
                                })

                        i += 2  # Skip both lines
                    else:
                        i += 1
                else:
                    i += 1
        
        else:  # text format
            # Process simple text format (Artist - Title per line)
            for line in playlist_lines:
                parsed = self.parse_text_entry(line)
                if parsed:
                    artist, title, album = parsed
                    
                    # Find match in library
                    matched_path, failure_reason = self.cache.find_match(title, artist, album)
                    
                    if matched_path:
                        # Convert to relative path from music directory
                        rel_path = Path(matched_path).relative_to(self.music_dir)
                        # Create EXTINF line with default duration
                        extinf_line = f"#EXTINF:-1,{artist} - {title}"
                        matched_entries.append((extinf_line, str(rel_path)))
                        logger.debug(f"✓ Matched: {artist} - {title}")
                    else:
                        # Log detailed failure reason
                        logger.warning(f"✗ No match: {artist} - {title}")
                        logger.warning(f"  Reason: {failure_reason}")
                        
                        unmatched_entries.append({
                            'artist': artist,
                            'title': title,
                            'album': album,
                            'original_path': line,
                            'failure_reason': failure_reason
                        })

        logger.info(f"Matched: {len(matched_entries)}, Unmatched: {len(unmatched_entries)}")
        return matched_entries, unmatched_entries

    def write_new_playlist(self, matched_entries: List[Tuple[str, str]]):
        """Step 4: Write new playlist with corrected paths

        Args:
            matched_entries: List of (extinf_line, path) tuples
        """
        logger.info(f"Step 4: Writing new playlist: {self.output_path}")

        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for extinf, path in matched_entries:
                f.write(f'{extinf}\n')
                f.write(f'{path}\n')

        logger.info(f"Wrote {len(matched_entries)} entries to new playlist")

    def write_log(self, matched_entries: List[Tuple[str, str]], unmatched_entries: List[Dict]):
        """Step 5: Write log of unmatched entries

        Args:
            matched_entries: List of matched entries
            unmatched_entries: List of unmatched entry dictionaries
        """
        logger.info(f"Step 5: Writing unmatched log: {self.log_path}")

        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(f"Unmatched Songs Log\n")
            f.write(f"===================\n\n")
            f.write(f"Total songs in playlist: {len(matched_entries) + len(unmatched_entries)}\n")
            f.write(f"Matched: {len(matched_entries)}\n")
            f.write(f"Unmatched: {len(unmatched_entries)}\n\n")

            if unmatched_entries:
                f.write("Unmatched Songs:\n")
                f.write("-" * 80 + "\n")
                for entry in unmatched_entries:
                    f.write(f"Artist: {entry['artist']}\n")
                    f.write(f"Title: {entry['title']}\n")
                    f.write(f"Album: {entry['album']}\n")
                    f.write(f"Original Path: {entry['original_path']}\n")
                    f.write(f"Failure Reason: {entry.get('failure_reason', 'Unknown')}\n")
                    f.write("-" * 80 + "\n")

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total songs: {len(matched_entries) + len(unmatched_entries)}")
        logger.info(f"Matched: {len(matched_entries)}")
        logger.info(f"Unmatched: {len(unmatched_entries)}")
        if len(matched_entries) + len(unmatched_entries) > 0:
            logger.info(f"Success rate: {len(matched_entries) / (len(matched_entries) + len(unmatched_entries)) * 100:.1f}%")
        logger.info(f"\nNew playlist written to: {self.output_path}")
        logger.info(f"Unmatched log written to: {self.log_path}")

    def process_playlist(self, file_paths: Optional[List[str]] = None):
        """Process the playlist and create new one with corrected paths

        This method orchestrates all the steps:
        1. Build library cache
        2. Read old playlist
        3. Find matches
        4. Write new playlist
        5. Write log

        Args:
            file_paths: Optional list of file paths for cache building. If None, scans music_dir
        """
        # Step 1: Build library cache
        self.build_library_cache(file_paths)

        # Step 2: Read old playlist
        playlist_lines = self.read_old_playlist()
        if not playlist_lines:
            return

        # Step 3: Find matches
        matched_entries, unmatched_entries = self.find_matches(playlist_lines)

        # Step 4: Write new playlist
        self.write_new_playlist(matched_entries)

        # Step 5: Write log
        self.write_log(matched_entries, unmatched_entries)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Match playlist songs to music library and create corrected playlist',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Playlist Path Formats:
  artist_album       : Artist(s)/Album/CD# - Track# - Artist(s) - Title - Album.ext (default)
  albumartist_album  : Album Artist/Album/CD# - Track# - Title - Artist(s) - Album.ext

Examples:
  %(prog)s
  %(prog)s --music-dir /Volumes/Music --format albumartist_album
  %(prog)s --playlist MyPlaylist.m3u8 --output corrected.m3u8
        """
    )

    parser.add_argument(
        '--playlist',
        default='Favourites.m3u8',
        help='Input playlist file (default: Favourites.m3u8)'
    )
    parser.add_argument(
        '--music-dir',
        default='E:/Music/',
        help='Music library root directory (default: E:/Music/)'
    )
    parser.add_argument(
        '--output',
        default='foobar.m3u8',
        help='Output playlist file (default: foobar.m3u8)'
    )
    parser.add_argument(
        '--log',
        default='unmatched_songs.log',
        help='Unmatched songs log file (default: unmatched_songs.log)'
    )
    parser.add_argument(
        '--format',
        choices=['artist_album', 'albumartist_album'],
        default='artist_album',
        help='Playlist path format (default: artist_album)'
    )
    parser.add_argument(
        '--list-formats',
        action='store_true',
        help='List available path formats and exit'
    )

    args = parser.parse_args()

    # List formats if requested
    if args.list_formats:
        print("\nAvailable Playlist Path Formats:\n")
        for name, fmt in PlaylistPathParser.FORMATS.items():
            print(f"  {name}:")
            print(f"    {fmt['description']}\n")
        sys.exit(0)

    # Check if music directory exists
    if not os.path.exists(args.music_dir):
        logger.error(f"Music directory not found: {args.music_dir}")
        logger.info("Use --music-dir to specify your music library path")
        sys.exit(1)

    # Create matcher and process
    matcher = PlaylistMatcher(
        args.playlist,
        args.music_dir,
        args.output,
        args.log,
        args.format
    )
    matcher.process_playlist()


if __name__ == "__main__":
    main()
