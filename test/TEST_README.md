# Test Suite Documentation

This directory contains comprehensive unit tests for the project's audio processing tools.

## Test Files

### test_playlist_matcher.py
Tests for the main playlist matching functionality:
- Music library cache building
- Playlist parsing (M3U8 and text formats)
- Metadata matching strategies
- Path format parsing
- Special character handling

### test_soundcloud_tagger.py
Tests for the SoundCloud music tagger:
- Library.txt parsing
- Filename matching algorithms
- Metadata aggregation from multiple sources
- File tagging (MP3 and M4A)
- Filename generation with sanitization
- Cover art handling

### test_find_duplicates.py
Tests for the audio duplicate finder:
- Audio fingerprinting methods (AcoustID, waveform, duration)
- Duplicate detection logic
- Quality comparison (bitrate, file size)
- CSV report generation
- File organization and copying

## Running Tests

### Run All Tests
```bash
# From project root
python3 -m unittest discover test -v

# Or use the test runner
python3 test/run_all_tests.py
```

### Run Specific Test File
```bash
# Playlist matcher tests
python3 -m unittest test.test_playlist_matcher -v

# SoundCloud tagger tests
python3 -m unittest test.test_soundcloud_tagger -v

# Duplicate finder tests
python3 -m unittest test.test_find_duplicates -v
```

### Run Specific Test Class
```bash
python3 -m unittest test.test_soundcloud_tagger.TestLibraryParser -v
```

### Run Specific Test Method
```bash
python3 -m unittest test.test_soundcloud_tagger.TestLibraryParser.test_library_parsing -v
```

## Coverage Reports

### Generate Coverage Report
```bash
# Install coverage tool
pip install coverage

# Run tests with coverage
python3 test/run_all_tests.py --coverage

# Or manually
python3 -m coverage run -m unittest discover test
python3 -m coverage report -m
python3 -m coverage html
```

### View Coverage
After running with coverage, open `htmlcov/index.html` in your browser to see:
- Line-by-line coverage
- Branch coverage
- Missing lines highlighted
- Per-file coverage percentages

## Test Structure

Each test file follows this structure:

1. **Setup/Teardown**: Creates temporary files/directories, cleans up after
2. **Unit Tests**: Tests individual functions and methods
3. **Integration Tests**: Tests component interactions
4. **Edge Cases**: Tests error handling and boundary conditions

## Writing New Tests

When adding new functionality:

1. Create test file: `test_<module_name>.py`
2. Import the module to test
3. Create test classes inheriting from `unittest.TestCase`
4. Write test methods starting with `test_`
5. Use `setUp()` and `tearDown()` for test fixtures
6. Run tests to verify

Example:
```python
import unittest
from pathlib import Path

class TestNewFeature(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = "example"
    
    def tearDown(self):
        """Clean up after tests."""
        pass
    
    def test_basic_functionality(self):
        """Test basic feature behavior."""
        result = my_function(self.test_data)
        self.assertEqual(result, expected_value)
```

## Dependencies

Required for running tests:
- `mutagen` - Audio file metadata handling
- `unittest` - Built-in Python testing framework

Optional for coverage:
- `coverage` - Code coverage measurement

Optional for full functionality tests:
- `pyacoustid` - Audio fingerprinting
- `pydub` - Audio processing
- `scipy` - Scientific computing
- `numpy` - Numerical operations

## Current Coverage

Run `python3 test/run_all_tests.py --coverage` to see current coverage statistics.

Target coverage goals:
- Overall: >80%
- Core modules: >90%
- Utility functions: >95%

## Continuous Integration

These tests are designed to be run in CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run tests
  run: python3 -m unittest discover test -v

- name: Generate coverage
  run: |
    pip install coverage
    python3 test/run_all_tests.py --coverage
```

## Troubleshooting

### Import Errors
If you get import errors, ensure you're running from the project root:
```bash
cd /path/to/project
python3 -m unittest test.test_module -v
```

### Missing Dependencies
Install required packages:
```bash
pip install mutagen coverage
```

### Test Failures
1. Check that test data files exist (e.g., `test/example.flac`)
2. Verify file permissions
3. Check for leftover temporary files
4. Run tests individually to isolate issues

## Best Practices

1. **Isolation**: Each test should be independent
2. **Cleanup**: Always clean up temporary files
3. **Mocking**: Use mocks for external dependencies
4. **Assertions**: Use specific assertions (assertEqual, assertIn, etc.)
5. **Documentation**: Add docstrings explaining what each test verifies
6. **Coverage**: Aim for high coverage but focus on meaningful tests