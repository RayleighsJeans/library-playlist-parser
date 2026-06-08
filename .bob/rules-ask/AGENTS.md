# Project Documentation Rules (Non-Obvious Only)

## Non-Obvious Documentation Context

### Dual Cache Building Not in CLI Help
- `build_cache()` accepts optional `file_paths` parameter for programmatic use
- This feature is not documented in `--help` output
- Only discoverable by reading code or README's "Advanced Usage" section
- Critical for library integration scenarios

### Test Notebook Requires Template File
- `test_playlist_matcher.ipynb` requires `example.flac` in project root
- This dependency is not obvious from notebook alone
- Template file is used to generate test library with proper metadata
- Missing file causes test failures without clear error message

### Special Character Handling Pattern
- Unicode division slash `∕` (U+2215) used in filenames instead of `/`
- This is a cross-platform compatibility pattern, not a bug
- Metadata tags preserve original characters
- Pattern demonstrated in test notebook but not explained in main README

### Playlist Format Auto-Detection
- Script auto-detects M3U8 vs simple text format
- Text format (Artist - Title per line) is undocumented feature
- Converted to M3U8 internally with duration `-1`
- No CLI flag to force format - detection is automatic

### EXTINF Line Priority
- EXTINF metadata takes precedence over path-derived metadata
- This is intentional design but not explicitly documented
- Path metadata only used for album field (EXTINF lacks it)
- Important for understanding why path changes don't affect matching