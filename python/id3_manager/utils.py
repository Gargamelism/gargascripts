"""Utility functions for ID3 Manager."""

import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import TrackMetadata


def sanitize_filename(s: str) -> str:
    """Sanitize a string for use in filenames."""
    s = re.sub(r'[<>:"/\\|?*]', '_', s)
    s = s.strip('. ')
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'_+', '_', s)
    return s


def generate_expected_filename(metadata: "TrackMetadata", extension: str) -> Optional[str]:
    """Generate expected filename from metadata.

    Args:
        metadata: Track metadata with title, artist, album, track_number
        extension: File extension including dot (e.g., '.mp3')

    Returns:
        Expected filename or None if required fields are missing
    """
    if not all([metadata.title, metadata.artist, metadata.album, metadata.track_number]):
        return None

    artist = sanitize_filename(metadata.artist)
    album = sanitize_filename(metadata.album)
    title = sanitize_filename(metadata.title)
    track_num = f"{metadata.track_number:02d}"

    if metadata.disc_number and metadata.total_discs and metadata.total_discs > 1:
        album_part = f"{album} CD{metadata.disc_number}"
    else:
        album_part = album

    return f"{artist} - {album_part} - {track_num} - {title}{extension}"


def file_needs_rename(file_path: str, metadata: "TrackMetadata") -> bool:
    """Check if file needs renaming based on metadata.

    Args:
        file_path: Path to the audio file
        metadata: Track metadata to compare against

    Returns:
        True if file needs renaming, False otherwise
    """
    current_name = Path(file_path).stem
    extension = Path(file_path).suffix
    expected = generate_expected_filename(metadata, extension)
    if expected is None:
        return False
    expected_stem = Path(expected).stem
    return current_name != expected_stem
