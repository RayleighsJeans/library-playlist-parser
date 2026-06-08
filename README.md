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
  --cache-file PATH     Cache file path (default: <music-dir>/.playlist_matcher_cache.json)
  --no-cache            Disable cache loading and saving
  --rebuild-cache       Force rebuild cache even if valid cache exists
  --clear-cache         Clear cache file and exit
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

## Cache System

The script includes an intelligent caching system to dramatically speed up subsequent runs:

### How Caching Works

1. **First Run**: Scans your entire music library and saves metadata to `.playlist_matcher_cache.json`
2. **Subsequent Runs**: Loads cached metadata instantly (seconds vs minutes)
3. **Auto-Invalidation**: Cache is automatically rebuilt if:
   - Music library directory changes
   - Files are added, removed, or modified
   - Cache version is outdated

### Cache Features

- **Version Tracking**: Cache format version ensures compatibility
- **Change Detection**: MD5 hash of file modification times detects library changes
- **Atomic Writes**: Cache saves use atomic file operations to prevent corruption
- **JSON Format**: Human-readable cache file for debugging

### Cache Management

**View cache location:**
```bash
# Default: <music-dir>/.playlist_matcher_cache.json
ls -lh /Music/.playlist_matcher_cache.json
```

**Update cache (incremental):**
```bash
# Intelligently updates cache with new/modified/deleted files
python3 playlist_matcher.py --update-cache
```

**Force rebuild cache:**
```bash
python3 playlist_matcher.py --rebuild-cache
```

**Disable caching:**
```bash
python3 playlist_matcher.py --no-cache
```

**Clear cache:**
```bash
python3 playlist_matcher.py --clear-cache
```

**Custom cache location:**
```bash
python3 playlist_matcher.py --cache-file /path/to/custom_cache.json
```

### Incremental Updates

The `--update-cache` command provides intelligent incremental updates:

**What it does:**
1. Loads existing cache
2. Scans music directory for all audio files
3. Identifies changes:
   - **New files**: Not in cache
   - **Modified files**: Different modification time
   - **Deleted files**: In cache but not on disk
4. Updates only changed files
5. Saves updated cache

**When to use:**
- After adding new albums to your library
- After editing metadata tags
- After reorganizing files
- Periodically to keep cache fresh

**Example output:**
```
2026-05-29 09:00:00 - INFO - Starting incremental cache update
2026-05-29 09:00:01 - INFO - Cache loaded successfully: 10000 files
2026-05-29 09:00:02 - INFO - Scanning music library for changes
2026-05-29 09:00:05 - INFO - Changes detected:
2026-05-29 09:00:05 - INFO -   New files: 25
2026-05-29 09:00:05 - INFO -   Modified files: 3
2026-05-29 09:00:05 - INFO -   Deleted files: 2
2026-05-29 09:00:06 - INFO - Cache update complete: processed 28 files
2026-05-29 09:00:06 - INFO - Total files in cache: 10023
```

### Performance Impact

**Without Cache (first run):**
- 10,000 files: ~2-3 minutes
- 50,000 files: ~10-15 minutes

**With Cache (subsequent runs):**
- Any library size: ~2-5 seconds

**Incremental Update:**
- Depends on number of changes
- 100 new files: ~5-10 seconds
- Much faster than full rebuild

### Cache File Structure

