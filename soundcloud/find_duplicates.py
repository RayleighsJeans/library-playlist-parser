#!/usr/bin/env python3
"""
Audio Duplicate Finder
Finds duplicate audio files by comparing audio fingerprints using chromaprint/acoustid.
Falls back to duration + waveform comparison if chromaprint is not available.
"""

import os
import csv
import hashlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
import shutil

try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    print("Warning: mutagen not available. Install with: pip install mutagen")
    MUTAGEN_AVAILABLE = False

try:
    import acoustid
    import chromaprint
    ACOUSTID_AVAILABLE = True
except ImportError:
    print("Warning: acoustid/chromaprint not available. Using fallback method.")
    print("For better accuracy, install with: pip install pyacoustid")
    ACOUSTID_AVAILABLE = False

try:
    import numpy as np
    from scipy.io import wavfile
    from scipy.signal import resample
    SCIPY_AVAILABLE = True
except ImportError:
    print("Warning: scipy not available. Install with: pip install scipy numpy")
    SCIPY_AVAILABLE = False

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    print("Warning: pydub not available. Install with: pip install pydub")
    PYDUB_AVAILABLE = False


class AudioFingerprinter:
    """Generate audio fingerprints for duplicate detection."""

    def __init__(self):
        self.method = self._determine_method()
        print(f"Using fingerprint method: {self.method}")

    def _determine_method(self) -> str:
        """Determine which fingerprinting method to use based on available libraries."""
        if ACOUSTID_AVAILABLE:
            return "acoustid"
        elif PYDUB_AVAILABLE and SCIPY_AVAILABLE:
            return "waveform"
        elif MUTAGEN_AVAILABLE:
            return "duration_only"
        else:
            return "none"

    def get_fingerprint(self, filepath: str) -> Optional[Tuple[str, float]]:
        """
        Get audio fingerprint and duration.
        Returns: (fingerprint_hash, duration_seconds) or None if failed
        """
        if self.method == "acoustid":
            return self._fingerprint_acoustid(filepath)
        elif self.method == "waveform":
            return self._fingerprint_waveform(filepath)
        elif self.method == "duration_only":
            return self._fingerprint_duration(filepath)
        else:
            return None

    def _fingerprint_acoustid(self, filepath: str) -> Optional[Tuple[str, float]]:
        """Use Chromaprint/AcoustID for high-quality fingerprinting."""
        try:
            duration, fingerprint = acoustid.fingerprint_file(filepath)
            # Use the fingerprint as hash
            fp_hash = hashlib.md5(fingerprint.encode()).hexdigest()
            return (fp_hash, duration)
        except Exception as e:
            print(f"  ⚠️  AcoustID error for {Path(filepath).name}: {e}")
            return None

    def _fingerprint_waveform(self, filepath: str) -> Optional[Tuple[str, float]]:
        """
        Fallback: Compare first 15 seconds of audio waveform.
        Converts to mono, resamples to 8kHz, and creates hash of waveform.
        """
        try:
            # Load audio file
            audio = AudioSegment.from_file(filepath)
            duration = len(audio) / 1000.0  # Convert to seconds

            # Take first 15 seconds
            sample_duration = min(15000, len(audio))  # 15 seconds in milliseconds
            sample = audio[:sample_duration]

            # Convert to mono and resample to 8kHz for comparison
            sample = sample.set_channels(1)
            sample = sample.set_frame_rate(8000)

            # Get raw audio data
            raw_data = sample.raw_data

            # Create hash of the waveform
            waveform_hash = hashlib.md5(raw_data).hexdigest()

            return (waveform_hash, duration)
        except Exception as e:
            print(f"  ⚠️  Waveform error for {Path(filepath).name}: {e}")
            return None

    def _fingerprint_duration(self, filepath: str) -> Optional[Tuple[str, float]]:
        """
        Last resort: Use only duration for grouping.
        This will group files by duration, requiring manual review.
        """
        try:
            audio = MutagenFile(filepath)
            if audio and audio.info:
                duration = audio.info.length
                # Use duration rounded to nearest second as "fingerprint"
                duration_key = f"duration_{int(duration)}"
                return (duration_key, duration)
        except Exception as e:
            print(f"  ⚠️  Duration error for {Path(filepath).name}: {e}")
            return None


