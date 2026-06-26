#!/usr/bin/env python3
"""
album_overlap.py — find albums with significant track overlap within each album artist.

Compares albums belonging to the same album artist and reports pairs whose
track overlap exceeds a configurable threshold.  Comparisons are intentionally
restricted to albums that share the same album-artist directory so that, e.g.,
a "greatest hits" compilation by Artist A is never compared with an album by
Artist B.

Reuses the existing ``MusicLibraryCache`` from ``playlist_matcher.py`` so the
persistent on-disk cache (``{music_dir}/.playlist_matcher_cache.json``) is
shared with the playlist matcher — scanning the library only happens once.

---
Track fingerprinting
--------------------
Each track is represented by a **fingerprint hash** built from:

  * ``title_norm``  — normalised title (already computed by MusicLibraryCache)
  * ``artist_norm`` — normalised track artist (already computed)
  * ``duration_bucket`` — track duration rounded to the nearest 5 seconds
    (tolerates slight re-masters that changed the exact length)

Fallback fingerprint (when title is empty) uses the filename stem normalised
to lowercase.

Two tracks are considered the *same* when their hashes match.  An album is
represented as the **set** of its track hashes; overlap is computed as the
Jaccard index of those sets::

    overlap = |A ∩ B| / |A ∪ B|

---
Public API
----------
::

    from album_overlap import find_overlapping_albums, build_track_fingerprints

CLI::

    python3 album_overlap.py --music-dir /Volumes/Music --threshold 0.5
    python3 album_overlap.py --music-dir /Volumes/Music --threshold 0.3 \\
        --output overlaps.json --no-cache
"""

import hashlib
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

try:
    from mutagen import File as MutagenFile
except ImportError:
    print("Error: mutagen library not found.  Install with: pip install mutagen")
    sys.exit(1)

# Reuse the existing cache + normaliser from playlist_matcher
from playlist_matcher import MusicLibraryCache

from music_library import AUDIO_EXTENSIONS, scan_albums_in_dir

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Duration is bucketed to this many seconds so minor re-master length
# differences don't break the match.
DURATION_BUCKET_SECONDS: int = 5


# ---------------------------------------------------------------------------
# Track duration helper
# ---------------------------------------------------------------------------

def get_duration(file_path: Path) -> Optional[float]:
    """
    Return the duration in seconds of *file_path*, or ``None`` on failure.

    Uses ``audio.info.length`` which mutagen exposes for all common formats.
    """
    try:
        audio = MutagenFile(str(file_path))
        if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
            return float(audio.info.length)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Track fingerprint
# ---------------------------------------------------------------------------

def _bucket(seconds: Optional[float], bucket: int = DURATION_BUCKET_SECONDS) -> int:
    """Round *seconds* to the nearest *bucket*-second boundary."""
    if seconds is None:
        return 0
    return round(seconds / bucket) * bucket


