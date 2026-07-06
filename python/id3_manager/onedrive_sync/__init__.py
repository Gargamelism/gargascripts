"""Push local folder trees to OneDrive via rclone.

Renames and tag writes are applied locally without touching the remote.
Callers queue the touched folders and flush them later with `sync_folder`,
which runs a single `rclone sync --track-renames` per folder: it uploads
changed content, deletes remote files no longer present locally, and
reconciles local renames server-side (via checksum matching) instead of
deleting and re-uploading.
"""

import shlex
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable, Optional

from sync_results import RcloneResult


def _default_log(msg: str) -> None:
    print(msg, flush=True)


class OneDriveSync:
    """Runs rclone sync on a OneDrive remote for a batch of touched local folders."""

    def __init__(
        self,
        local_root: Path,
        remote: str = "onedrive:",
        rclone_path: Optional[str] = None,
        timeout: int = 120,
        log: Callable[[str], None] = _default_log,
    ):
        self.local_root = local_root.resolve(strict=True)
        self.remote = remote if remote.endswith(":") else f"{remote}:"
        self.rclone_path = (
            rclone_path or shutil.which("rclone") or "/opt/homebrew/bin/rclone"
        )
        self.timeout = timeout
        self.log = log

    def is_in_sync_root(self, local_path: Path) -> bool:
        try:
            local_path.resolve().relative_to(self.local_root)
            return True
        except ValueError:
            return False

    def _to_remote(self, local_path: Path) -> str:
        rel = local_path.resolve().relative_to(self.local_root)
        normalized = unicodedata.normalize("NFC", rel.as_posix())
        return f"{self.remote}{normalized}"

    def sync_folder(
        self,
        local_folder: Path,
        dry_run: bool = False,
        timeout: Optional[int] = None,
    ) -> RcloneResult:
        if not self.is_in_sync_root(local_folder):
            return RcloneResult(True, "skipped: outside sync root")

        remote_dst = self._to_remote(local_folder)
        cmd = [
            self.rclone_path,
            "sync",
            str(local_folder),
            remote_dst,
            "--track-renames",
            "--checksum",
        ]
        if dry_run:
            cmd.append("--dry-run")

        prefix = "[onedrive dry-run]" if dry_run else "[onedrive]"
        self.log(f"    {prefix} sync {local_folder} -> {remote_dst}")

        effective_timeout = timeout if timeout is not None else self.timeout * 5

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            return RcloneResult(
                False,
                f"rclone sync timed out after {effective_timeout}s: {shlex.join(cmd)}",
            )
        except FileNotFoundError:
            return RcloneResult(False, f"rclone binary not found at {self.rclone_path}")

        if result.returncode == 0:
            return RcloneResult(True, f"synced {local_folder} -> {remote_dst}")

        stderr = (result.stderr or result.stdout).strip()
        return RcloneResult(False, f"rclone exit {result.returncode}: {stderr}")