class DuplicateFinder:
    """Find duplicate audio files and manage originals."""

    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.fingerprinter = AudioFingerprinter()

        # Storage for analysis
        self.fingerprints: Dict[str, List[Dict]] = defaultdict(list)
        self.duplicates: List[Tuple[str, List[str]]] = []  # (original, [duplicates])

    def scan_files(self) -> List[Path]:
        """Scan input directory for audio files."""
        audio_extensions = {'.mp3', '.m4a', '.flac', '.ogg', '.wav', '.aac'}
        files = []

        for ext in audio_extensions:
            files.extend(self.input_dir.glob(f'*{ext}'))

        # Exclude already sorted files
        files = [f for f in files if 'sorted' not in str(f)]

        return sorted(files)

    def analyze_file(self, filepath: Path) -> Optional[Dict]:
        """Analyze a single file and return its metadata."""
        try:
            # Get fingerprint
            result = self.fingerprinter.get_fingerprint(str(filepath))
            if not result:
                return None

            fingerprint, duration = result

            # Get file size and bitrate
            file_size = filepath.stat().st_size

            bitrate = None
            if MUTAGEN_AVAILABLE:
                try:
                    audio = MutagenFile(str(filepath))
                    if audio and audio.info:
                        bitrate = getattr(audio.info, 'bitrate', None)
                except:
                    pass

            return {
                'path': filepath,
                'filename': filepath.name,
                'fingerprint': fingerprint,
                'duration': duration,
                'size': file_size,
                'bitrate': bitrate or 0
            }
        except Exception as e:
            print(f"  ❌ Error analyzing {filepath.name}: {e}")
            return None

    def find_duplicates(self):
        """Scan all files and identify duplicates."""
        print(f"\n🔍 Scanning {self.input_dir} for audio files...")
        files = self.scan_files()
        print(f"   Found {len(files)} audio files\n")

        if not files:
            print("No audio files found!")
            return

        # Analyze all files
        print("📊 Analyzing files...")
        for i, filepath in enumerate(files, 1):
            print(f"   [{i}/{len(files)}] {filepath.name}")

            metadata = self.analyze_file(filepath)
            if metadata:
                # Group by fingerprint
                self.fingerprints[metadata['fingerprint']].append(metadata)

        # Identify duplicates (fingerprints with multiple files)
        print(f"\n🔎 Identifying duplicates...")
        for fingerprint, file_list in self.fingerprints.items():
            if len(file_list) > 1:
                # Sort by quality: bitrate desc, then size desc
                sorted_files = sorted(
                    file_list,
                    key=lambda x: (x['bitrate'], x['size']),
                    reverse=True
                )

                # First file is the original (highest quality)
                original = sorted_files[0]
                duplicates = sorted_files[1:]

                self.duplicates.append((
                    original,
                    duplicates
                ))

        print(f"   Found {len(self.duplicates)} groups of duplicates")
        print(f"   Total duplicate files: {sum(len(dups) for _, dups in self.duplicates)}")

    def save_report(self, report_path: str = "duplicates_report.csv"):
        """Save duplicate report to CSV file."""
        report_file = self.input_dir.parent / report_path

        with open(report_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Status', 'Filename', 'Duration (s)', 'Size (MB)',
                'Bitrate (kbps)', 'Fingerprint', 'Group'
            ])

            for group_idx, (original, duplicates) in enumerate(self.duplicates, 1):
                # Write original
                writer.writerow([
                    'ORIGINAL',
                    original['filename'],
                    f"{original['duration']:.1f}",
                    f"{original['size'] / 1024 / 1024:.2f}",
                    f"{original['bitrate'] / 1000:.0f}" if original['bitrate'] else 'N/A',
                    original['fingerprint'][:8],
                    group_idx
                ])

                # Write duplicates
                for dup in duplicates:
                    writer.writerow([
                        'DUPLICATE',
                        dup['filename'],
                        f"{dup['duration']:.1f}",
                        f"{dup['size'] / 1024 / 1024:.2f}",
                        f"{dup['bitrate'] / 1000:.0f}" if dup['bitrate'] else 'N/A',
                        dup['fingerprint'][:8],
                        group_idx
                    ])

                # Empty row between groups
                writer.writerow([])

        print(f"\n📄 Report saved to: {report_file}")
        return report_file

    def copy_originals(self):
        """Copy original (highest quality) files to output directory."""
        if not self.duplicates:
            print("\n✓ No duplicates found - all files are unique!")
            return

        os.makedirs(self.output_dir, exist_ok=True)

        print(f"\n📁 Copying originals to {self.output_dir}...")
        copied = 0

        for original, duplicates in self.duplicates:
            src = original['path']
            dst = self.output_dir / original['filename']

            # Handle filename conflicts
            if dst.exists():
                base = dst.stem
                ext = dst.suffix
                counter = 1
                while dst.exists():
                    dst = self.output_dir / f"{base}_{counter}{ext}"
                    counter += 1

            try:
                shutil.copy2(src, dst)
                copied += 1
                print(f"   ✓ {original['filename']}")
            except Exception as e:
                print(f"   ❌ Failed to copy {original['filename']}: {e}")

        print(f"\n✅ Copied {copied} original files")
        print(f"   {sum(len(dups) for _, dups in self.duplicates)} duplicates identified")


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Find duplicate audio files using audio fingerprinting'
    )
    parser.add_argument(
        '--input-dir',
        default='raw',
        help='Input directory with audio files (default: raw)'
    )
    parser.add_argument(
        '--output-dir',
        default='sorted',
        help='Output directory for original files (default: sorted)'
    )
    parser.add_argument(
        '--report',
        default='duplicates_report.csv',
        help='Output CSV report filename (default: duplicates_report.csv)'
    )
    parser.add_argument(
        '--no-copy',
        action='store_true',
        help='Generate report only, do not copy files'
    )

    args = parser.parse_args()

    print("🎵 Audio Duplicate Finder")
    print("=" * 60)

    # Check dependencies
    if not MUTAGEN_AVAILABLE:
        print("\n❌ Error: mutagen is required")
        print("   Install with: pip install mutagen")
        return

    if not ACOUSTID_AVAILABLE and not PYDUB_AVAILABLE:
        print("\n⚠️  Warning: No audio analysis libraries available")
        print("   For best results, install:")
        print("   pip install pyacoustid")
        print("   or")
        print("   pip install pydub scipy numpy")
        print("\n   Falling back to duration-only comparison (less accurate)")

    # Initialize finder
    finder = DuplicateFinder(args.input_dir, args.output_dir)

    # Find duplicates
    finder.find_duplicates()

    # Save report
    finder.save_report(args.report)

    # Copy originals unless --no-copy specified
    if not args.no_copy:
        finder.copy_originals()
    else:
        print("\n⚠️  Skipping file copy (--no-copy specified)")

    print("\n" + "=" * 60)
    print("✅ Done!")


if __name__ == '__main__':
    main()

# Made with Bob
