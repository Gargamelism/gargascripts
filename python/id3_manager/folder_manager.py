"""Folder management for multi-disc detection and renaming."""

import os
import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from config import eprint
from models import AlbumFolder, AudioFile


class FolderManager:
    """Manages folder detection, multi-disc detection, and renaming."""

    # Patterns for detecting disc folders
    DISC_PATTERNS = [
        r"(?:cd|disc|disk)\s*(\d+)",  # CD1, CD 1, Disc1, Disk 1
        r"^(\d+)$",                     # Just a number (subfolder named "1", "2")
        r"d(\d+)",                       # d1, d2
    ]

    # Pattern for properly formatted album folder
    ALBUM_FOLDER_PATTERN = r"^(\d{4})\s*-\s*(.+)$"

    def detect_multi_disc_structure(self, folder_path: str) -> List[AlbumFolder]:
        """
        Detect if folder contains multi-disc structure.

        Args:
            folder_path: Path to album folder

        Returns:
            List of AlbumFolder objects for each disc found
        """
        path = Path(folder_path)

        if not path.is_dir():
            return [AlbumFolder(folder_path=folder_path)]

        subfolders = [d for d in path.iterdir() if d.is_dir()]

        disc_folders = []
        for subfolder in subfolders:
            disc_num = self._extract_disc_number(subfolder.name)
            if disc_num is not None:
                disc_folders.append((disc_num, subfolder))

        if len(disc_folders) >= 2:
            # This is a multi-disc album
            disc_folders.sort(key=lambda x: x[0])
            return [
                AlbumFolder(
                    folder_path=str(sf),
                    detected_disc_number=num,
                    parent_folder=folder_path
                )
                for num, sf in disc_folders
            ]

        # Single disc or not a multi-disc structure
        return [AlbumFolder(folder_path=folder_path)]

    def _extract_disc_number(self, folder_name: str) -> Optional[int]:
        """Extract disc number from folder name."""
        folder_name_lower = folder_name.lower()
        for pattern in self.DISC_PATTERNS:
            match = re.search(pattern, folder_name_lower, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    def normalize_disc_folder_name(self, folder_path: str, disc_number: int,
                                   dry_run: bool = False) -> Tuple[bool, str]:
        """
        Normalize disc folder name to standard CD{N} format.

        Args:
            folder_path: Path to disc folder
            disc_number: Detected disc number
            dry_run: If True, don't actually rename

        Returns:
            (success, new_path or message)
        """
        current = Path(folder_path)
        expected_name = self.generate_disc_folder_name(disc_number)

        if current.name == expected_name:
            return True, folder_path  # Already correct

        new_path = current.parent / expected_name

        if new_path.exists():
            return False, f"Target folder already exists: {new_path}"

        if dry_run:
            return True, f"Would rename '{current.name}' to '{expected_name}'"

        try:
            current.rename(new_path)
            return True, str(new_path)
        except OSError as e:
            return False, str(e)

    def detect_multi_disc_from_metadata(self,
                                        audio_files: List[AudioFile]) -> int:
        """
        Detect total disc count from file metadata.

        Args:
            audio_files: List of audio files with tags

        Returns:
            Maximum disc number found, or 1 if no disc info
        """
        max_disc = 1
        for af in audio_files:
            if af.current_tags.disc_number:
                max_disc = max(max_disc, af.current_tags.disc_number)
            if af.current_tags.total_discs:
                max_disc = max(max_disc, af.current_tags.total_discs)
        return max_disc

    def generate_folder_name(self, year: int, album_name: str) -> str:
        """
        Generate standardized folder name: YEAR - ALBUM_NAME.

        Args:
            year: Album release year
            album_name: Album title

        Returns:
            Formatted folder name
        """
        clean_name = self._sanitize_folder_name(album_name)
        return f"{year} - {clean_name}"

    def generate_disc_folder_name(self, disc_number: int) -> str:
        """
        Generate disc subfolder name: CD{NUM}.

        Args:
            disc_number: Disc number

        Returns:
            Formatted disc folder name
        """
        return f"CD{disc_number}"

    def _sanitize_folder_name(self, name: str) -> str:
        """Remove/replace characters invalid for folder names."""
        # Replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        # Remove leading/trailing whitespace and dots
        name = name.strip(". ")
        # Collapse multiple spaces/underscores
        name = re.sub(r"[_\s]+", " ", name)
        return name

    def is_folder_properly_named(self, folder_path: str) -> bool:
        """
        Check if folder follows YEAR - ALBUM_NAME convention.

        Args:
            folder_path: Path to folder

        Returns:
            True if properly named
        """
        folder_name = Path(folder_path).name
        return bool(re.match(self.ALBUM_FOLDER_PATTERN, folder_name))

    def parse_folder_name(self, folder_path: str) -> Tuple[Optional[int], Optional[str]]:
        """
        Parse year and album from folder name if properly formatted.

        Args:
            folder_path: Path to folder

        Returns:
            (year, album_name) tuple, both None if not parseable
        """
        folder_name = Path(folder_path).name
        match = re.match(self.ALBUM_FOLDER_PATTERN, folder_name)
        if match:
            return int(match.group(1)), match.group(2).strip()
        return None, None

    def rename_folder(self, current_path: str, new_name: str,
                      dry_run: bool = False) -> Tuple[bool, str]:
        """
        Rename folder to new name.

        Args:
            current_path: Current folder path
            new_name: New folder name
            dry_run: If True, don't actually rename

        Returns:
            (success, message) tuple
        """
        current = Path(current_path)
        new_path = current.parent / new_name

        if new_path.exists():
            return False, f"Target folder already exists: {new_path}"

        if current.name == new_name:
            return True, "Folder already has correct name"

        if dry_run:
            return True, f"Would rename to: {new_path}"

        try:
            current.rename(new_path)
            return True, str(new_path)
        except OSError as e:
            return False, str(e)

    def create_multi_disc_structure(self, source_folder: str, year: int,
                                    album_name: str, total_discs: int,
                                    dry_run: bool = False) -> Tuple[bool, str]:
        """
        Create proper multi-disc folder structure and move files.

        Structure:
            {YEAR} - {ALBUM_NAME}/
                CD1/
                CD2/
                ...

        Args:
            source_folder: Current folder with all files
            year: Album year
            album_name: Album title
            total_discs: Number of discs
            dry_run: If True, don't make changes

        Returns:
            (success, new_base_path or error message)
        """
        source = Path(source_folder)
        new_base_name = self.generate_folder_name(year, album_name)
        new_base = source.parent / new_base_name

        if dry_run:
            return True, f"Would create: {new_base}/ with CD1-CD{total_discs} subfolders"

        try:
            # Create base folder
            new_base.mkdir(exist_ok=True)

            # Create disc subfolders
            for disc_num in range(1, total_discs + 1):
                disc_folder = new_base / self.generate_disc_folder_name(disc_num)
                disc_folder.mkdir(exist_ok=True)

            return True, str(new_base)
        except OSError as e:
            return False, str(e)

    def move_file_to_disc_folder(self, file_path: str, disc_folder: str,
                                 dry_run: bool = False) -> Tuple[bool, str]:
        """
        Move audio file to appropriate disc folder.

        Args:
            file_path: Path to audio file
            disc_folder: Target disc folder
            dry_run: If True, don't move

        Returns:
            (success, new_path or error message)
        """
        source = Path(file_path)
        target = Path(disc_folder) / source.name

        if dry_run:
            return True, f"Would move to: {target}"

        if not source.exists():
            return False, f"Source file not found: {source}"

        if target.exists():
            return False, f"Target already exists: {target}"

        try:
            shutil.move(str(source), str(target))
            return True, str(target)
        except Exception as e:
            return False, str(e)

    def reorganize_multi_disc_album(self, folder_path: str,
                                    audio_files: List[AudioFile],
                                    year: int, album_name: str,
                                    dry_run: bool = False) -> Tuple[bool, str]:
        """
        Reorganize files into proper multi-disc structure based on metadata.

        Args:
            folder_path: Current folder path
            audio_files: List of audio files with disc info in tags
            year: Album year
            album_name: Album title
            dry_run: If True, don't make changes

        Returns:
            (success, message)
        """
        # Determine total discs from metadata
        total_discs = self.detect_multi_disc_from_metadata(audio_files)

        if total_discs <= 1:
            return False, "Not a multi-disc album based on metadata"

        # Create folder structure
        success, result = self.create_multi_disc_structure(
            folder_path, year, album_name, total_discs, dry_run
        )

        if not success:
            return False, result

        new_base = Path(result) if not dry_run else Path(folder_path).parent / self.generate_folder_name(year, album_name)

        if dry_run:
            moves = []
            for af in audio_files:
                disc_num = af.current_tags.disc_number or 1
                disc_folder = new_base / self.generate_disc_folder_name(disc_num)
                moves.append(f"  {Path(af.file_path).name} -> {disc_folder}")
            return True, f"Would reorganize to:\n{result}\n" + "\n".join(moves)

        # Move files to appropriate disc folders
        errors = []
        for af in audio_files:
            disc_num = af.current_tags.disc_number or 1
            disc_folder = new_base / self.generate_disc_folder_name(disc_num)

            success, msg = self.move_file_to_disc_folder(
                af.file_path, str(disc_folder), dry_run
            )

            if not success:
                errors.append(msg)

        if errors:
            return False, f"Partial success. Errors:\n" + "\n".join(errors)

        # Remove old empty folder
        try:
            old_folder = Path(folder_path)
            if old_folder.exists() and not list(old_folder.iterdir()):
                old_folder.rmdir()
        except Exception:
            pass  # Non-critical

        return True, str(new_base)

    def get_album_info_from_files(self,
                                  audio_files: List[AudioFile]) -> Tuple[Optional[int], Optional[str]]:
        """
        Extract album info from audio file tags.

        Args:
            audio_files: List of audio files

        Returns:
            (year, album_name) tuple, values may be None
        """
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

    def _sanitize_filename(self, name: str) -> str:
        """Remove/replace characters invalid for filenames."""
        # Replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        # Remove leading/trailing whitespace and dots
        name = name.strip(". ")
        # Collapse multiple spaces/underscores
        name = re.sub(r"[_\s]+", " ", name)
        return name

    def generate_filename(self, metadata, extension: str) -> Optional[str]:
        """
        Generate filename based on metadata.

        Single disc: {ARTIST} - {ALBUM} - {TRACK_NUMBER} - {TITLE}.{ext}
        Multi-disc:  {ARTIST} - {ALBUM} CD{N} - {TRACK_NUMBER} - {TITLE}.{ext}

        Args:
            metadata: TrackMetadata with file info
            extension: File extension including dot (e.g., '.mp3')

        Returns:
            New filename or None if any required field is missing
        """
        # All fields must be present - never rename with incomplete metadata
        if not all([metadata.artist, metadata.album, metadata.track_number, metadata.title]):
            return None

        artist = self._sanitize_filename(metadata.artist)
        album = self._sanitize_filename(metadata.album)
        title = self._sanitize_filename(metadata.title)
        track_num = f"{metadata.track_number:02d}"

        # Include CD number for multi-disc albums
        if metadata.disc_number and (metadata.total_discs and metadata.total_discs > 1):
            album_part = f"{album} CD{metadata.disc_number}"
        else:
            album_part = album

        return f"{artist} - {album_part} - {track_num} - {title}{extension}"

    def should_rename_file(self, current_path: str, metadata) -> bool:
        """
        Check if file needs renaming (not already correctly named).

        Args:
            current_path: Current file path
            metadata: TrackMetadata with expected values

        Returns:
            True if file should be renamed, False otherwise
        """
        current_name = Path(current_path).stem
        extension = Path(current_path).suffix

        expected_filename = self.generate_filename(metadata, extension)
        if expected_filename is None:
            return False  # Missing metadata - don't rename

        expected_stem = Path(expected_filename).stem
        return current_name != expected_stem

    def rename_audio_file(self, file_path: str, new_name: str,
                          dry_run: bool = False) -> Tuple[bool, str]:
        """
        Rename audio file to new name.

        Args:
            file_path: Current file path
            new_name: New filename (not full path)
            dry_run: If True, don't actually rename

        Returns:
            (success, new_path or error message)
        """
        current = Path(file_path)
        new_path = current.parent / new_name

        if new_path.exists() and new_path != current:
            return False, f"Target file already exists: {new_path}"

        if current.name == new_name:
            return True, "File already has correct name"

        if dry_run:
            return True, f"Would rename to: {new_name}"

        try:
            current.rename(new_path)
            return True, str(new_path)
        except OSError as e:
            return False, str(e)
