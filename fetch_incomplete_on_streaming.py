#!/usr/bin/env python3
"""
fetch_incomplete_on_streaming.py — search incomplete albums on streaming services.

Reads the JSON produced by ``incomplete_albums.py`` and searches each album
across all streaming services using :class:`~find_albums_on_streaming.StreamingSearcher`.

Results are written as a human-readable ``.txt`` report and a machine-readable
``.json`` report so you can review which albums to download.

Public API (importable from notebooks / other scripts)::

    from fetch_incomplete_on_streaming import (
        load_incomplete_albums,
        search_albums_on_streaming,
        write_text_report,
        write_json_report,
    )

CLI::

    python3 fetch_incomplete_on_streaming.py
    python3 fetch_incomplete_on_streaming.py --input incomplete_albums.json
    python3 fetch_incomplete_on_streaming.py --input incomplete_albums.json \\
        --output streaming_incomplete.txt \\
        --json-output streaming_incomplete.json
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Reuse StreamingSearcher directly from find_albums_on_streaming.py
try:
    from find_albums_on_streaming import StreamingSearcher
except ImportError:
    print(
        "Error: find_albums_on_streaming.py not found in the same directory."
    )
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def load_incomplete_albums(input_path: Path) -> List[Dict]:
    """
    Load the incomplete-albums list produced by :func:`incomplete_albums.scan_library_for_incomplete`.

    Args:
        input_path: Path to the JSON file.

    Returns:
        List of album dicts, or an empty list when the file is missing.
    """
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return []

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    logger.info(f"Loaded {len(data)} incomplete album(s) from {input_path}")
    return data


def search_albums_on_streaming(
    albums: List[Dict],
    searcher: Optional["StreamingSearcher"] = None,
    limit: Optional[int] = None,
) -> List[Dict]:
    """
    Search each incomplete album across all streaming services.

    Each result dict contains all fields from the input plus a ``"streaming"``
    key that maps service names to URLs (or ``None`` when not found)::

        {
          "album_artist":   str,
          "album":          str,
          "reason":         str,
          "local_tracks":   int,
          "declared_total": int | None,
          "mb_total":       int | None,
          "check_source":   str,
          "streaming": {
            "deezer":       str | None,
            "spotify":      str | None,
            "apple_music":  str | None,
            "tidal":        str | None,
            "qobuz":        str | None,
            "amazon_music": str | None,
          }
        }

    Args:
        albums:   List of incomplete-album dicts (from :func:`load_incomplete_albums`
                  or directly from :func:`incomplete_albums.scan_library_for_incomplete`).
        searcher: Optional :class:`~find_albums_on_streaming.StreamingSearcher`
                  instance.  A new one (with credentials from ``streaming_config.json``)
                  is created when ``None``.
        limit:    Process at most this many albums (for testing).

    Returns:
        List of result dicts, one per album searched.
    """
    if searcher is None:
        searcher = StreamingSearcher()

    if limit:
        albums = albums[:limit]
        logger.info(f"Limited to {limit} albums")

    results: List[Dict] = []
    total = len(albums)

    for i, entry in enumerate(albums, 1):
        album_artist = entry.get("album_artist", "")
        album = entry.get("album", "")

        logger.info(f"[{i}/{total}] Searching: {album_artist} — {album}")

        streaming_links = searcher.search_all_services(album_artist, album)

        result = {
            "album_artist":   album_artist,
            "album":          album,
            "reason":         entry.get("reason", ""),
            "local_tracks":   entry.get("local_tracks", 0),
            "declared_total": entry.get("declared_total"),
            "mb_total":       entry.get("mb_total"),
            "check_source":   entry.get("check_source", "local"),
            "streaming":      streaming_links,
        }
        results.append(result)

        for service, url in streaming_links.items():
            if url:
                logger.info(f"  ✓ {service}: {url}")
            else:
                logger.debug(f"  ✗ {service}: not found")

    return results


def write_text_report(results: List[Dict], output_path: Path):
    """
    Write *results* as a human-readable text file.

    Args:
        results:     List produced by :func:`search_albums_on_streaming`.
        output_path: Destination ``.txt`` file.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("Incomplete Albums — Streaming Links\n")
        f.write("=" * 70 + "\n\n")

        for entry in results:
            f.write(f"{entry['album_artist']} — {entry['album']}\n")
            f.write(f"  Reason : {entry['reason']}\n")

            local = entry.get("local_tracks", 0)
            mb = entry.get("mb_total")
            declared = entry.get("declared_total")
            if mb:
                f.write(f"  Tracks : {local} on disk / {mb} on MusicBrainz\n")
            elif declared:
                f.write(
                    f"  Tracks : {local} on disk / {declared} declared in tags\n"
                )
            else:
                f.write(f"  Tracks : {local} on disk\n")

            f.write("  Streaming links:\n")
            streaming = entry.get("streaming", {})
            any_found = False
            for service, url in streaming.items():
                if url:
                    f.write(f"    {service:<15} {url}\n")
                    any_found = True
            if not any_found:
                f.write("    (no streaming links found)\n")
            f.write("\n")

    logger.info(f"Text report written to: {output_path}")


def write_json_report(results: List[Dict], output_path: Path):
    """
    Write *results* as a machine-readable JSON file.

    Args:
        results:     List produced by :func:`search_albums_on_streaming`.
        output_path: Destination ``.json`` file.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"JSON report written to: {output_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Search incomplete albums (from incomplete_albums.py) "
            "on streaming services."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--input', default='incomplete_albums.json',
                        help='Incomplete albums JSON file '
                             '(default: incomplete_albums.json)')
    parser.add_argument('--output', default='streaming_incomplete.txt',
                        help='Output text report '
                             '(default: streaming_incomplete.txt)')
    parser.add_argument('--json-output', default='streaming_incomplete.json',
                        help='Output JSON report '
                             '(default: streaming_incomplete.json)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of albums to search (for testing)')
    args = parser.parse_args()

    albums = load_incomplete_albums(Path(args.input))
    if not albums:
        logger.info("No incomplete albums to search.")
        return

    results = search_albums_on_streaming(albums, limit=args.limit)

    write_text_report(results, Path(args.output))
    write_json_report(results, Path(args.json_output))

    found_any = sum(
        1 for r in results if any(u for u in r.get("streaming", {}).values())
    )
    logger.info(
        f"Done — {len(results)} albums searched, "
        f"{found_any} found on at least one streaming service"
    )


if __name__ == '__main__':
    main()
