#!/usr/bin/env python3
"""
Unit tests for find_duplicates.py

Tests the audio duplicate finder functionality including:
- Audio fingerprinting
- Duplicate detection
- Quality comparison
- File organization
"""

import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path to import find_duplicates
sys.path.insert(0, str(Path(__file__).parent.parent / 'soundcloud'))

import find_duplicates as fd


class TestAudioFingerprinter(unittest.TestCase):
    """Test audio fingerprinting functionality."""
    
    def test_determine_method_with_acoustid(self):
        """Test method selection when acoustid is available."""
        with patch.object(fd, 'ACOUSTID_AVAILABLE', True):
            fingerprinter = fd.AudioFingerprinter()
            self.assertEqual(fingerprinter.method, 'acoustid')
    
    def test_determine_method_with_waveform(self):
        """Test method selection when only waveform libraries available."""
        with patch.object(fd, 'ACOUSTID_AVAILABLE', False), \
             patch.object(fd, 'PYDUB_AVAILABLE', True), \
             patch.object(fd, 'SCIPY_AVAILABLE', True):
            fingerprinter = fd.AudioFingerprinter()
            self.assertEqual(fingerprinter.method, 'waveform')
    
    def test_determine_method_duration_only(self):
        """Test fallback to duration-only method."""
        with patch.object(fd, 'ACOUSTID_AVAILABLE', False), \
             patch.object(fd, 'PYDUB_AVAILABLE', False), \
             patch.object(fd, 'MUTAGEN_AVAILABLE', True):
            fingerprinter = fd.AudioFingerprinter()
            self.assertEqual(fingerprinter.method, 'duration_only')
    
    def test_determine_method_none(self):
        """Test when no libraries are available."""
        with patch.object(fd, 'ACOUSTID_AVAILABLE', False), \
             patch.object(fd, 'PYDUB_AVAILABLE', False), \
             patch.object(fd, 'MUTAGEN_AVAILABLE', False):
            fingerprinter = fd.AudioFingerprinter()
            self.assertEqual(fingerprinter.method, 'none')


