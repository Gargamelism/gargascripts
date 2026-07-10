"""Protocols defining the public interfaces consumed by disc and naming helpers."""

from pathlib import Path
from typing import Callable, Protocol, Tuple

from sync_results import CommitResult


class RenameCoordinator(Protocol):
    """Provides atomic local rename commits and deferred remote-sync queuing."""

    def queue_sync(self, folder: Path) -> None: ...

    def commit(
        self,
        local_dst: Path,
        commit_fn: Callable[[], None],
    ) -> CommitResult: ...

    def commit_and_queue(
        self,
        local_dst: Path,
        commit_fn: Callable[[], None],
        sync_folder: Path,
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

    def queue_sync(self, folder: Path) -> None: ...
