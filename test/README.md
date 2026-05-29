# Test Suite for Playlist Matcher

This directory contains unit tests for the playlist_matcher.py script.

## Structure

- `test_playlist_matcher.py` - Main test suite with 11 test cases
- `example.flac` - Template FLAC file for creating test library
- `test_coverage_analysis.md` - Detailed coverage analysis and recommendations
- `__init__.py` - Python package marker

## Running Tests

### Run all tests
```bash
python -m pytest test/
```

### Run with verbose output
```bash
python -m pytest test/ -v
```

### Run specific test
```bash
python -m pytest test/test_playlist_matcher.py::TestPlaylistMatcher::test_m3u8_playlist_matching -v
```

### Run with unittest (no pytest required)
```bash
python -m unittest test.test_playlist_matcher
```

### Run single test with unittest
```bash
python -m unittest test.test_playlist_matcher.TestPlaylistMatcher.test_m3u8_playlist_matching
```

## Code Coverage

### Running Coverage Analysis
```bash
# Run tests with coverage
python3 -m coverage run -m unittest test.test_playlist_matcher

# View coverage report in terminal
python3 -m coverage report -m

# Generate HTML coverage report
python3 -m coverage html
# Open htmlcov/index.html in browser
```

### Current Coverage Stats
- **playlist_matcher.py**: 73% coverage (404 statements, 111 missing)
- **Total project**: 82% coverage (including test code)
- **11 test cases** covering core functionality

See [`test_coverage_analysis.md`](test_coverage_analysis.md) for detailed gap analysis.

## Test Coverage

The test suite covers:

1. **Mock Library Creation** - Verifies test library structure with proper metadata
2. **M3U8 Playlist Matching** - Tests standard M3U8 format with 100% match rate
3. **Text Playlist Matching** - Tests simple text format (Artist - Title per line)
4. **Special Character Handling** - Verifies `/` → `∕` sanitization in filenames
5. **Format Detection** - Tests automatic detection of M3U8 vs text format
6. **Advanced Matching Strategies** - Tests all 5 sequential matching strategies
7. **Cache Building from Paths** - Tests programmatic cache building
8. **Error Handling** - Tests missing files and invalid directories
9. **Invalid Parser Format** - Tests error handling for unknown formats
10. **Empty Playlist** - Tests edge case of empty playlist
11. **Malformed Entries** - Tests handling of invalid playlist entries

## Test Data

Tests use 10 sample songs including edge cases:
- Special characters in titles (e.g., "1/2 Lovesong")
- Multiple artists (e.g., "JAY-Z, Beyoncé")
- Parentheses and quotes in titles
- Various album formats

## Requirements

```bash
pip install mutagen pytest
```

## Expected Results

All tests should pass with 100% match rate:
- 10/10 songs matched in M3U8 format test
- 10/10 songs matched in text format test
- Proper special character handling verified
- Format auto-detection working correctly