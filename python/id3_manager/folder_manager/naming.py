"""Naming helpers and rename operations for FolderManager."""

import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

from models import AudioFile
from sync_results import CommitResult
from folder_manager.protocols import RenameCoordinator


def sanitize_name(name: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "_")
    name = re.sub(r"[_\s]+", " ", name)
    name = name.strip(". ")
    return unicodedata.normalize("NFC", name)


def generate_folder_name(year: int, album_name: str) -> str:
    return f"{year} - {sanitize_name(album_name)}"


def generate_disc_folder_name(disc_number: int) -> str:
    return f"CD{disc_number}"


def generate_filename(metadata, extension: str) -> Optional[str]:
    if not all(
        [metadata.artist, metadata.album, metadata.track_number, metadata.title]
    ):
        return None
    artist = sanitize_name(metadata.artist)
    album = sanitize_name(metadata.album)
    title = sanitize_name(metadata.title)
    track_num = f"{metadata.track_number:02d}"
    if metadata.disc_number and (metadata.total_discs and metadata.total_discs > 1):
        album_part = f"{album} CD{metadata.disc_number}"
    else:
        album_part = album
    return f"{artist} - {album_part} - {track_num} - {title}{extension}"


def parse_folder_name(
    folder_path: str, pattern: str
) -> Tuple[Optional[int], Optional[str]]:
    folder_name = Path(folder_path).name
    match = re.match(pattern, folder_name)
    if match:
        return int(match.group(1)), match.group(2).strip()
    return None, None


def is_folder_properly_named(folder_path: str, pattern: str) -> bool:
    return bool(re.match(pattern, Path(folder_path).name))


def get_album_info_from_files(
    audio_files: List[AudioFile],
) -> Tuple[Optional[int], Optional[str]]:
    year = None
    album = None
    for af in audio_files:
        tags = af.proposed_tags or af.current_tags
        if tags.year and not year:
            year = tags.year
        if tags.album and not album:
            album = tags.album
        if year and album:
            break
    return year, album


def should_rename_file(current_path: str, metadata) -> bool:
    extension = Path(current_path).suffix.lower()
    expected_filename = generate_filename(metadata, extension)
    if expected_filename is None:
        return False
    return Path(current_path).name != expected_filename


def rename_folder(
    renamer: RenameCoordinator, current_path: str, new_name: str, dry_run: bool = False
) -> CommitResult:
    current = Path(current_path)
    new_path = current.parent / new_name

    if new_path.exists():
        return CommitResult(
            success=False, message=f"Target folder already exists: {new_path}"
        )

    if current.name == new_name:
        return CommitResult(success=True, message="Folder already has correct name")

    mirror = renamer.mirror_rename(current, new_path, dry_run, allow_recovery=False)
    if not mirror.success:
        return CommitResult(
            success=False, message=f"Remote rename failed: {mirror.message}"
        )

    if dry_run:
        return CommitResult(success=True, message=f"Would rename to: {new_path}")

    return renamer.commit_with_rollback(
        current, new_path, lambda: current.rename(new_path), mirror_result=mirror
    )


def rename_audio_file(
    renamer: RenameCoordinator, file_path: str, new_name: str, dry_run: bool = False
) -> CommitResult:
    current = Path(file_path)
    new_path = current.parent / new_name

    if new_path.exists() and new_path != current:
        return CommitResult(
            success=False, message=f"Target file already exists: {new_path}"
        )

    if current.name == new_name:
        return CommitResult(success=True, message="File already has correct name")

    mirror = renamer.mirror_rename(current, new_path, dry_run)
    if not mirror.success:
        return CommitResult(
            success=False, message=f"Remote rename failed: {mirror.message}"
        )

    if dry_run:
        return CommitResult(success=True, message=f"Would rename to: {new_name}")

    return renamer.commit_with_rollback(
        current, new_path, lambda: current.rename(new_path), mirror_result=mirror
    )
