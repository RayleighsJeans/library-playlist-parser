#!/usr/bin/env python3
"""
music_library.py — shared helpers used across all music-library tools.

Provides:
  - AUDIO_EXTENSIONS: set of recognised audio file suffixes
  - scan_albums_in_dir(music_dir): yield (album_artist_name, album_name, album_dir)
  - scan_album_dirs(music_dir): dict { artist_key -> { album_key -> Path } }
  - normalise(name): lowercase+strip for case-insensitive comparisons
"""

from pathlib import Path
from typing import Dict, Generator, Tuple

AUDIO_EXTENSIONS: frozenset = frozenset({
    '.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wma', '.aac', '.wav'
})


def normalise(name: str) -> str:
    """Lowercase + strip for case-insensitive name comparisons."""
    return name.strip().lower()


def scan_albums_in_dir(
    music_dir: Path,
) -> Generator[Tuple[str, str, Path], None, None]:
    """
    Yield ``(album_artist_name, album_name, album_dir)`` for every album
    directory that contains at least one recognised audio file.

    Expected structure::

        music_dir/
          <Album Artist>/
            <Album>/
              track files…

    Args:
        music_dir: Root path of the music library.

    Yields:
        (album_artist_name, album_name, album_dir_path) tuples.
    """
    if not music_dir.exists() or not music_dir.is_dir():
        return

    for artist_dir in sorted(music_dir.iterdir()):
        if not artist_dir.is_dir():
            continue

        for album_dir in sorted(artist_dir.iterdir()):
            if not album_dir.is_dir():
                continue

            has_audio = any(
                f.suffix.lower() in AUDIO_EXTENSIONS
                for f in album_dir.iterdir()
                if f.is_file()
            )

            if has_audio:
                yield artist_dir.name, album_dir.name, album_dir


def scan_album_dirs(
    music_dir: Path,
) -> Dict[str, Dict[str, Path]]:
    """
    Scan a music library and return a nested case-insensitive mapping.

    Returns:
        ``{ normalised_artist -> { normalised_album -> album_dir_path } }``

    This is the dict form of :func:`scan_albums_in_dir`, useful when you need
    fast membership tests (e.g. diff two libraries).

    Args:
        music_dir: Root path of the music library.
    """
    result: Dict[str, Dict[str, Path]] = {}
    for artist_name, album_name, album_dir in scan_albums_in_dir(music_dir):
        artist_key = normalise(artist_name)
        album_key = normalise(album_name)
        result.setdefault(artist_key, {})[album_key] = album_dir
    return result
