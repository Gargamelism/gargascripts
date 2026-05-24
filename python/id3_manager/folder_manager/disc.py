"""Disc detection and multi-disc reorganization helpers for FolderManager."""

import re
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from models import AlbumFolder, AudioFile
from sync_results import CommitResult
from folder_manager.naming import generate_disc_folder_name, generate_folder_name


DISC_PATTERNS = [
    r"(?:cd|disc|disk)\s*(\d+)",
    r"^(\d+)$",
    r"d(\d+)",
]


def extract_disc_number(patterns: list, folder_name: str) -> Optional[int]:
    folder_name_lower = folder_name.lower()
    for pattern in patterns:
        match = re.search(pattern, folder_name_lower, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def detect_multi_disc_structure(fm, folder_path: str) -> List[AlbumFolder]:
    path = Path(folder_path)

    if not path.is_dir():
        return [AlbumFolder(folder_path=folder_path)]

    subfolders = [d for d in path.iterdir() if d.is_dir()]

    disc_folders = []
    for subfolder in subfolders:
        disc_num = extract_disc_number(fm.DISC_PATTERNS,subfolder.name)
        if disc_num is not None:
            disc_folders.append((disc_num, subfolder))

    if len(disc_folders) >= 2:
        disc_folders.sort(key=lambda x: x[0])
        return [
            AlbumFolder(
                folder_path=str(sf),
                detected_disc_number=num,
                parent_folder=folder_path,
            )
            for num, sf in disc_folders
        ]

    return [AlbumFolder(folder_path=folder_path)]


def infer_disc_info_from_path(fm, file_path: str) -> Optional[Tuple[int, int]]:
    parent = Path(file_path).parent
    disc_num = extract_disc_number(fm.DISC_PATTERNS,parent.name)
    if disc_num is None:
        return None
    grandparent = parent.parent
    sibling_disc_count = sum(
        1 for d in grandparent.iterdir()
        if d.is_dir() and extract_disc_number(fm.DISC_PATTERNS,d.name) is not None
    )
    return (disc_num, sibling_disc_count) if sibling_disc_count >= 2 else None


def detect_multi_disc_from_metadata(audio_files: List[AudioFile]) -> int:
    max_disc = 1
    for af in audio_files:
        if af.current_tags.disc_number:
            max_disc = max(max_disc, af.current_tags.disc_number)
        if af.current_tags.total_discs:
            max_disc = max(max_disc, af.current_tags.total_discs)
    return max_disc


def normalize_disc_folder_name(fm, folder_path: str, disc_number: int,
                                dry_run: bool = False) -> CommitResult:
    current = Path(folder_path)
    expected_name = generate_disc_folder_name(disc_number)

    if current.name == expected_name:
        return CommitResult(success=True, message=folder_path)

    new_path = current.parent / expected_name

    if new_path.exists():
        return CommitResult(success=False, message=f"Target folder already exists: {new_path}")

    mirror = fm._mirror_rename(current, new_path, dry_run, allow_recovery=False)
    if not mirror.success:
        return CommitResult(success=False, message=f"Remote rename failed: {mirror.message}")

    if dry_run:
        return CommitResult(
            success=True, message=f"Would rename '{current.name}' to '{expected_name}'"
        )

    return fm._commit_with_rollback(
        current, new_path, lambda: current.rename(new_path), mirror_result=mirror
    )


def create_multi_disc_structure(fm, source_folder: str, year: int, album_name: str,
                                 total_discs: int, dry_run: bool = False) -> Tuple[bool, str]:
    source = Path(source_folder)
    new_base_name = generate_folder_name(year, album_name)
    new_base = source.parent / new_base_name

    if dry_run:
        return True, f"Would create: {new_base}/ with CD1-CD{total_discs} subfolders"

    try:
        new_base.mkdir(exist_ok=True)
        for disc_num in range(1, total_discs + 1):
            disc_folder = new_base / generate_disc_folder_name(disc_num)
            disc_folder.mkdir(exist_ok=True)
        return True, str(new_base)
    except OSError as e:
        return False, str(e)


def move_file_to_disc_folder(fm, file_path: str, disc_folder: str,
                              dry_run: bool = False) -> CommitResult:
    source = Path(file_path)
    target = Path(disc_folder) / source.name

    if not source.exists():
        return CommitResult(success=False, message=f"Source file not found: {source}")

    if target.exists():
        return CommitResult(success=False, message=f"Target already exists: {target}")

    mirror = fm._mirror_rename(source, target, dry_run=dry_run)
    if not mirror.success:
        return CommitResult(success=False, message=f"Remote move failed: {mirror.message}")

    if dry_run:
        return CommitResult(success=True, message=f"Would move to: {target}")

    return fm._commit_with_rollback(
        source,
        target,
        lambda: shutil.move(str(source), str(target)),
        mirror_result=mirror,
    )


def reorganize_multi_disc_album(fm, folder_path: str, audio_files: List[AudioFile],
                                 year: int, album_name: str,
                                 dry_run: bool = False) -> Tuple[bool, str]:
    total_discs = detect_multi_disc_from_metadata(audio_files)

    if total_discs <= 1:
        return False, "Not a multi-disc album based on metadata"

    success, result = fm.create_multi_disc_structure(
        folder_path, year, album_name, total_discs, dry_run
    )

    if not success:
        return False, result

    new_base = (
        Path(result) if not dry_run
        else Path(folder_path).parent / generate_folder_name(year, album_name)
    )

    if dry_run:
        moves = []
        for af in audio_files:
            disc_num = af.current_tags.disc_number or 1
            disc_folder = new_base / generate_disc_folder_name(disc_num)
            moves.append(f"  {Path(af.file_path).name} -> {disc_folder}")
        return True, f"Would reorganize to:\n{result}\n" + "\n".join(moves)

    errors = []
    for af in audio_files:
        disc_num = af.current_tags.disc_number or 1
        disc_folder = new_base / generate_disc_folder_name(disc_num)
        move_result = fm.move_file_to_disc_folder(af.file_path, str(disc_folder), dry_run)
        if not move_result.success:
            errors.append(move_result.message)

    if errors:
        return False, f"Partial success. Errors:\n" + "\n".join(errors)

    try:
        old_folder = Path(folder_path)
        if old_folder.exists() and not list(old_folder.iterdir()):
            old_folder.rmdir()
    except Exception:
        pass

    return True, str(new_base)
