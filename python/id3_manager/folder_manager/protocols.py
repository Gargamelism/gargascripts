"""Protocols defining the public interfaces consumed by disc and naming helpers."""

from pathlib import Path
from typing import Callable, Protocol, Tuple

from sync_results import CommitResult, MoveResult


class RenameCoordinator(Protocol):
    """Provides atomic rename + remote-mirror operations."""

    def mirror_rename(
        self,
        local_src: Path,
        local_dst: Path,
        dry_run: bool,
        *,
        allow_recovery: bool = True,
    ) -> MoveResult: ...

    def commit_with_rollback(
        self,
        local_src: Path,
        local_dst: Path,
        commit_fn: Callable[[], None],
        *,
        mirror_result: MoveResult,
    ) -> CommitResult: ...


class MultiDiscOrganizer(Protocol):
    """Creates multi-disc folder structures and moves files into them."""

    def create_multi_disc_structure(
        self,
        source_folder: str,
        year: int,
        album_name: str,
        total_discs: int,
        dry_run: bool = False,
    ) -> Tuple[bool, str]: ...

    def move_file_to_disc_folder(
        self,
        file_path: str,
        disc_folder: str,
        dry_run: bool = False,
    ) -> CommitResult: ...