```json
{
  "metadata": {
    "version": "1.0.0",
    "created_at": "2026-05-29T08:00:00",
    "updated_at": "2026-05-29T08:00:00",
    "music_dir": "/Music",
    "file_count": 10000,
    "directory_hash": "abc123..."
  },
  "cache": {
    "/Music/Artist/Album/song.flac": {
      "title": "Song Title",
      "artist": "Artist Name",
      ...
    }
  },
  "album_artist_index": {
    "artist name": ["/Music/Artist/Album/song1.flac", ...]
  }
}
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

# SoundCloud Music Tagger

Automatically tags music files in the `soundcloud/` directory using the `library.txt` reference and multiple online music databases with intelligent fallback.

## Features

- **Smart Matching**: Fuzzy matching algorithm to match ambiguous filenames with library entries
- **Multi-Source Metadata**: Cascading search across three databases:
  1. **MusicBrainz** (primary) - Comprehensive music database
  2. **Last.fm** (fallback) - Community-driven metadata
  3. **Discogs** (final fallback) - Extensive release database
- **Comprehensive Metadata**: Retrieves and tags:
  - Artist name
  - Track title
  - Album name
  - Release year
  - Genre tags
- **Cover Art**: Downloads and embeds album artwork from MusicBrainz Cover Art Archive
- **File Organization**: Successfully tagged files are **copied** to `soundcloud/sorted/` (originals preserved)
- **Existing Tag Reading**: Reads and displays current metadata before updating
- **Filename Parsing Fallback**: Extracts artist/title from filename when no library match exists
- **Supports Multiple Formats**: M4A and MP3 files
- **Artist as Album Artist**: Sets artist as album artist for proper library organization

## Installation

Required Python packages:
```bash
pip install mutagen requests
```

## Usage

### Basic Usage
Process all files in the soundcloud directory:
```bash
python3 soundcloud_tagger.py
```

### Dry Run
See what would be done without making changes:
```bash
python3 soundcloud_tagger.py --dry-run
```

### Process Limited Number of Files
Test with just a few files first:
```bash
python3 soundcloud_tagger.py --limit 10
```

### Custom Paths
```bash
python3 soundcloud_tagger.py \
  --library soundcloud/library.txt \
  --input-dir soundcloud \
  --output-dir soundcloud/sorted
```

## How It Works

1. **Library Parsing**: Reads `library.txt` and extracts artist/title pairs from various formats
2. **Existing Tag Reading**: Checks and displays current metadata in the file
3. **File Matching**: For each music file, finds the best matching library entry using fuzzy string matching
4. **Filename Parsing Fallback**: If no library match, parses "Artist - Title" from filename
5. **Multi-Source Metadata Retrieval**:
   - Tries MusicBrainz first (most comprehensive)
   - Falls back to Last.fm if MusicBrainz has no results
   - Falls back to Discogs if Last.fm has no results
   - Uses library/filename data if all online sources fail
6. **Cover Art Download**: Fetches album artwork from MusicBrainz Cover Art Archive
7. **Tagging**: Applies all metadata tags to the music file
8. **Organization**: **Copies** successfully tagged files to `soundcloud/sorted/` (originals remain untouched)

## Matching Algorithm

The script uses a sophisticated matching algorithm that:
- Cleans filenames by removing special characters and numbers
- Calculates similarity scores between filenames and library entries
- Boosts scores when artist or title names appear in the filename
- Requires minimum 40% confidence to proceed with tagging
- Handles various filename patterns and formats

## API Rate Limiting

The script respects API rate limits for all services:
- **MusicBrainz**: 1 request per second (strictly enforced)
- **Last.fm**: ~3 requests per second
- **Discogs**: 1 request per second

This ensures reliable operation without hitting rate limits.

## Output

For each file, you'll see:
- 📋 Existing tags (if present)
- 📚 Library match with confidence score (or filename parsing)
- 🔍 Database search progress (MusicBrainz → Last.fm → Discogs)
- ✓ Which database provided the metadata
- 🖼️ Cover art status
- ✅ Success/failure status

Example output:
```
[1/479]
Processing: Moon Boots - No One [77831355].m4a
  📋 Existing tags: Moon Boots - No One
  📚 Library match: Moon Boots - No One (confidence: 0.95)
  🔍 Searching MusicBrainz...
  🔍 Searching Last.fm...
  ✓ Last.fm: First Landing
  🖼️  Cover art downloaded
  ✅ Tagged and copied to soundcloud/sorted
