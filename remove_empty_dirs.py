#!/usr/bin/env python3
"""
Remove Empty Directories

Recursively walks a directory tree and removes all empty directories,
bottom-up (deepest first) so that removing a subdirectory can also
empty its parent, allowing that parent to be removed in the same pass.

Usage:
    python3 remove_empty_dirs.py /path/to/tree
    python3 remove_empty_dirs.py /path/to/tree --dry-run
    python3 remove_empty_dirs.py /path/to/tree --keep-root
"""

import sys
import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def remove_empty_dirs(
    root: Path,
    dry_run: bool = False,
    keep_root: bool = False,
) -> int:
    """
    Walk *root* bottom-up and delete every directory that is empty.

    A directory is considered empty when it contains no files and no
    non-empty sub-directories (after their own sub-trees have been pruned).

    Args:
        root:       The top-level path to start from.
        dry_run:    When True, log what would be removed but don't touch the fs.
        keep_root:  When True, never remove *root* itself even if it ends up empty.

    Returns:
        Number of directories removed (or that would be removed in dry-run mode).
    """
    if not root.exists():
        logger.error(f"Path does not exist: {root}")
        return 0

    if not root.is_dir():
        logger.error(f"Path is not a directory: {root}")
        return 0

    removed = 0

    # os.walk with topdown=False visits deepest directories first
    for dirpath_str, subdirs, files in __import__('os').walk(str(root), topdown=False):
        dirpath = Path(dirpath_str)

        # Skip root itself — handled separately below
        if dirpath == root:
            continue

        # A directory is empty when it has no files and no remaining subdirs
        try:
            contents = list(dirpath.iterdir())
        except PermissionError:
            logger.warning(f"Permission denied, skipping: {dirpath}")
            continue

        if not contents:
            if dry_run:
                logger.info(f"[DRY RUN] Would remove: {dirpath}")
            else:
                try:
                    dirpath.rmdir()
                    logger.info(f"Removed: {dirpath}")
                except OSError as e:
                    logger.warning(f"Could not remove {dirpath}: {e}")
                    continue
            removed += 1

    # Optionally remove root if it is now empty
    if not keep_root:
        try:
            root_contents = list(root.iterdir())
        except PermissionError:
            logger.warning(f"Permission denied checking root: {root}")
            root_contents = [True]  # Treat as non-empty

        if not root_contents:
            if dry_run:
                logger.info(f"[DRY RUN] Would remove root: {root}")
            else:
                try:
                    root.rmdir()
                    logger.info(f"Removed root: {root}")
                except OSError as e:
                    logger.warning(f"Could not remove root {root}: {e}")
                    return removed
            removed += 1

    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Recursively remove all empty directories under a path.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('path', help='Root directory to clean up')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be removed without deleting anything')
    parser.add_argument('--keep-root', action='store_true',
                        help='Do not remove the root directory itself, even if empty')
    args = parser.parse_args()

    root = Path(args.path)
    count = remove_empty_dirs(root, dry_run=args.dry_run, keep_root=args.keep_root)

    verb = "Would remove" if args.dry_run else "Removed"
    logger.info(f"{verb} {count} empty director{'y' if count == 1 else 'ies'}")


if __name__ == '__main__':
    main()
