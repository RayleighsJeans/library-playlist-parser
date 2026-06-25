#!/usr/bin/env python3
"""
library_diff.py — compare two music libraries and transfer surplus albums.

Compares two libraries structured as ``album_artist/album/`` and identifies
albums that are present in the *source* library but absent from the *reference*
library.  The surplus albums can then be moved or copied to a dedicated
output location.

Public API (importable from notebooks / other scripts)::

    from library_diff import find_surplus, transfer_surplus, scan_library

CLI::

    python3 library_diff.py --source /Volumes/Music \\
                             --reference /Volumes/MainMusic \\
                             --output /Volumes/Surplus
    python3 library_diff.py --source ... --reference ... --dry-run
    python3 library_diff.py --source ... --reference ... --report-only
"""

import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from music_library import normalise, scan_album_dirs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def scan_library(music_dir: Path) -> Dict[str, Dict[str, Path]]:
    """
    Scan *music_dir* and return ``{ normalised_artist -> { normalised_album -> Path } }``.

    This is a thin wrapper around :func:`music_library.scan_album_dirs` that
    also logs a summary line, making it more convenient when called
    interactively from a notebook.

    Args:
        music_dir: Root directory of the music library.

    Returns:
        Nested dict mapping normalised artist key → normalised album key → album directory.
    """
    result = scan_album_dirs(music_dir)
    if not music_dir.exists():
        logger.error(f"Directory does not exist: {music_dir}")
    else:
        n_artists = len(result)
        n_albums = sum(len(v) for v in result.values())
        logger.info(f"Scanned {music_dir}: {n_artists} artists, {n_albums} albums")
    return result


def find_surplus(
    source: Dict[str, Dict[str, Path]],
    reference: Dict[str, Dict[str, Path]],
) -> List[Path]:
    """
    Return album directories that are in *source* but not in *reference*.

    Comparison is case-insensitive (both dicts use :func:`music_library.normalise`
    keys).  An album is "surplus" when its (artist, album) pair is absent from
    the reference, regardless of whether the artist itself exists there.

    Args:
        source:    Index produced by :func:`scan_library` for the surplus library.
        reference: Index produced by :func:`scan_library` for the main library.

    Returns:
        Sorted list of :class:`pathlib.Path` objects pointing at surplus album directories.
    """
    surplus: List[Path] = []
    for artist_key, albums in source.items():
        ref_albums = reference.get(artist_key, {})
        for album_key, album_path in albums.items():
            if album_key not in ref_albums:
                surplus.append(album_path)

    surplus.sort(key=lambda p: str(p).lower())
    return surplus


def transfer_surplus(
    surplus_albums: List[Path],
    source_root: Path,
    destination: Path,
    move: bool = True,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    Copy or move surplus album directories to *destination*, preserving the
    ``artist/album`` sub-directory structure relative to *source_root*.

    Args:
        surplus_albums: List of album paths (as returned by :func:`find_surplus`).
        source_root:    Root of the source library (used to compute relative paths).
        destination:    Target root directory.
        move:           ``True`` to move (default), ``False`` to copy.
        dry_run:        When ``True``, log planned operations but make no changes.

    Returns:
        ``(success_count, failure_count)``
    """
    success = 0
    failure = 0

    for album_path in surplus_albums:
        try:
            rel = album_path.relative_to(source_root)
        except ValueError:
            logger.error(
                f"Album path {album_path} is not under source root {source_root}"
            )
            failure += 1
            continue

        dest_path = destination / rel
        action = "move" if move else "copy"

        if dry_run:
            logger.info(f"[DRY RUN] Would {action}: {album_path} -> {dest_path}")
            success += 1
            continue

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if move:
                shutil.move(str(album_path), str(dest_path))
            else:
                shutil.copytree(str(album_path), str(dest_path))
            logger.info(f"{action.capitalize()}d: {rel}")
            success += 1
        except Exception as e:
            logger.error(f"Failed to {action} {album_path}: {e}")
            failure += 1

    return success, failure


def build_diff_report(
    surplus_albums: List[Path],
    source_root: Path,
    reference_root: Path,
    destination: Optional[Path],
    move: bool,
    dry_run: bool,
) -> dict:
    """
    Build a dictionary report describing the diff result.

    This is the data that :func:`write_report` serialises to JSON, and that
    notebooks can inspect directly without touching the filesystem.

    Returns:
        Plain dict with keys: ``source``, ``reference``, ``destination``,
        ``action``, ``dry_run``, ``surplus_count``, ``surplus_albums``.
    """
    return {
        "source": str(source_root),
        "reference": str(reference_root),
        "destination": str(destination) if destination else None,
        "action": "move" if move else "copy",
        "dry_run": dry_run,
        "surplus_count": len(surplus_albums),
        "surplus_albums": [
            str(p.relative_to(source_root)) for p in surplus_albums
        ],
    }


def write_report(
    surplus_albums: List[Path],
    source_root: Path,
    reference_root: Path,
    destination: Optional[Path],
    move: bool,
    dry_run: bool,
    report_file: Optional[Path],
):
    """
    Serialise the diff report to *report_file* as JSON, or print to stdout
    when *report_file* is ``None``.
    """
    report = build_diff_report(
        surplus_albums, source_root, reference_root, destination, move, dry_run
    )
    if report_file:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Report written to: {report_file}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Find albums in source library that are absent from reference "
            "library, then optionally move/copy them to a destination."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--source', required=True,
                        help='Source music library root (the larger / surplus library)')
    parser.add_argument('--reference', required=True,
                        help='Reference music library root (the "main" library)')
    parser.add_argument('--output', default=None,
                        help='Destination directory for surplus albums. '
                             'Required unless --dry-run or --report-only is used.')
    parser.add_argument('--copy', action='store_true',
                        help='Copy files instead of moving them (default: move)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making any changes')
    parser.add_argument('--report-only', action='store_true',
                        help='Only print the diff report, do not transfer files')
    parser.add_argument('--report-file', default=None,
                        help='Write JSON report to this file (default: print to stdout)')
    args = parser.parse_args()

    source_root = Path(args.source)
    reference_root = Path(args.reference)
    destination = Path(args.output) if args.output else None
    move = not args.copy
    report_file = Path(args.report_file) if args.report_file else None

    if not args.dry_run and not args.report_only and destination is None:
        parser.error(
            "--output is required unless --dry-run or --report-only is specified"
        )

    logger.info(f"Scanning source library:    {source_root}")
    source_index = scan_library(source_root)

    logger.info(f"Scanning reference library: {reference_root}")
    reference_index = scan_library(reference_root)

    surplus = find_surplus(source_index, reference_index)
    logger.info(
        f"Found {len(surplus)} surplus album(s) in source not present in reference"
    )

    for album_path in surplus:
        try:
            rel = album_path.relative_to(source_root)
        except ValueError:
            rel = album_path
        logger.info(f"  Surplus: {rel}")

    write_report(surplus, source_root, reference_root, destination, move,
                 args.dry_run, report_file)

    if args.report_only or not destination:
        return

    success, failure = transfer_surplus(
        surplus_albums=surplus,
        source_root=source_root,
        destination=destination,
        move=move,
        dry_run=args.dry_run,
    )
    logger.info(f"Transfer complete — success: {success}, failures: {failure}")
    if failure:
        sys.exit(1)


if __name__ == '__main__':
    main()
