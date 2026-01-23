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
    
    def build_cache(self):
        """Build cache of all music files in the library"""
        logger.info(f"Scanning music library: {self.music_dir}")
        
        if not self.music_dir.exists():
            logger.error(f"Music directory does not exist: {self.music_dir}")
            return
        
        # Supported audio extensions
        audio_extensions = {'.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wma', '.aac'}
        
        file_count = 0
        # Walk through the directory structure: Album Artist / Album / files
        for album_artist_dir in sorted(self.music_dir.iterdir()):
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
    
    def find_match(self, title: str, artist: str, album: str = "") -> Optional[str]:
        """Find matching file in cache based on metadata"""
        title_norm = self.normalize_string(title)
        artist_norm = self.normalize_string(artist)
        album_norm = self.normalize_string(album)
        
        # Strategy 1: Try exact match on title + artist + album
        for file_key, metadata in self.cache.items():
            if (metadata['title_norm'] == title_norm and 
                metadata['artist_norm'] == artist_norm and
                metadata['album_norm'] == album_norm):
                return file_key
        
        # Strategy 2: Try match on title + artist (album might differ)
        for file_key, metadata in self.cache.items():
            if (metadata['title_norm'] == title_norm and 
                metadata['artist_norm'] == artist_norm):
                return file_key
        
        # Strategy 3: Try matching with album artist instead
        for file_key, metadata in self.cache.items():
            if (metadata['title_norm'] == title_norm and 
                metadata['albumartist_norm'] == artist_norm):
                return file_key
        
        # Strategy 4: Fuzzy match - title matches and artist is contained
        for file_key, metadata in self.cache.items():
            if metadata['title_norm'] == title_norm:
                # Check if artist is part of the metadata artist or vice versa
                if (artist_norm in metadata['artist_norm'] or 
                    metadata['artist_norm'] in artist_norm or
                    artist_norm in metadata['albumartist_norm'] or
                    metadata['albumartist_norm'] in artist_norm):
                    return file_key
        
        return None


class PlaylistPathParser:
    """Parse playlist paths based on configurable format patterns"""
    
    # Predefined format patterns
    FORMATS = {
        'artist_album': {
            'description': 'Artist(s)/Album/CD# - Track# - Artist(s) - Title - Album.ext',
            'path_parts': ['artist', 'album', 'filename'],
            'filename_pattern': r'^(\d+)\s*-\s*(\d+)\s*-\s*(.+?)\s*-\s*(.+?)\s*-\s*(.+?)\.(\w+)$',
            'filename_groups': ['disc', 'track', 'artist', 'title', 'album', 'ext']
        },
        'albumartist_album': {
            'description': 'Album Artist/Album/CD# - Track# - Title - Artist(s) - Album.ext',
            'path_parts': ['albumartist', 'album', 'filename'],
            'filename_pattern': r'^(\d+)\s*-\s*(\d+)\s*-\s*(.+?)\s*-\s*(.+?)\s*-\s*(.+?)\.(\w+)$',
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
        
        # Parse path using configured format
        path_metadata = self.path_parser.parse_path(path_line)
        
        # Prefer path metadata, fall back to EXTINF
        artist = path_metadata.get('artist', '').strip() or extinf_artist.strip()
        title = path_metadata.get('title', '').strip() or extinf_title.strip()
        album = path_metadata.get('album', '').strip()
        
        return duration, artist, title, album
    
    def process_playlist(self):
        """Process the playlist and create new one with corrected paths"""
        logger.info(f"Reading playlist: {self.playlist_path}")
        
        if not self.playlist_path.exists():
            logger.error(f"Playlist file does not exist: {self.playlist_path}")
            return
        
        # Build cache first
        self.cache.build_cache()
        
        # Read playlist
        with open(self.playlist_path, 'r', encoding='utf-8-sig') as f:
            lines = [line.rstrip('\n\r') for line in f.readlines()]
        
        # Process playlist
        matched_entries = []
        unmatched_entries = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if line.startswith('#EXTINF:'):
                if i + 1 < len(lines):
                    extinf_line = line
                    path_line = lines[i + 1]
                    
                    # Parse entry
                    parsed = self.parse_playlist_entry(extinf_line, path_line)
                    if parsed:
                        duration, artist, title, album = parsed
                        
                        # Find match in library
                        matched_path = self.cache.find_match(title, artist, album)
                        
                        if matched_path:
                            # Convert to relative path from music directory
                            rel_path = Path(matched_path).relative_to(self.music_dir)
                            matched_entries.append((extinf_line, str(rel_path)))
                            logger.debug(f"✓ Matched: {artist} - {title}")
                        else:
                            unmatched_entries.append({
                                'artist': artist,
                                'title': title,
                                'album': album,
                                'original_path': path_line
                            })
                            logger.warning(f"✗ No match: {artist} - {title}")
                    
                    i += 2  # Skip both lines
                else:
                    i += 1
            else:
                i += 1
        
        # Write new playlist
        logger.info(f"Writing new playlist: {self.output_path}")
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for extinf, path in matched_entries:
                f.write(f'{extinf}\n')
                f.write(f'{path}\n')
        
        # Write log of unmatched entries
        logger.info(f"Writing unmatched log: {self.log_path}")
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
                    f.write("-" * 80 + "\n")
        
        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total songs: {len(matched_entries) + len(unmatched_entries)}")
        logger.info(f"Matched: {len(matched_entries)}")
        logger.info(f"Unmatched: {len(unmatched_entries)}")
        logger.info(f"Success rate: {len(matched_entries) / (len(matched_entries) + len(unmatched_entries)) * 100:.1f}%")
        logger.info(f"\nNew playlist written to: {self.output_path}")
        logger.info(f"Unmatched log written to: {self.log_path}")


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

# Made with Bob
