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

### Architecture

The script is organized into modular components:

#### **MusicLibraryCache Class**
Manages metadata caching and song matching:
- `extract_metadata()` - Reads audio file tags using mutagen
- `normalize_string()` - Normalizes text for comparison
- `build_cache_from_paths()` - Builds cache from provided file paths
- `build_cache_from_directory()` - Scans directory for audio files
- `build_cache()` - Flexible cache builder (accepts file paths or scans directory)
- `find_match()` - Multi-strategy matching algorithm

#### **PlaylistPathParser Class**
Parses playlist paths using configurable regex patterns:
- Supports multiple path format configurations
- Uses ` - ` (space-dash-space) as delimiter to allow hyphens in names
- Extensible format system for custom path structures

#### **PlaylistMatcher Class**
Orchestrates the matching process in 5 steps:
1. `build_library_cache()` - Build metadata cache
2. `read_old_playlist()` - Parse playlist file
3. `find_matches()` - Match entries to library
4. `write_new_playlist()` - Write corrected playlist
5. `write_log()` - Write unmatched log with diagnostics

### 1. Metadata Caching

The cache building process is flexible and efficient:

**From Directory (default):**
- Scans your entire music directory recursively
- Extracts metadata (title, artist, album, album artist) from each audio file
- Builds indexed lookups for fast matching
- Processes album artists in alphabetical order
- Progress updates every 100 files

**From File Paths (programmatic use):**
- Accepts a pre-computed list of file paths
- Useful for integration with other tools or custom workflows
- Skips directory scanning for faster processing

```python
# Example: Using custom file paths
from playlist_matcher import PlaylistMatcher

matcher = PlaylistMatcher(
    playlist_path='my_playlist.m3u8',
    music_dir='/Music',
    output_path='output.m3u8',
    log_path='unmatched.log'
)

# Provide your own file list
file_paths = ['/Music/Artist/Album/song1.flac', '/Music/Artist/Album/song2.flac']
matcher.process_playlist(file_paths=file_paths)
```

### 2. Matching Strategy

The script tries multiple strategies to find matches (in order of priority):

1. **Exact match**: title + artist + album all match
2. **Fuzzy match with album priority**: Similar title + artist, prioritizes same album
3. **Partial match**: title + artist (ignoring album)
4. **Album artist match**: title + album artist instead of artist
5. **Fuzzy title match**: Title exact, artist contained in metadata

Each strategy provides detailed failure diagnostics when no match is found.

### 3. Normalization

Text normalization ensures flexible matching:
- Converts to lowercase
- Normalizes "feat.", "ft.", "featuring" variations
- Removes extra whitespace
- Handles special characters
- Preserves original metadata in tags while sanitizing filenames

### 4. Output

- **foobar.m3u8**: New playlist with corrected paths relative to music directory
- **unmatched_songs.log**: Detailed log with failure diagnostics for each unmatched song

## Match Failure Diagnostics

When a song cannot be matched, the script provides detailed diagnostic information:

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
- "Found N file(s) with matching title; No files found with artist 'X'" - Title exists but artist mismatch

This helps identify:
- Missing files in your library
- Metadata inconsistencies
- Spelling differences between playlist and library tags
- Artist name variations (e.g., "The Beatles" vs "Beatles")

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
- Optional file path list for even faster processing

## Testing

### Self-Test with test_playlist_matcher.ipynb

A Jupyter notebook is provided for testing the script with a mock library:

**What it does:**
1. Parses the first 10 songs from `Favourites.m3u8`
2. Creates a mock music library with proper directory structure
3. Generates FLAC files with correct metadata tags
4. Handles special characters (e.g., `/` in titles) via sanitization
5. Runs the playlist matcher script
6. Verifies results and displays statistics

**How to use:**
```bash
# Install Jupyter if needed
pip install jupyter mutagen

# Run the notebook
jupyter notebook test_playlist_matcher.ipynb
```

**Test workflow:**
1. **Setup** - Installs dependencies and imports modules
2. **Parse Playlist** - Extracts metadata from first 10 songs
3. **Create Mock Library** - Builds test library with proper structure:
   ```
   test_music_library/
   ├── Artist Name/
   │   └── Album Name/
   │       └── 1 - 01 - Title - Artist - Album.flac
   ```
