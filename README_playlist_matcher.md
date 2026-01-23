# Playlist Matcher

This script matches songs from `Favourites.m3u8` to your actual music library structure and creates a new `foobar.m3u8` playlist with corrected paths.

## Problem

Your playlist may use different path formats than your music library. For example:

**Playlist format:**
```
..\Artist(s)\Album\CD# - Track# - Artist(s) - Title - Album.ext
```

**Library format:**
```
Album Artist\Album\CD# - Track# - Title - Artist(s) - Album.ext
```

The script handles this by using metadata tags instead of file paths to match songs.

## Solution

The script:
1. **Caches** all music files and their metadata from `/Music/` directory
2. **Matches** songs using metadata tags (title, artist, album) instead of file paths
3. **Generates** a new `foobar.m3u8` playlist with correct paths
4. **Logs** any unmatched songs to `unmatched_songs.log`

## Installation

Install the required Python package:

```bash
pip install mutagen
```

## Usage

### Basic Usage

Run with default settings:

```bash
python3 playlist_matcher.py
```

This uses:
- Input: `Favourites.m3u8`
- Music library: `E:/Music/`
- Output: `foobar.m3u8`
- Log: `unmatched_songs.log`
- Format: `artist_album` (default)

### Command Line Options

```bash
python3 playlist_matcher.py [OPTIONS]

Options:
  --playlist PATH       Input playlist file (default: Favourites.m3u8)
  --music-dir PATH      Music library root directory (default: E:/Music/)
  --output PATH         Output playlist file (default: foobar.m3u8)
  --log PATH            Unmatched songs log file (default: unmatched_songs.log)
  --format FORMAT       Playlist path format (default: artist_album)
  --list-formats        List available path formats and exit
  -h, --help            Show help message
```

### Path Format Configuration

The script supports different playlist path formats via the `--format` option:

#### `artist_album` (default)
Playlist paths organized by Artist(s):
```
Artist(s)/Album/CD# - Track# - Artist(s) - Title - Album.ext
```

#### `albumartist_album`
Playlist paths organized by Album Artist:
```
Album Artist/Album/CD# - Track# - Title - Artist(s) - Album.ext
```

To list all available formats:
```bash
python3 playlist_matcher.py --list-formats
```

### Examples

**Use a different music directory:**
```bash
python3 playlist_matcher.py --music-dir /Volumes/Music
```

**Use albumartist_album format:**
```bash
python3 playlist_matcher.py --format albumartist_album
```

**Custom input/output files:**
```bash
python3 playlist_matcher.py --playlist MyPlaylist.m3u8 --output corrected.m3u8
```

**Full custom configuration:**
```bash
python3 playlist_matcher.py \
  --playlist Favourites.m3u8 \
  --music-dir /Volumes/Music \
  --output foobar.m3u8 \
  --log unmatched.log \
  --format artist_album
```

## How It Works

### 1. Metadata Caching
- Scans your entire `/Music/` directory
- Extracts metadata (title, artist, album, album artist) from each audio file
- Builds an indexed cache for fast lookups
- Processes album artists in alphabetical order

### 2. Matching Strategy
The script tries multiple strategies to find matches (in order):

1. **Exact match**: title + artist + album
2. **Partial match**: title + artist (ignoring album)
3. **Album artist match**: title + album artist
4. **Fuzzy match**: title exact, artist contained in metadata

### 3. Normalization
- Converts to lowercase
- Normalizes "feat.", "ft.", "featuring" variations
- Removes extra whitespace
- Handles special characters

### 4. Output
- **foobar.m3u8**: New playlist with corrected paths relative to `/Music/`
- **unmatched_songs.log**: Detailed log of songs that couldn't be matched

## Match Failure Diagnostics

When a song cannot be matched, the script now provides detailed diagnostic information:

**Console Output:**
```
✗ No match: Artist Name - Song Title
  Reason: Found 5 file(s) with matching title; No files found with artist 'Artist Name'
```

**Log File:**
Each unmatched song includes:
- Artist, Title, Album
- Original playlist path
- **Failure Reason** - Detailed explanation of why the match failed

**Common Failure Reasons:**
- "No files found with title 'X'" - Title doesn't exist in library
- "No files found with artist 'X'" - Artist doesn't exist in library
- "Title and artist exist separately but not in the same file" - Both exist but in different songs
- "Title exists but with different artist" - Song title found but by different artist
- "Artist exists but with different title" - Artist found but different song

This helps identify:
- Missing files in your library
- Metadata inconsistencies
- Spelling differences between playlist and library tags

## Supported Audio Formats

- FLAC (.flac)
- MP3 (.mp3)
- M4A/AAC (.m4a, .aac)
- OGG Vorbis (.ogg)
- Opus (.opus)
- WMA (.wma)

## Performance

- Caches metadata upfront to avoid repeated file reads
- Processes album artists alphabetically as requested
- Progress updates every 100 files during caching
- Efficient for large libraries (10,000+ files)

## Adding Custom Path Formats

To add a new path format, edit the `PlaylistPathParser.FORMATS` dictionary in the script:

```python
FORMATS = {
    'your_format_name': {
        'description': 'Your format description',
        'path_parts': ['part1', 'part2', 'filename'],
        'filename_pattern': r'^your_regex_pattern$',
        'filename_groups': ['group1', 'group2', ...]
    }
}
```

**Example:** If your playlist uses `Genre/Artist/Album/Track - Title.ext`:

```python
'genre_artist_album': {
    'description': 'Genre/Artist/Album/Track - Title.ext',
    'path_parts': ['genre', 'artist', 'album', 'filename'],
    'filename_pattern': r'^(\d+)\s*-\s*(.+?)\.(\w+)$',
    'filename_groups': ['track', 'title', 'ext']
}
```

Then use it with:
```bash
python3 playlist_matcher.py --format genre_artist_album
```

## Troubleshooting

### No matches found
- Check that music directory path is correct (use `--music-dir`)
- Verify audio files have proper metadata tags
- Check the unmatched songs log for details
- Try a different `--format` if your playlist structure differs

### Wrong format detected
- Use `--list-formats` to see available formats
- Specify the correct format with `--format`
- Add a custom format if needed (see above)

### Script runs slowly
- First run will be slower due to caching
- Large libraries (50,000+ files) may take several minutes
- Progress is logged every 100 files

### Import errors
Make sure mutagen is installed:
```bash
pip install mutagen
```

## Example Output

```
2026-01-22 16:30:00 - INFO - Scanning music library: /Music
2026-01-22 16:30:05 - INFO - Processing album artist: The Beatles
2026-01-22 16:30:10 - INFO - Cached 100 files...
2026-01-22 16:30:15 - INFO - Cached 200 files...
...
2026-01-22 16:35:00 - INFO - Cache built: 5000 files indexed
2026-01-22 16:35:00 - INFO - Album artists found: 250
2026-01-22 16:35:00 - INFO - Reading playlist: Favourites.m3u8
2026-01-22 16:35:30 - INFO - Writing new playlist: foobar.m3u8
2026-01-22 16:35:30 - INFO - Writing unmatched log: unmatched_songs.log
================================================================================
SUMMARY
================================================================================
Total songs: 1064
Matched: 1050
Unmatched: 14
Success rate: 98.7%

New playlist written to: foobar.m3u8
Unmatched log written to: unmatched_songs.log