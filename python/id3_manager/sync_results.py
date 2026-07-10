"""Dataclasses for sync-operation return values (rclone wrappers, rename/move flows)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RcloneResult:
    """Result of a single rclone subprocess invocation (copyto, sync)."""

    success: bool
    message: str  # human-readable status ("synced ...", "pushed ...") or error string


@dataclass(frozen=True)
class CommitResult:
    """Result of FolderManager.commit and the 4 public rename/move methods.

    On success, `message` is the destination path string. On failure, it's an error description.
    """

    success: bool
    message: str