```

## Metadata Tags Applied

### M4A Files
- `©nam`: Title
- `©ART`: Artist
- `aART`: Album Artist (same as artist)
- `©alb`: Album
- `©day`: Year
- `©gen`: Genre
- `covr`: Cover art

### MP3 Files
- `TIT2`: Title
- `TPE1`: Artist
- `TPE2`: Album Artist (same as artist)
- `TALB`: Album
- `TDRC`: Year
- `APIC`: Cover art

## Notes

- **Original files are preserved** - files are copied, not moved
- Original filenames are preserved (not renamed)
- Files are only copied after successful tagging
- Unmatched files remain in the original directory
- The script will not modify files already in `soundcloud/sorted/`
- **Multi-source fallback** ensures maximum metadata coverage:
  - MusicBrainz: Best for official releases
  - Last.fm: Good for popular tracks and remixes
  - Discogs: Excellent for vinyl releases and obscure tracks
- When all online sources fail, library/filename data is used as fallback

## Troubleshooting

**No library match found**: The filename is too different from library entries. Check if the track exists in `library.txt`.

**No online metadata found**: MusicBrainz doesn't have this recording. The file will still be tagged with library data (artist/title only).

**Failed to apply tags**: File format issue or file is corrupted. Check file integrity.

## Statistics

After processing, you'll see a summary:
```
📊 Summary:
   ✅ Successfully tagged: 450
   ❌ Failed: 29
   📁 Output directory: soundcloud/sorted

## SoundCloud Authentication Setup

To enable SoundCloud artwork fallback, you need to provide your SoundCloud API credentials.

### Setup Instructions

#### 1. Get SoundCloud Credentials

You need two pieces of information:
- **Client ID**: Your SoundCloud application client ID
- **OAuth Token** (optional): For authenticated requests

##### Option A: Find Your Client ID from Browser
1. Go to [SoundCloud](https://soundcloud.com)
2. Open browser Developer Tools (F12)
3. Go to Network tab
4. Play any track
5. Look for API requests to `api-v2.soundcloud.com`
6. Find the `client_id` parameter in the request URL

##### Option B: Create a SoundCloud App
1. Go to [SoundCloud Developers](https://developers.soundcloud.com/)
2. Register a new application
3. Copy your Client ID from the app settings

#### 2. Create Configuration File

Create a file named `soundcloud_config.json` in the project directory:

```json
{
  "soundcloud": {
    "client_id": "YOUR_CLIENT_ID_HERE",
    "oauth_token": "YOUR_OAUTH_TOKEN_HERE"
  }
}
```

**Alternative location**: `~/.soundcloud_config.json` (in your home directory)

#### 3. Secure Your Credentials

**IMPORTANT**: Never commit your credentials to version control!

Add to `.gitignore`:
```
soundcloud_config.json
```

### How It Works

When configured, the tagger will:

1. Try **MusicBrainz Cover Art Archive** first (no auth needed)
2. Try **Last.fm artwork** second (no auth needed)
3. Try **SoundCloud artwork** as final fallback (requires auth)

The SoundCloud API will search for tracks matching the artist and title, then download the highest quality artwork available.

### Testing

Test your configuration:

```bash
python3 -c "
from soundcloud_tagger import SoundCloudAPI

sc = SoundCloudAPI()
if sc.client_id:
    print('✓ SoundCloud credentials loaded')
    print(f'  Client ID: {sc.client_id[:10]}...')
else:
    print('✗ No SoundCloud credentials found')
"
```

### Troubleshooting

#### "No SoundCloud credentials found"
- Check that `soundcloud_config.json` exists in the project directory or `~/.soundcloud_config.json`
- Verify the JSON syntax is correct
- Ensure the file has the correct structure with `soundcloud.client_id`

#### "SoundCloud API error: 401"
- Your client ID may be invalid or expired
- Try getting a fresh client ID from the browser method

### "SoundCloud API error: 429"
- You've hit the rate limit
- The script includes rate limiting (0.5s between requests)
- Wait a few minutes and try again

### Privacy & Security

- Your credentials are stored locally only
- They are never transmitted except to SoundCloud's official API
- The script only requests public track information and artwork
- No personal data or listening history is accessed

### Optional: OAuth Token

For higher rate limits and access to private tracks (if needed):

1. Use the SoundCloud OAuth flow to get a token
2. Add it to your config file under `oauth_token`
3. The script will automatically use it for authenticated requests

**Note**: OAuth token is optional. The client ID alone is sufficient for public track artwork.