4. **Run Matcher** - Tests the script with test data
5. **Verify Results** - Checks output playlist and unmatched log

**Special Character Handling:**
The test notebook demonstrates how the script handles problematic characters:
- Filenames: `/` → `∕` (Unicode division slash)
- Metadata tags: Original characters preserved
- Example: "1/2 Lovesong" in metadata, "1∕2 Lovesong" in filename

**Expected Results:**
- 10/10 songs matched (100% success rate)
- Corrected paths in `test_output.m3u8`
- Empty or minimal `test_unmatched.log`

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
- Check the unmatched songs log for detailed diagnostics
- Try a different `--format` if your playlist structure differs
- Run the test notebook to verify the script works correctly

### Wrong format detected
- Use `--list-formats` to see available formats
- Specify the correct format with `--format`
- Add a custom format if needed (see above)

### Script runs slowly
- First run will be slower due to caching
- Large libraries (50,000+ files) may take several minutes
- Progress is logged every 100 files
- Consider using file path list for faster processing

### Special characters in filenames
- The script automatically sanitizes problematic characters
- Metadata tags preserve original characters
- See test notebook for examples

### Import errors
Make sure mutagen is installed:
```bash
pip install mutagen
```

### Testing issues
Run the test notebook to verify:
```bash
jupyter notebook test_playlist_matcher.ipynb
```

## Example Output

```
2026-01-22 16:30:00 - INFO - Step 1: Building library cache
2026-01-22 16:30:00 - INFO - Scanning music library: /Music
2026-01-22 16:30:05 - INFO - Processing album artist: The Beatles
2026-01-22 16:30:10 - INFO - Cached 100 files...
2026-01-22 16:30:15 - INFO - Cached 200 files...
...
2026-01-22 16:35:00 - INFO - Cache built: 5000 files indexed
2026-01-22 16:35:00 - INFO - Album artists found: 250
2026-01-22 16:35:00 - INFO - Step 2: Reading playlist: Favourites.m3u8
2026-01-22 16:35:00 - INFO - Read 2128 lines from playlist
2026-01-22 16:35:00 - INFO - Step 3: Finding matches for playlist entries
2026-01-22 16:35:25 - INFO - Matched: 1050, Unmatched: 14
2026-01-22 16:35:25 - INFO - Step 4: Writing new playlist: foobar.m3u8
2026-01-22 16:35:25 - INFO - Wrote 1050 entries to new playlist
2026-01-22 16:35:25 - INFO - Step 5: Writing unmatched log: unmatched_songs.log
================================================================================
SUMMARY
================================================================================
Total songs: 1064
Matched: 1050
Unmatched: 14
Success rate: 98.7%

New playlist written to: foobar.m3u8
Unmatched log written to: unmatched_songs.log
```

## Advanced Usage

### Programmatic Use

```python
from playlist_matcher import PlaylistMatcher

# Create matcher instance
matcher = PlaylistMatcher(
    playlist_path='my_playlist.m3u8',
    music_dir='/Music',
    output_path='output.m3u8',
    log_path='unmatched.log',
    path_format='artist_album'
)

# Option 1: Process with directory scanning (default)
matcher.process_playlist()

# Option 2: Process with custom file paths
file_paths = ['/Music/Artist/Album/song.flac', ...]
matcher.process_playlist(file_paths=file_paths)

# Option 3: Step-by-step processing
matcher.build_library_cache()
playlist_lines = matcher.read_old_playlist()
matched, unmatched = matcher.find_matches(playlist_lines)
matcher.write_new_playlist(matched)
matcher.write_log(matched, unmatched)
```

### Integration with Other Tools

The modular design allows easy integration:

```python
# Example: Use with custom file discovery
import glob
from playlist_matcher import PlaylistMatcher

# Find all FLAC files using custom logic
file_paths = glob.glob('/Music/**/*.flac', recursive=True)

# Process with pre-computed file list
matcher = PlaylistMatcher('playlist.m3u8', '/Music', 'output.m3u8', 'log.txt')
matcher.process_playlist(file_paths=file_paths)
```

## Files

- `playlist_matcher.py` - Main script
- `test_playlist_matcher.ipynb` - Test notebook with mock library
- `README_playlist_matcher.md` - This documentation
- `example.flac` - Template FLAC file for testing (required for test notebook)

## License

This script is provided as-is for personal use.