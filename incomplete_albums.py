#!/usr/bin/env python3
"""
incomplete_albums.py — find incomplete albums in a music library.

Scans a library (``album_artist/album/`` structure) and identifies albums that
appear incomplete via two complementary checks:

1. **Local gap check** — reads ``tracknumber`` tags (falls back to filename
   ``NN - …`` parsing) and looks for gaps in the sequence, or a count that
   differs from the embedded ``totaltracks`` tag.

2. **Online check (MusicBrainz)** — queries the public MB release API for the
   expected track count and compares with what is on disk.

Results are returned as plain dicts and can optionally be written to a JSON
file consumed by ``fetch_incomplete_on_streaming.py``.

Public API (importable from notebooks / other scripts)::

    from incomplete_albums import (
        scan_library_for_incomplete,
        check_local_completeness,
        check_online_completeness,
    )

CLI::

    python3 incomplete_albums.py --music-dir /Volumes/Music
    python3 incomplete_albums.py --music-dir /Volumes/Music --no-online
    python3 incomplete_albums.py --music-dir /Volumes/Music --output missing.json
"""

import re
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("Error: mutagen library not found. Install it with: pip install mutagen")
    sys.exit(1)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from music_library import AUDIO_EXTENSIONS, scan_albums_in_dir

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MusicBrainz public API — strictly ≤ 1 req/s per their ToS
MB_API_BASE = "https://musicbrainz.org/ws/2"
MB_HEADERS = {
    "User-Agent": "library-playlist-parser/1.0 (https://github.com/private)",
    "Accept": "application/json",
}


# ---------------------------------------------------------------------------
# Track-number helpers
# ---------------------------------------------------------------------------

def _parse_track_num(raw: str) -> Optional[int]:
    """Parse ``'3'``, ``'03'``, ``'3/12'``, ``'3 of 12'`` → integer track number."""
    if not raw:
        return None
    m = re.match(r'^(\d+)', raw.strip())
    return int(m.group(1)) if m else None


def _parse_total_tracks(raw: str) -> Optional[int]:
    """Parse total from ``'3/12'`` or a plain integer string."""
    if not raw:
        return None
    m = re.search(r'/\s*(\d+)', raw)
    if m:
        return int(m.group(1))
    m = re.match(r'^(\d+)$', raw.strip())
    return int(m.group(1)) if m else None


def _track_num_from_filename(name: str) -> Optional[int]:
    """
    Fallback: extract a leading track number from the filename.
    Handles patterns like ``'01 - …'``, ``'1 - …'``, ``'01. …'``, ``'01_…'``.
    """
    m = re.match(r'^(\d{1,3})\s*[-._\s]', name)
    return int(m.group(1)) if m else None


