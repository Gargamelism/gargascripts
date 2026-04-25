"""Mirror local renames to the remote OneDrive via rclone server-side moves.

Paired with FolderManager's rename entry points so that when a file or folder
is renamed locally, the same rename is applied on OneDrive before the local
operation is committed. This prevents bisync from seeing a delete+add pair
and keeping both copies, and lets the next bisync run see matching names on
both sides with nothing to do.
"""

import shlex
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable, Optional, Tuple


def _default_log(msg: str) -> None:
    print(msg, flush=True)


class OneDriveSync:
    """Run rclone server-side renames on a OneDrive remote in lockstep with local renames."""

    def __init__(
        self,
        local_root: Path,
        remote: str = "onedrive:",
        rclone_path: Optional[str] = None,
        timeout: int = 120,
        log: Callable[[str], None] = _default_log,
    ):
        # strict=True surfaces a missing sync root immediately instead of letting
        # every moveto() call fail later with a cryptic relative_to ValueError.
        self.local_root = local_root.resolve(strict=True)
        self.remote = remote if remote.endswith(":") else f"{remote}:"
        self.rclone_path = rclone_path or shutil.which("rclone") or "/opt/homebrew/bin/rclone"
        self.timeout = timeout
        self.log = log

    def is_in_sync_root(self, local_path: Path) -> bool:
        """True if local_path is under the configured sync root."""
        try:
            local_path.resolve().relative_to(self.local_root)
            return True
        except ValueError:
            return False

    def _to_remote(self, local_path: Path) -> str:
        """Map a local path inside the sync root to a rclone remote path (NFC)."""
        rel = local_path.resolve().relative_to(self.local_root)
        # OneDrive stores NFC; normalize so we ask for the canonical form.
        normalized = unicodedata.normalize("NFC", rel.as_posix())
        return f"{self.remote}{normalized}"

    def moveto(
        self,
        local_src: Path,
        local_dst: Path,
        dry_run: bool = False,
    ) -> Tuple[bool, str]:
        """Rename src → dst on the remote via `rclone moveto`.

        Returns (True, message) if the remote operation succeeded (or was skipped
        because the source is outside the sync root). Returns (False, message)
        on any rclone failure so the caller can abort the local rename.
        """
        if not self.is_in_sync_root(local_src):
            return True, "skipped: source outside sync root"

        if not self.is_in_sync_root(local_dst):
            return True, "skipped: destination outside sync root"

        remote_src = self._to_remote(local_src)
        remote_dst = self._to_remote(local_dst)

        if remote_src == remote_dst:
            return True, "skipped: remote src and dst identical"

        cmd = [self.rclone_path, "moveto", remote_src, remote_dst]
        if dry_run:
            cmd.append("--dry-run")

        prefix = "[onedrive dry-run]" if dry_run else "[onedrive]"
        self.log(f"    {prefix} {remote_src} -> {remote_dst}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            # shlex.join here is only for the human-readable error message.
            return False, f"rclone moveto timed out after {self.timeout}s: {shlex.join(cmd)}"
        except FileNotFoundError:
            return False, f"rclone binary not found at {self.rclone_path}"

        if result.returncode == 0:
            return True, f"renamed {remote_src} -> {remote_dst}"

        stderr = (result.stderr or result.stdout).strip()
        return False, f"rclone exit {result.returncode}: {stderr}"

    def copyto(
        self,
        local_path: Path,
        dry_run: bool = False,
        timeout: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """Push local content to its matching remote path via `rclone copyto`.

        Used after an in-place ID3 write so the remote `quickXorHash` and mtime
        match the freshly-edited local file. Without this, the next bisync
        sees mismatched checksums and emits `quickxor differ`.

        --checksum makes rclone skip the upload when content already matches
        (e.g. when preserve_existing left the file byte-identical). --metadata
        carries local mtime to the remote so bisync's mtime+size check stays
        clean — without it OneDrive stamps "now" and the next bisync sees a
        fresh mtime conflict.
        """
        if not self.is_in_sync_root(local_path):
            return True, "skipped: outside sync root"

        if not local_path.exists():
            return False, f"local file missing: {local_path}"

        remote_dst = self._to_remote(local_path)

        cmd = [
            self.rclone_path,
            "copyto",
            str(local_path),
            remote_dst,
            "--checksum",
            "--metadata",
        ]
        if dry_run:
            cmd.append("--dry-run")

        prefix = "[onedrive dry-run]" if dry_run else "[onedrive]"
        self.log(f"    {prefix} copyto {local_path} -> {remote_dst}")

        # Large files over a slow link can exceed the moveto default; give
        # copyto a longer fallback so we don't time out on multi-MB FLACs.
        effective_timeout = timeout if timeout is not None else self.timeout * 5

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"rclone copyto timed out after {effective_timeout}s: {shlex.join(cmd)}"
        except FileNotFoundError:
            return False, f"rclone binary not found at {self.rclone_path}"

        if result.returncode == 0:
            return True, f"pushed {local_path} -> {remote_dst}"

        stderr = (result.stderr or result.stdout).strip()
        return False, f"rclone exit {result.returncode}: {stderr}"
