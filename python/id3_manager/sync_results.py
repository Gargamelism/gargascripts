"""Dataclasses for sync-operation return values (rclone wrappers, rename/move flows)."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class RcloneResult:
    """Result of a single rclone subprocess invocation (copyto, deletefile, copyto_explicit)."""
    success: bool
    message: str  # human-readable status ("pushed ...", "deleted ...") or error string


@dataclass(frozen=True)
class MoveResult:
    """Result of OneDriveSync.moveto, FolderManager._mirror_rename, and _recover_diverged_rename.

    `mode` values:
      - "moveto"    — rclone moveto succeeded normally; rollback-safe by reverse moveto.
      - "recovered" — divergence detected and recovery performed (copyto + best-effort delete).
                      NOT cleanly reversible by moveto alone.
      - "skipped"   — no-op (src/dst out of sync root, identical paths, or no onedrive_sync configured).
      - "failed"    — non-recoverable error.
    """
    success: bool
    message: str
    mode: str


@dataclass(frozen=True)
class LsJsonResult:
    """Result of `rclone lsjson`. On success, `entries` is the parsed JSON list of dicts.
    On failure, `error` is the error message and `entries` is empty."""
    success: bool
    entries: List[dict] = field(default_factory=list)
    error: str = ""


@dataclass(frozen=True)
class DivergenceConfirmation:
    """Output of OneDriveSync._confirm_source_missing.

    `confirmed=True` ⇒ src is genuinely absent on remote AND dst_parent exists; recovery should proceed.
    `confirmed=False` ⇒ at least one probe failed (transient error, dst missing, or src present).
    """
    confirmed: bool
    reason: str


@dataclass(frozen=True)
class RecoveryMetadata:
    """Local-file metadata used to identify the OLD diverged remote filename."""
    title: Optional[str]
    track_number: Optional[int]
    duration_seconds: Optional[float]


@dataclass(frozen=True)
class CommitResult:
    """Result of FolderManager._commit_with_rollback and the 4 public rename/move methods.

    On success, `message` is the destination path string. On failure, it's an error description.
    """
    success: bool
    message: str
