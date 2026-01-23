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


class PlaylistMatcher:
    """Match playlist entries to music library"""
    
    def __init__(self, playlist_path: str, music_dir: str, output_path: str, log_path: str):
        self.playlist_path = Path(playlist_path)
        self.music_dir = Path(music_dir)
        self.output_path = Path(output_path)
        self.log_path = Path(log_path)
        self.cache = MusicLibraryCache(music_dir)
        
    def parse_playlist_entry(self, extinf_line: str, path_line: str) -> Optional[Tuple[str, str, str, str]]:
        """Parse EXTINF and path lines to extract metadata"""
        # Parse EXTINF line: #EXTINF:duration,Artist - Title
        extinf_match = re.match(r'#EXTINF:(\d+),(.+)', extinf_line)
        if not extinf_match:
            return None
        
        duration = extinf_match.group(1)
        artist_title = extinf_match.group(2)
        
        # Split artist and title
        if ' - ' in artist_title:
            artist, title = artist_title.split(' - ', 1)
        else:
            artist = ""
            title = artist_title
        
        # Extract album from path if possible
        # Path format: ..\Artist(s)\Album\CD# - Track# - Artist(s) - Title - Album.ext
        album = ""
        path_parts = path_line.replace('..\\', '').replace('../', '').split('/')
        if len(path_parts) >= 2:
            album = path_parts[1]  # Album is second part
        
        return duration, artist.strip(), title.strip(), album.strip()
    
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
    # Configuration
    PLAYLIST_PATH = "Favourites.m3u8"
    MUSIC_DIR = "/Music"
    OUTPUT_PATH = "foobar.m3u8"
    LOG_PATH = "unmatched_songs.log"
    
    # Check if music directory exists
    if not os.path.exists(MUSIC_DIR):
        logger.error(f"Music directory not found: {MUSIC_DIR}")
        logger.info("Please update MUSIC_DIR in the script to point to your music library")
        sys.exit(1)
    
    # Create matcher and process
    matcher = PlaylistMatcher(PLAYLIST_PATH, MUSIC_DIR, OUTPUT_PATH, LOG_PATH)
    matcher.process_playlist()


if __name__ == "__main__":
    main()

# Made with Bob
