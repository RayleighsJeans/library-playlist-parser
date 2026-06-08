# Project Coding Rules (Non-Obvious Only)

## Critical Implementation Details

### Path Format Pattern System
- `PlaylistPathParser.FORMATS` dictionary defines path parsing patterns
- Filename regex uses ` - ` (space-dash-space) as delimiter - allows hyphens in artist/title names
- Pattern: `r'^(\d+) - (\d+) - (.+?) - (.+?) - (.+?)\.(\w+)$'`
- Non-greedy matching (`.+?`) is critical to prevent over-matching across delimiters

### Cache Building Dual Mode
- `build_cache()` method has hidden dual behavior based on `file_paths` parameter
- `file_paths=None`: scans directory (default CLI)
- `file_paths=[...]`: builds from list (programmatic use)
- This is not documented in CLI help but critical for library integration

### Matching Strategy Order Matters
- `find_match()` tries 5 strategies sequentially - order is critical
- Strategy 5 (similarity scoring) uses >50% threshold - hardcoded, not configurable
- Returns tuple `(path, None)` on success or `(None, reason)` on failure
- Failure reason string format is used by logging - don't change structure

### EXTINF Metadata Priority
- In `parse_playlist_entry()`, EXTINF line is authoritative for artist/title
- Path metadata only used for album (EXTINF doesn't contain it)
- This priority is intentional - path may have escaped characters, EXTINF has correct data

### Special Character Sanitization
- Filenames use Unicode division slash `∕` (U+2215) instead of `/`
- Metadata tags preserve original characters
- This pattern must be maintained for cross-platform compatibility