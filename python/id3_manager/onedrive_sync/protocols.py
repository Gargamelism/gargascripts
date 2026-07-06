"""Protocol defining the public interface for remote sync operations."""

from pathlib import Path
from typing import Callable, Protocol

from sync_results import RcloneResult


class RemoteSync(Protocol):
    """Pushes a local folder's contents to a remote storage backend."""

    log: Callable[[str], None]

    def is_in_sync_root(self, local_path: Path) -> bool: ...

    def sync_folder(
        self,
        local_folder: Path,
        dry_run: bool = False,
        timeout: int | None = None,
    ) -> RcloneResult: ...
