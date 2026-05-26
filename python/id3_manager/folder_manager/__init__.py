"""Folder management for multi-disc detection and renaming."""

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from config import eprint
from models import AlbumFolder, AudioFile
from onedrive_sync import OneDriveSync
from sync_results import CommitResult, MoveResult
from . import disc as _disc
from . import naming as _naming
from .disc import DISC_PATTERNS


class FolderManager:
    """Manages folder detection, multi-disc detection, and renaming."""

    DISC_PATTERNS = DISC_PATTERNS

    ALBUM_FOLDER_PATTERN = r"^(\d{4})\s*-\s*(.+)$"

    def __init__(self, onedrive_sync: Optional[OneDriveSync] = None):
        self.onedrive_sync = onedrive_sync

    def _mirror_rename(
        self,
        local_src: Path,
        local_dst: Path,
        dry_run: bool,
        *,
        allow_recovery: bool = True,
    ) -> MoveResult:
        if self.onedrive_sync is None:
            return MoveResult(success=True, message="", mode="skipped")
        return self.onedrive_sync.moveto(
            local_src, local_dst, dry_run=dry_run, allow_recovery=allow_recovery
        )

    def _commit_with_rollback(
        self,
        local_src: Path,
        local_dst: Path,
        commit_fn: Callable[[], None],
        *,
        mirror_result: MoveResult,
    ) -> CommitResult:
        try:
            commit_fn()
            return CommitResult(success=True, message=str(local_dst))
        except Exception as e:
            if mirror_result.mode == "recovered":
                if self.onedrive_sync is not None:
                    self.onedrive_sync.log(
                        f"[onedrive] WARNING: local commit failed after recovered rename "
                        f"({local_src.name} -> {local_dst.name}); remote at NEW path, "
                        f"local at OLD path. Next bisync will reconcile by downloading the NEW name."
                    )
                return CommitResult(
                    success=False,
                    message=f"{e} (remote already recovered to NEW name; not rolled back)",
                )
            rollback = self._mirror_rename(
                local_dst, local_src, dry_run=False, allow_recovery=False
            )
            if not rollback.success:
                eprint(
                    f"WARNING: remote rollback FAILED after local commit error — "
                    f"local and remote trees are out of sync. "
                    f"Local error: {e}. Rollback error: {rollback.message}"
                )
                return CommitResult(
                    success=False,
                    message=f"local error: {e}; remote rollback failed: {rollback.message}",
                )
            return CommitResult(success=False, message=str(e))

    # --- Disc detection / reorganization ---

    def detect_multi_disc_structure(self, folder_path: str) -> List[AlbumFolder]:
        return _disc.detect_multi_disc_structure(self, folder_path)

    def infer_disc_info_from_path(self, file_path: str) -> Optional[Tuple[int, int]]:
        return _disc.infer_disc_info_from_path(self, file_path)

    def detect_multi_disc_from_metadata(self, audio_files: List[AudioFile]) -> int:
        return _disc.detect_multi_disc_from_metadata(audio_files)

    def normalize_disc_folder_name(
        self, folder_path: str, disc_number: int, dry_run: bool = False
    ) -> CommitResult:
        return _disc.normalize_disc_folder_name(self, folder_path, disc_number, dry_run)

    def create_multi_disc_structure(
        self,
        source_folder: str,
        year: int,
        album_name: str,
        total_discs: int,
        dry_run: bool = False,
    ) -> Tuple[bool, str]:
        return _disc.create_multi_disc_structure(
            self, source_folder, year, album_name, total_discs, dry_run
        )

    def move_file_to_disc_folder(
        self, file_path: str, disc_folder: str, dry_run: bool = False
    ) -> CommitResult:
        return _disc.move_file_to_disc_folder(self, file_path, disc_folder, dry_run)

    def reorganize_multi_disc_album(
        self,
        folder_path: str,
        audio_files: List[AudioFile],
        year: int,
        album_name: str,
        dry_run: bool = False,
    ) -> Tuple[bool, str]:
        return _disc.reorganize_multi_disc_album(
            self, folder_path, audio_files, year, album_name, dry_run
        )

    # --- Naming / filename helpers ---

    def generate_folder_name(self, year: int, album_name: str) -> str:
        return _naming.generate_folder_name(year, album_name)

    def generate_disc_folder_name(self, disc_number: int) -> str:
        return _naming.generate_disc_folder_name(disc_number)

    def is_folder_properly_named(self, folder_path: str) -> bool:
        return _naming.is_folder_properly_named(folder_path, self.ALBUM_FOLDER_PATTERN)

    def parse_folder_name(
        self, folder_path: str
    ) -> Tuple[Optional[int], Optional[str]]:
        return _naming.parse_folder_name(folder_path, self.ALBUM_FOLDER_PATTERN)

    def rename_folder(
        self, current_path: str, new_name: str, dry_run: bool = False
    ) -> CommitResult:
        return _naming.rename_folder(self, current_path, new_name, dry_run)

    def get_album_info_from_files(
        self, audio_files: List[AudioFile]
    ) -> Tuple[Optional[int], Optional[str]]:
        return _naming.get_album_info_from_files(audio_files)

    def generate_filename(self, metadata, extension: str) -> Optional[str]:
        return _naming.generate_filename(metadata, extension)

    def should_rename_file(self, current_path: str, metadata) -> bool:
        return _naming.should_rename_file(current_path, metadata)

    def rename_audio_file(
        self, file_path: str, new_name: str, dry_run: bool = False
    ) -> CommitResult:
        return _naming.rename_audio_file(self, file_path, new_name, dry_run)
