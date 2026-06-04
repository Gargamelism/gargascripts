"""Protocol defining the public interface for remote sync operations."""

from pathlib import Path
from typing import Callable, Optional, Protocol

from sync_results import MoveResult, RcloneResult


class RemoteSync(Protocol):
    """Mirrors local renames and file pushes to a remote storage backend."""

    log: Callable[[str], None]

    def moveto(
        self,
        local_src: Path,
        local_dst: Path,
        dry_run: bool = False,
        *,
        allow_recovery: bool = True,
    ) -> MoveResult: ...

    def copyto(
        self,
        local_path: Path,
        dry_run: bool = False,
        timeout: Optional[int] = None,
    ) -> RcloneResult: ...