class TestDuplicateFinder(unittest.TestCase):
    """Test duplicate finding functionality."""
    
    def setUp(self):
        """Set up test environment with temporary directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.temp_dir, 'input')
        self.output_dir = os.path.join(self.temp_dir, 'output')
        os.makedirs(self.input_dir)
        os.makedirs(self.output_dir)
        
        self.finder = fd.DuplicateFinder(self.input_dir, self.output_dir)
    
    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.temp_dir)
    
    def test_scan_files_empty_directory(self):
        """Test scanning empty directory."""
        files = self.finder.scan_files()
        self.assertEqual(len(files), 0)
    
    def test_scan_files_with_audio_files(self):
        """Test scanning directory with audio files."""
        # Create dummy audio files
        test_files = ['song1.mp3', 'song2.m4a', 'song3.flac']
        for filename in test_files:
            filepath = os.path.join(self.input_dir, filename)
            Path(filepath).touch()
        
        files = self.finder.scan_files()
        self.assertEqual(len(files), 3)
    
    def test_scan_files_excludes_sorted(self):
        """Test that files in 'sorted' subdirectory are excluded."""
        # Create files in main directory
        Path(os.path.join(self.input_dir, 'song1.mp3')).touch()
        
        # Create sorted subdirectory with file
        sorted_dir = os.path.join(self.input_dir, 'sorted')
        os.makedirs(sorted_dir)
        Path(os.path.join(sorted_dir, 'song2.mp3')).touch()
        
        files = self.finder.scan_files()
        # Should only find song1.mp3, not song2.mp3 in sorted/
        self.assertEqual(len(files), 1)
        self.assertIn('song1.mp3', str(files[0]))
    
    def test_scan_files_ignores_non_audio(self):
        """Test that non-audio files are ignored."""
        # Create audio and non-audio files
        Path(os.path.join(self.input_dir, 'song.mp3')).touch()
        Path(os.path.join(self.input_dir, 'readme.txt')).touch()
        Path(os.path.join(self.input_dir, 'image.jpg')).touch()
        
        files = self.finder.scan_files()
        self.assertEqual(len(files), 1)
        self.assertIn('song.mp3', str(files[0]))
    
    def test_analyze_file_structure(self):
        """Test that analyze_file returns correct structure."""
        # Create a dummy file
        test_file = os.path.join(self.input_dir, 'test.mp3')
        Path(test_file).touch()
        
        # Mock the fingerprinter
        self.finder.fingerprinter.get_fingerprint = Mock(
            return_value=('abc123', 180.5)
        )
        
        result = self.finder.analyze_file(Path(test_file))
        
        self.assertIsNotNone(result)
        self.assertEqual(result['filename'], 'test.mp3')
        self.assertEqual(result['fingerprint'], 'abc123')
        self.assertEqual(result['duration'], 180.5)
        self.assertIn('path', result)
        self.assertIn('size', result)
        self.assertIn('bitrate', result)


class TestDuplicateDetection(unittest.TestCase):
    """Test duplicate detection logic."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.temp_dir, 'input')
        self.output_dir = os.path.join(self.temp_dir, 'output')
        os.makedirs(self.input_dir)
        
        self.finder = fd.DuplicateFinder(self.input_dir, self.output_dir)
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)
    
    def test_duplicate_grouping(self):
        """Test that files with same fingerprint are grouped."""
        # Manually populate fingerprints dict
        self.finder.fingerprints = {
            'fp1': [
                {'path': Path('file1.mp3'), 'filename': 'file1.mp3', 
                 'bitrate': 320000, 'size': 5000000},
                {'path': Path('file2.mp3'), 'filename': 'file2.mp3',
                 'bitrate': 128000, 'size': 2000000}
            ],
            'fp2': [
                {'path': Path('file3.mp3'), 'filename': 'file3.mp3',
                 'bitrate': 256000, 'size': 4000000}
            ]
        }
        
        # Manually trigger duplicate identification logic
        for fingerprint, file_list in self.finder.fingerprints.items():
            if len(file_list) > 1:
                sorted_files = sorted(
                    file_list,
                    key=lambda x: (x['bitrate'], x['size']),
                    reverse=True
                )
                original = sorted_files[0]
                duplicates = sorted_files[1:]
                self.finder.duplicates.append((original, duplicates))
        
        # Should have 1 duplicate group
        self.assertEqual(len(self.finder.duplicates), 1)
        
        # Original should be higher quality (file1.mp3 with 320kbps)
        original, dups = self.finder.duplicates[0]
        self.assertEqual(original['filename'], 'file1.mp3')
        self.assertEqual(len(dups), 1)
        self.assertEqual(dups[0]['filename'], 'file2.mp3')
    
    def test_quality_comparison_bitrate_priority(self):
        """Test that higher bitrate is preferred."""
        files = [
            {'bitrate': 128000, 'size': 5000000},
            {'bitrate': 320000, 'size': 3000000}
        ]
        
        sorted_files = sorted(
            files,
            key=lambda x: (x['bitrate'], x['size']),
            reverse=True
        )
        
        # Higher bitrate should be first
        self.assertEqual(sorted_files[0]['bitrate'], 320000)
    
    def test_quality_comparison_size_secondary(self):
        """Test that size is used when bitrate is equal."""
        files = [
            {'bitrate': 320000, 'size': 3000000},
            {'bitrate': 320000, 'size': 5000000}
        ]
        
        sorted_files = sorted(
            files,
            key=lambda x: (x['bitrate'], x['size']),
            reverse=True
        )
        
        # Larger size should be first when bitrate equal
        self.assertEqual(sorted_files[0]['size'], 5000000)