def make_track_fingerprint(
    title_norm: str,
    artist_norm: str,
    duration_seconds: Optional[float],
    filename_stem: str = "",
    duration_bucket: int = DURATION_BUCKET_SECONDS,
) -> str:
    """
    Return a short hex hash that represents a single track.

    The hash is built from ``(title_norm, artist_norm, duration_bucket)``.
    When *title_norm* is empty the *filename_stem* (lowercased) is used
    as a fallback so that files without tags still get a stable fingerprint.

    Args:
        title_norm:       Normalised track title (from ``MusicLibraryCache``).
        artist_norm:      Normalised track artist (from ``MusicLibraryCache``).
        duration_seconds: Raw duration; will be bucketed internally.
        filename_stem:    Filename without extension — used when title is absent.
        duration_bucket:  Bucket size in seconds (default 5).

    Returns:
        8-character hex string (truncated MD5).
    """
    effective_title = title_norm or filename_stem.lower().strip()
    dur = _bucket(duration_seconds, duration_bucket)
    raw = f"{effective_title}|{artist_norm}|{dur}"
    return hashlib.md5(raw.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Album fingerprint set builder
# ---------------------------------------------------------------------------

def build_track_fingerprints(
    album_dir: Path,
    cache: MusicLibraryCache,
    duration_bucket: int = DURATION_BUCKET_SECONDS,
) -> FrozenSet[str]:
    """
    Return the set of track fingerprint hashes for all audio files in *album_dir*.

    Metadata is pulled from *cache* when available (free lookup); duration is
    read on-demand from the file because ``MusicLibraryCache`` does not store
    it.  The cache is never modified by this function.

    Args:
        album_dir:       Path to the album directory.
        cache:           A populated :class:`~playlist_matcher.MusicLibraryCache`.
        duration_bucket: Bucket size passed to :func:`make_track_fingerprint`.

    Returns:
        Frozen set of fingerprint hex strings (one per unique track).
    """
    hashes = set()

    for f in sorted(album_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        # Pull cached metadata (already normalised)
        cached = cache.cache.get(str(f))
        if cached:
            title_norm  = cached.get('title_norm', '')
            artist_norm = cached.get('artist_norm', '')
        else:
            # File not in cache (e.g. recently added) — extract on the fly
            meta = cache.extract_metadata(f)
            title_norm  = meta['title_norm']  if meta else ''
            artist_norm = meta['artist_norm'] if meta else ''

        duration = get_duration(f)
        fp = make_track_fingerprint(
            title_norm, artist_norm, duration, f.stem, duration_bucket
        )
        hashes.add(fp)

    return frozenset(hashes)


# ---------------------------------------------------------------------------
# Jaccard overlap
# ---------------------------------------------------------------------------

def jaccard(a: FrozenSet, b: FrozenSet) -> float:
    """Return the Jaccard similarity of two sets (0.0 – 1.0)."""
    if not a and not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# Main comparison engine
# ---------------------------------------------------------------------------

def find_overlapping_albums(
    music_dir: Path,
    threshold: float = 0.5,
    cache_file: Optional[Path] = None,
    use_cache: bool = True,
    force_rebuild: bool = False,
    duration_bucket: int = DURATION_BUCKET_SECONDS,
) -> List[Dict]:
    """
    Find album pairs within each album artist whose track overlap meets or
    exceeds *threshold*.

    Albums are compared only within the same album-artist directory — no
    cross-artist comparisons are made.

    Args:
        music_dir:      Root of the music library (``album_artist/album/`` layout).
        threshold:      Minimum Jaccard overlap to report (0.0 – 1.0).
        cache_file:     Override the default cache file path.
        use_cache:      Load / save the ``MusicLibraryCache`` on disk.
        force_rebuild:  Ignore any existing cache and rebuild from scratch.
        duration_bucket: Bucket size in seconds for duration comparison.

    Returns:
        List of dicts sorted by descending overlap, each containing:

        .. code-block:: python

            {
              "album_artist":  str,
              "album_a":       str,
              "album_b":       str,
              "overlap":       float,      # Jaccard score 0.0–1.0
              "common_tracks": int,        # |A ∩ B|
              "total_tracks":  int,        # |A ∪ B|
              "tracks_a":      int,
              "tracks_b":      int,
            }
    """
    # ── Build / load library cache ────────────────────────────────────────
    lib_cache = MusicLibraryCache(str(music_dir), str(cache_file) if cache_file else None)

    if use_cache and not force_rebuild:
        loaded = lib_cache.load_cache()
    else:
        loaded = False

    if not loaded:
        lib_cache.build_cache()
        if use_cache:
            lib_cache.save_cache()

    # ── Group albums by album artist ──────────────────────────────────────
    # { artist_dir_name -> [(album_name, album_dir), ...] }
    artist_albums: Dict[str, List[Tuple[str, Path]]] = defaultdict(list)

    for artist_name, album_name, album_dir in scan_albums_in_dir(music_dir):
        artist_albums[artist_name].append((album_name, album_dir))

    # ── Compare album pairs within each artist ────────────────────────────
    results: List[Dict] = []

    for artist_name, albums in sorted(artist_albums.items()):
        if len(albums) < 2:
            continue  # nothing to compare

        logger.debug(f"Comparing {len(albums)} albums for: {artist_name}")

        # Build fingerprint set once per album (cache the set, not the cache)
        fp_cache: Dict[str, FrozenSet[str]] = {}
        for album_name, album_dir in albums:
            fp_cache[album_name] = build_track_fingerprints(
                album_dir, lib_cache, duration_bucket
            )

        # All unique pairs
        for i in range(len(albums)):
            for j in range(i + 1, len(albums)):
                name_a, _ = albums[i]
                name_b, _ = albums[j]
                fps_a = fp_cache[name_a]
                fps_b = fp_cache[name_b]

                if not fps_a or not fps_b:
                    continue

                score = jaccard(fps_a, fps_b)
                if score >= threshold:
                    common = len(fps_a & fps_b)
                    total  = len(fps_a | fps_b)
                    results.append({
                        "album_artist":  artist_name,
                        "album_a":       name_a,
                        "album_b":       name_b,
                        "overlap":       round(score, 4),
                        "common_tracks": common,
                        "total_tracks":  total,
                        "tracks_a":      len(fps_a),
                        "tracks_b":      len(fps_b),
                    })
                    logger.info(
                        f"  {artist_name} | {name_a!r} ↔ {name_b!r}: "
                        f"{score:.0%} overlap ({common}/{total} tracks)"
                    )

    results.sort(key=lambda r: r["overlap"], reverse=True)
    logger.info(
        f"Done — checked {sum(len(v) for v in artist_albums.values())} albums "
        f"across {len(artist_albums)} artists, "
        f"found {len(results)} overlapping pair(s)"
    )
    return results


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def write_text_report(results: List[Dict], output_path: Path):
    """Write *results* as a human-readable text file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("Album Overlap Report\n")
        f.write("=" * 70 + "\n\n")
        for r in results:
            pct = f"{r['overlap']:.0%}"
            f.write(
                f"{r['album_artist']}\n"
                f"  {r['album_a']!r}\n"
                f"  {r['album_b']!r}\n"
                f"  overlap: {pct}  "
                f"({r['common_tracks']} common / {r['total_tracks']} unique tracks, "
                f"A={r['tracks_a']}  B={r['tracks_b']})\n\n"
            )
    logger.info(f"Text report written to: {output_path}")


def write_json_report(results: List[Dict], output_path: Path):
    """Write *results* as a machine-readable JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"JSON report written to: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Find albums with significant track overlap within each album artist."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--music-dir', default='E:/Music/',
                        help='Music library root directory (default: E:/Music/)')
    parser.add_argument('--threshold', type=float, default=0.5,
                        help='Minimum overlap fraction to report, 0.0–1.0 '
                             '(default: 0.5 = 50%%)')
    parser.add_argument('--output', default=None,
                        help='Text report output path (default: stdout summary only)')
    parser.add_argument('--json-output', default=None,
                        help='JSON report output path')
    parser.add_argument('--cache-file', default=None,
                        help='Override default cache file path')
    parser.add_argument('--no-cache', action='store_true',
                        help='Disable loading/saving the library cache')
    parser.add_argument('--rebuild-cache', action='store_true',
                        help='Force-rebuild the library cache')
    parser.add_argument('--duration-bucket', type=int, default=DURATION_BUCKET_SECONDS,
                        help=f'Duration bucket size in seconds '
                             f'(default: {DURATION_BUCKET_SECONDS})')
    args = parser.parse_args()

    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0.0 and 1.0")

    results = find_overlapping_albums(
        music_dir=Path(args.music_dir),
        threshold=args.threshold,
        cache_file=Path(args.cache_file) if args.cache_file else None,
        use_cache=not args.no_cache,
        force_rebuild=args.rebuild_cache,
        duration_bucket=args.duration_bucket,
    )

    print(f"\nFound {len(results)} album pair(s) with ≥{args.threshold:.0%} overlap\n")
    for r in results:
        print(
            f"  [{r['overlap']:.0%}] {r['album_artist']} — "
            f"{r['album_a']!r} ↔ {r['album_b']!r}  "
            f"({r['common_tracks']}/{r['total_tracks']} tracks)"
        )

    if args.output:
        write_text_report(results, Path(args.output))
    if args.json_output:
        write_json_report(results, Path(args.json_output))


if __name__ == '__main__':
    main()
