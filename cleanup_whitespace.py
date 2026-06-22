#!/usr/bin/env python3
"""
Cleanup whitespace in repository files.
- Removes trailing whitespace from all lines
- Converts tabs to spaces (1 tab = 4 spaces)
- Ensures files end with a single newline
"""

import os
import sys
from pathlib import Path


def should_process_file(filepath: Path) -> bool:
    """Determine if a file should be processed."""
    # Skip binary files and certain directories
    skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'env',
                 'htmlcov', '.pytest_cache', '.coverage', 'test_music_library'}
    skip_extensions = {'.pyc', '.pyo', '.so', '.dylib', '.dll', '.exe',
                      '.jpg', '.jpeg', '.png', '.gif', '.ico', '.pdf',
                      '.flac', '.mp3', '.m4a', '.wav', '.ogg', '.aac',
                      '.zip', '.tar', '.gz', '.bz2', '.xz',
                      '.db', '.sqlite', '.sqlite3'}

    # Check if file is in a skip directory
    for part in filepath.parts:
        if part in skip_dirs:
            return False

    # Check file extension
    if filepath.suffix.lower() in skip_extensions:
        return False

    # Check if it's a hidden file (except .gitignore, .cursorrules, etc.)
    if filepath.name.startswith('.') and filepath.suffix not in {'.md', '.txt', '.json', '.yml', '.yaml'}:
        if filepath.name not in {'.gitignore', '.cursorrules', '.roorules'}:
            return False

    return True


def cleanup_file(filepath: Path, dry_run: bool = False) -> tuple[bool, int, int]:
    """
    Clean up whitespace in a file.

    Returns:
        (changed, lines_modified, tabs_converted)
    """
    try:
        # Try to read as text
        with open(filepath, 'r', encoding='utf-8', errors='strict') as f:
            original_content = f.read()
    except (UnicodeDecodeError, PermissionError):
        # Skip binary files or files we can't read
        return False, 0, 0

    lines = original_content.splitlines(keepends=True)
    modified_lines = []
    lines_changed = 0
    tabs_converted = 0

    for line in lines:
        original_line = line

        # Convert tabs to spaces (1 tab = 4 spaces)
        if '\t' in line:
            tabs_in_line = line.count('\t')
            line = line.replace('\t', '    ')
            tabs_converted += tabs_in_line

        # Remove trailing whitespace (but keep newline)
        if line.endswith('\n'):
            stripped = line.rstrip() + '\n'
        else:
            stripped = line.rstrip()

        if stripped != original_line:
            lines_changed += 1

        modified_lines.append(stripped)

    new_content = ''.join(modified_lines)

    # Ensure file ends with single newline if it's not empty
    if new_content and not new_content.endswith('\n'):
        new_content += '\n'
        lines_changed += 1

    # Check if anything changed
    changed = new_content != original_content

    if changed and not dry_run:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

    return changed, lines_changed, tabs_converted


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Clean up whitespace in repository files'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without modifying files'
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Show all files processed'
    )

    args = parser.parse_args()

    # Get repository root
    repo_root = Path(__file__).parent

    print("🧹 Whitespace Cleanup Tool")
    print("=" * 70)
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified")
        print("=" * 70)

    # Collect all files
    all_files = []
    for root, dirs, files in os.walk(repo_root):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.') or d in {'.bob'}]

        for filename in files:
            filepath = Path(root) / filename
            if should_process_file(filepath):
                all_files.append(filepath)

    print(f"\nFound {len(all_files)} files to process\n")

    # Process files
    total_changed = 0
    total_lines_modified = 0
    total_tabs_converted = 0
    changed_files = []

    for filepath in sorted(all_files):
        changed, lines_modified, tabs_converted = cleanup_file(filepath, args.dry_run)

        if changed:
            total_changed += 1
            total_lines_modified += lines_modified
            total_tabs_converted += tabs_converted
            changed_files.append(filepath)

            rel_path = filepath.relative_to(repo_root)
            status = "Would modify" if args.dry_run else "Modified"
            print(f"  {status}: {rel_path}")
            if lines_modified > 0 or tabs_converted > 0:
                details = []
                if lines_modified > 0:
                    details.append(f"{lines_modified} lines")
                if tabs_converted > 0:
                    details.append(f"{tabs_converted} tabs")
                print(f"    ({', '.join(details)})")
        elif args.verbose:
            rel_path = filepath.relative_to(repo_root)
            print(f"  No changes: {rel_path}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files processed: {len(all_files)}")
    print(f"Files {'that would be ' if args.dry_run else ''}modified: {total_changed}")
    print(f"Total lines modified: {total_lines_modified}")
    print(f"Total tabs converted: {total_tabs_converted}")

    if args.dry_run and total_changed > 0:
        print("\nRun without --dry-run to apply changes")
    elif total_changed > 0:
        print("\n✅ Whitespace cleanup complete!")
    else:
        print("\n✅ No changes needed - repository is clean!")

    print("=" * 70)


if __name__ == '__main__':
    main()