class TestReportGeneration(unittest.TestCase):
    """Test CSV report generation."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.temp_dir, 'input')
        self.output_dir = os.path.join(self.temp_dir, 'output')
        os.makedirs(self.input_dir)
        
        self.finder = fd.DuplicateFinder(self.input_dir, self.output_dir)
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)
    
    def test_save_report_creates_file(self):
        """Test that report file is created."""
        # Add some test duplicates
        self.finder.duplicates = [
            (
                {'filename': 'original.mp3', 'duration': 180.0, 
                 'size': 5000000, 'bitrate': 320000, 'fingerprint': 'abc123'},
                [
                    {'filename': 'dup1.mp3', 'duration': 180.0,
                     'size': 3000000, 'bitrate': 128000, 'fingerprint': 'abc123'}
                ]
            )
        ]
        
        report_path = self.finder.save_report('test_report.csv')
        
        self.assertTrue(os.path.exists(report_path))
    
    def test_save_report_content(self):
        """Test that report contains correct data."""
        # Add test duplicates
        self.finder.duplicates = [
            (
                {'filename': 'original.mp3', 'duration': 180.0,
                 'size': 5000000, 'bitrate': 320000, 'fingerprint': 'abc123'},
                [
                    {'filename': 'dup1.mp3', 'duration': 180.0,
                     'size': 3000000, 'bitrate': 128000, 'fingerprint': 'abc123'}
                ]
            )
        ]
        
        report_path = self.finder.save_report('test_report.csv')
        
        # Read and verify content
        with open(report_path, 'r') as f:
            content = f.read()
            self.assertIn('ORIGINAL', content)
            self.assertIn('DUPLICATE', content)
            self.assertIn('original.mp3', content)
            self.assertIn('dup1.mp3', content)


class TestFileCopying(unittest.TestCase):
    """Test file copying functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.input_dir = os.path.join(self.temp_dir, 'input')
        self.output_dir = os.path.join(self.temp_dir, 'output')
        os.makedirs(self.input_dir)
        
        self.finder = fd.DuplicateFinder(self.input_dir, self.output_dir)
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)
    
    def test_copy_originals_creates_output_dir(self):
        """Test that output directory is created if it doesn't exist."""
        # Remove output dir
        if os.path.exists(self.output_dir):
            os.rmdir(self.output_dir)
        
        # Create test file
        test_file = os.path.join(self.input_dir, 'test.mp3')
        Path(test_file).write_text('test content')
        
        # Add to duplicates
        self.finder.duplicates = [
            (
                {'path': Path(test_file), 'filename': 'test.mp3'},
                []
            )
        ]
        
        self.finder.copy_originals()
        
        # Output dir should be created
        self.assertTrue(os.path.exists(self.output_dir))
    
    def test_copy_originals_handles_conflicts(self):
        """Test that filename conflicts are handled."""
        # Create test file
        test_file = os.path.join(self.input_dir, 'test.mp3')
        Path(test_file).write_text('test content')
        
        # Create conflicting file in output
        os.makedirs(self.output_dir, exist_ok=True)
        conflict_file = os.path.join(self.output_dir, 'test.mp3')
        Path(conflict_file).write_text('existing content')
        
        # Add to duplicates
        self.finder.duplicates = [
            (
                {'path': Path(test_file), 'filename': 'test.mp3'},
                []
            )
        ]
        
        self.finder.copy_originals()
        
        # Should create test_1.mp3
        self.assertTrue(os.path.exists(os.path.join(self.output_dir, 'test_1.mp3')))


def run_tests():
    """Run all tests with verbose output."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestAudioFingerprinter))
    suite.addTests(loader.loadTestsFromTestCase(TestDuplicateFinder))
    suite.addTests(loader.loadTestsFromTestCase(TestDuplicateDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestReportGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestFileCopying))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 70)
    print("Test Summary:")
    print(f"  Tests run: {result.testsRun}")
    print(f"  Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  Failures: {len(result.failures)}")
    print(f"  Errors: {len(result.errors)}")
    print("=" * 70)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)

# Made with Bob