def extract_track_info(file_path: Path) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract ``(track_number, total_tracks)`` from a file's metadata tags.
    Falls back to filename parsing when tags are absent.

    Returns:
        ``(track_num, total_tracks)`` — either value may be ``None``.
    """
    try:
        audio = MutagenFile(str(file_path), easy=True)
        if audio and audio.tags:
            raw_track = (
                audio.get('tracknumber', [''])[0]
                if audio.get('tracknumber') else ''
            )
            track_num = _parse_track_num(raw_track)
            total = _parse_total_tracks(raw_track)

            if total is None:
                raw_total = (
                    audio.get('totaltracks', [''])[0]
                    if audio.get('totaltracks') else ''
                )
                total = _parse_total_tracks(raw_total)

            if track_num is None:
                track_num = _track_num_from_filename(file_path.name)

            return track_num, total
    except Exception:
        pass

    return _track_num_from_filename(file_path.name), None


def extract_album_artist_tag(file_path: Path) -> str:
    """Return the ``albumartist`` (or ``artist``) tag from a file."""
    try:
        audio = MutagenFile(str(file_path), easy=True)
        if audio and audio.tags:
            for key in ('albumartist', 'artist'):
                val = audio.get(key)
                if val:
                    return val[0].strip()
    except Exception:
        pass
    return ''


# ---------------------------------------------------------------------------
# Local gap detection
# ---------------------------------------------------------------------------

def check_local_completeness(
    album_dir: Path,
) -> Tuple[bool, str, List[int], Optional[int]]:
    """
    Scan all audio files in *album_dir* and report gaps in track numbering.

    Args:
        album_dir: Path to the album directory.

    Returns:
        ``(is_complete, reason, found_track_numbers, declared_total)``

        * ``is_complete`` – ``False`` if a gap or shortfall was detected.
        * ``reason`` – Human-readable explanation.
        * ``found_track_numbers`` – Sorted list of discovered track numbers.
        * ``declared_total`` – ``totaltracks`` value from tags, or ``None``.
    """
    audio_files = sorted(
        f for f in album_dir.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    )

    if not audio_files:
        return False, "No audio files found", [], None

    track_nums: List[int] = []
    declared_total: Optional[int] = None

    for f in audio_files:
        num, total = extract_track_info(f)
        if num is not None:
            track_nums.append(num)
        if total is not None and declared_total is None:
            declared_total = total

    if not track_nums:
        # Cannot determine track numbers at all — assume OK
        return True, "Track numbers unavailable", [], declared_total

    unique_tracks = sorted(set(track_nums))

    # Gap check: expected contiguous sequence from min to max
    expected = set(range(unique_tracks[0], unique_tracks[-1] + 1))
    gaps = sorted(expected - set(unique_tracks))
    if gaps:
        return (
            False,
            f"Gap(s) in track sequence: missing {gaps}",
            unique_tracks,
            declared_total,
        )

    # Count vs. declared total
    if declared_total is not None and len(unique_tracks) < declared_total:
        missing_count = declared_total - len(unique_tracks)
        return (
            False,
            f"Have {len(unique_tracks)}/{declared_total} tracks "
            f"({missing_count} missing)",
            unique_tracks,
            declared_total,
        )

    return True, "Complete (local check)", unique_tracks, declared_total


# ---------------------------------------------------------------------------
# MusicBrainz online check
# ---------------------------------------------------------------------------

def _mb_search_release(
    album_artist: str,
    album: str,
    session: "requests.Session",
) -> Optional[Dict]:
    """
    Search MusicBrainz for the best-matching release.

    Returns the first release dict, or ``None`` if nothing was found.
    Sleeps for ≥ 1 second before each request to respect MB's rate limit.
    """
    time.sleep(1.1)
    query = f'release:"{album}" AND artist:"{album_artist}"'
    params = {"query": query, "limit": 1, "fmt": "json"}
    try:
        resp = session.get(
            f"{MB_API_BASE}/release",
            params=params,
            headers=MB_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        releases = resp.json().get("releases", [])
        return releases[0] if releases else None
    except Exception as e:
        logger.debug(
            f"MusicBrainz search failed for '{album_artist} - {album}': {e}"
        )
    return None


def _mb_track_count(release_mbid: str, session: "requests.Session") -> Optional[int]:
    """Fetch total track count for a release by its MusicBrainz ID."""
    time.sleep(1.1)
    try:
        resp = session.get(
            f"{MB_API_BASE}/release/{release_mbid}",
            params={"inc": "recordings", "fmt": "json"},
            headers=MB_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        total = sum(
            m.get("track-count", 0)
            for m in resp.json().get("media", [])
        )
        return total or None
    except Exception as e:
        logger.debug(
            f"MusicBrainz release lookup failed for {release_mbid}: {e}"
        )
    return None


def check_online_completeness(
    album_artist: str,
    album: str,
    local_track_count: int,
    session: "requests.Session",
) -> Tuple[bool, str, Optional[int]]:
    """
    Query MusicBrainz and compare the expected track count with *local_track_count*.

    Args:
        album_artist:       Artist name used for the MB search query.
        album:              Album name used for the MB search query.
        local_track_count:  Number of tracks found on disk.
        session:            A :class:`requests.Session` instance.

    Returns:
        ``(is_complete, reason, mb_total_tracks)``
    """
    release = _mb_search_release(album_artist, album, session)
    if release is None:
        return True, "Not found on MusicBrainz (skipping online check)", None

    mbid = release.get("id")
    track_count_mb = _mb_track_count(mbid, session) if mbid else None

    if track_count_mb is None:
        return True, "MusicBrainz track count unavailable", None

    if local_track_count < track_count_mb:
        missing = track_count_mb - local_track_count
        return (
            False,
            f"MusicBrainz expects {track_count_mb} tracks; "
            f"have {local_track_count} ({missing} missing)",
            track_count_mb,
        )

    return (
        True,
        f"Complete ({local_track_count}/{track_count_mb} tracks)",
        track_count_mb,
    )


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

def scan_library_for_incomplete(
    music_dir: Path,
    online: bool = True,
    limit: Optional[int] = None,
) -> List[Dict]:
    """
    Walk *music_dir* and return a list of dicts describing incomplete albums.

    Each result dict contains:

    .. code-block:: python

        {
          "album_artist": str,
          "album":        str,
          "album_dir":    str,           # absolute path
          "reason":       str,           # human-readable explanation
          "local_tracks": int,
          "declared_total": int | None,  # from tags
          "mb_total":     int | None,    # from MusicBrainz
          "check_source": "local" | "online" | "both",
        }

    Args:
        music_dir:  Root of the music library (``album_artist/album/`` layout).
        online:     When ``True``, also query MusicBrainz.  Requires *requests*.
        limit:      Stop after checking this many albums (useful for testing).

    Returns:
        List of incomplete-album dicts (empty when everything looks complete).
    """
    if online and not REQUESTS_AVAILABLE:
        logger.warning("requests not installed — online check disabled")
        online = False

    session = requests.Session() if online else None
    incomplete: List[Dict] = []
    checked = 0

    if not music_dir.exists():
        logger.error(f"Music directory does not exist: {music_dir}")
        return incomplete

    for album_artist, album_name, album_dir in scan_albums_in_dir(music_dir):
        checked += 1
        reasons: List[str] = []
        check_source: Optional[str] = None

        # -- Local gap check --
        local_ok, local_reason, track_nums, declared_total = \
            check_local_completeness(album_dir)

        if not local_ok:
            reasons.append(local_reason)
            check_source = "local"

        local_count = len(set(track_nums)) if track_nums else 0

        # -- Online check (MusicBrainz) --
        mb_total: Optional[int] = None
        if online and session is not None and local_count > 0:
            # Prefer the albumartist tag over the directory name
            sample = next(
                (f for f in album_dir.iterdir()
                 if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS),
                None,
            )
            tag_artist = extract_album_artist_tag(sample) if sample else ''
            query_artist = tag_artist or album_artist

            online_ok, online_reason, mb_total = check_online_completeness(
                query_artist, album_name, local_count, session
            )
            if not online_ok:
                reasons.append(online_reason)
                check_source = "both" if check_source else "online"

        if reasons:
            incomplete.append({
                "album_artist": album_artist,
                "album": album_name,
                "album_dir": str(album_dir),
                "reason": "; ".join(reasons),
                "local_tracks": local_count,
                "declared_total": declared_total,
                "mb_total": mb_total,
                "check_source": check_source or "local",
            })
            logger.warning(
                f"INCOMPLETE — {album_artist} / {album_name}: "
                + "; ".join(reasons)
            )
        else:
            logger.debug(f"OK — {album_artist} / {album_name}")

        if limit and checked >= limit:
            logger.info(f"Reached limit of {limit} albums")
            break

    logger.info(f"Checked {checked} albums — found {len(incomplete)} incomplete")
    return incomplete


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Find incomplete albums in a music library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--music-dir', default='E:/Music/',
                        help='Music library root directory (default: E:/Music/)')
    parser.add_argument('--output', default='incomplete_albums.json',
                        help='Output JSON file (default: incomplete_albums.json)')
    parser.add_argument('--no-online', action='store_true',
                        help='Disable MusicBrainz online check')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of albums to check (for testing)')
    args = parser.parse_args()

    music_dir = Path(args.music_dir)
    online = not args.no_online

    logger.info(f"Scanning: {music_dir}")
    logger.info(
        f"Online check (MusicBrainz): {'enabled' if online else 'disabled'}"
    )

    incomplete = scan_library_for_incomplete(
        music_dir, online=online, limit=args.limit
    )

    output_path = Path(args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(incomplete, f, indent=2, ensure_ascii=False)

    logger.info(f"Results written to: {output_path}")
    logger.info(f"Incomplete albums found: {len(incomplete)}")


if __name__ == '__main__':
    main()
