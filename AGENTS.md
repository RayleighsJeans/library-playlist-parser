# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
Python script for matching playlist entries to music library files using metadata tags instead of file paths.

## Non-Obvious Project-Specific Information

### Critical Path Format System
- Script uses **configurable path format patterns** via `PlaylistPathParser.FORMATS` dictionary
- Two built-in formats: `artist_album` (default) and `albumartist_album`
- Filename pattern uses ` - ` (space-dash-space) as delimiter to allow hyphens in artist/title names
- Pattern: `r'^(\d+) - (\d+) - (.+?) - (.+?) - (.+?)\.(\w+)$'` for parsing CD#, Track#, metadata

### Dual Cache Building Strategy
- `MusicLibraryCache.build_cache()` accepts **optional file_paths parameter**
- If `file_paths` provided: builds cache from list (faster, for programmatic use)
- If `None`: scans `music_dir` directory structure (default CLI behavior)
- This dual approach is not obvious from CLI usage alone

### Multi-Strategy Matching Algorithm
- `find_match()` uses **5 sequential strategies** with fallback:
  1. Exact: title + artist + album
  2. Partial: title + artist (ignoring album)
  3. Album artist: title + albumartist instead of artist
  4. Fuzzy: title exact, artist substring match
  5. Similarity: word-based similarity scoring (>50% threshold) prioritizing same album
- Returns `(matched_path, None)` on success or `(None, failure_reason)` with diagnostics

### Special Character Handling in Test Suite
- Test notebook (`test_playlist_matcher.ipynb`) demonstrates critical pattern:
- **Filenames**: `/` → `∕` (Unicode division slash U+2215) for filesystem compatibility
- **Metadata tags**: Original characters preserved in audio file tags
- Example: "1/2 Lovesong" in tags, "1∕2 Lovesong" in filename
- This sanitization is essential for cross-platform compatibility

### Playlist Format Auto-Detection
- `detect_playlist_format()` checks for `#EXTM3U` or `#EXTINF` markers
- Supports both M3U8 format and simple text format (Artist - Title per line)
- Text format entries converted to M3U8 with default duration `-1`
- **EXTINF metadata is authoritative** - path metadata only used for album info

### Testing Requirements
- Test notebook requires `example.flac` template file in project root
- Creates mock library structure: `test_music_library/Artist/Album/files`
- Tests first 10 songs from `Favourites.m3u8` (must exist for testing)
- Expected 100% match rate with proper test data

## Running Tests
```bash
# Install dependencies
pip install mutagen

# Run all unit tests (11 tests)
python3 -m unittest test.test_playlist_matcher -v

# Run specific test
python3 -m unittest test.test_playlist_matcher.TestPlaylistMatcher.test_m3u8_playlist_matching -v

# With pytest (if installed)
pytest test/ -v

# Run with coverage analysis
python3 -m coverage run -m unittest test.test_playlist_matcher
python3 -m coverage report -m
# Current coverage: 73% (playlist_matcher.py), 82% (total project)
```

## CLI Usage
```bash
# Basic usage (defaults: Favourites.m3u8 → foobar.m3u8)
python3 playlist_matcher.py

# Custom paths and format
python3 playlist_matcher.py --playlist input.m3u8 --music-dir /path/to/music --format albumartist_album

# Cache management
python3 playlist_matcher.py --update-cache   # Incremental update (new/modified/deleted files)
python3 playlist_matcher.py --rebuild-cache  # Force rebuild
python3 playlist_matcher.py --no-cache       # Disable caching
python3 playlist_matcher.py --clear-cache    # Delete cache file

# List available formats
python3 playlist_matcher.py --list-formats