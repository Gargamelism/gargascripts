"""Mirror local renames to the remote OneDrive via rclone server-side moves.

Paired with FolderManager's rename entry points so that when a file or folder
is renamed locally, the same rename is applied on OneDrive before the local
operation is committed. This prevents bisync from seeing a delete+add pair
and keeping both copies, and lets the next bisync run see matching names on
both sides with nothing to do.
"""

import json
import re
import shlex
import shutil
import subprocess
import unicodedata
from pathlib import Path
from typing import Callable, List, Optional

from mutagen import File as MutagenFile

from id3_handler import ID3Handler
from sync_results import (
    DivergenceConfirmation,
    LsJsonResult,
    MoveResult,
    RcloneResult,
    RecoveryMetadata,
)
from . import recovery as _recovery


def _default_log(msg: str) -> None:
    print(msg, flush=True)


class OneDriveSync:
    """Run rclone server-side renames on a OneDrive remote in lockstep with local renames."""

    _DIVERGENCE_PATTERN = re.compile(
        r"(directory|item)\s*not\s*found|directoryNotFound|itemNotFound",
        re.IGNORECASE,
    )

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
        self.rclone_path = rclone_path or shutil.which("rclone") or "/opt/homebrew/bin/rclone"
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

    def moveto(
        self,
        local_src: Path,
        local_dst: Path,
        dry_run: bool = False,
        *,
        allow_recovery: bool = True,
    ) -> MoveResult:
        if not self.is_in_sync_root(local_src):
            return MoveResult(True, "skipped: source outside sync root", "skipped")

        if not self.is_in_sync_root(local_dst):
            return MoveResult(True, "skipped: destination outside sync root", "skipped")

        remote_src = self._to_remote(local_src)
        remote_dst = self._to_remote(local_dst)

        if remote_src == remote_dst:
            return MoveResult(True, "skipped: remote src and dst identical", "skipped")

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
            return MoveResult(
                False,
                f"rclone moveto timed out after {self.timeout}s: {shlex.join(cmd)}",
                "failed",
            )
        except FileNotFoundError:
            return MoveResult(
                False, f"rclone binary not found at {self.rclone_path}", "failed"
            )

        if result.returncode == 0:
            return MoveResult(
                True, f"renamed {remote_src} -> {remote_dst}", "moveto"
            )

        stderr = (result.stderr or result.stdout).strip()
        if allow_recovery and self._looks_like_source_missing(result.returncode, stderr):
            confirmation = self._confirm_source_missing(local_src, local_dst)
            if confirmation.confirmed:
                return self._recover_diverged_rename(local_src, local_dst, dry_run)
            return MoveResult(
                success=False,
                message=f"rclone exit {result.returncode}: {stderr} ({confirmation.reason})",
                mode="failed",
            )
        return MoveResult(
            success=False,
            message=f"rclone exit {result.returncode}: {stderr}",
            mode="failed",
        )

    def copyto(
        self,
        local_path: Path,
        dry_run: bool = False,
        timeout: Optional[int] = None,
    ) -> RcloneResult:
        if not self.is_in_sync_root(local_path):
            return RcloneResult(True, "skipped: outside sync root")

        if not local_path.exists():
            return RcloneResult(False, f"local file missing: {local_path}")

        remote_dst = self._to_remote(local_path)
        return self._copyto_explicit(local_path, remote_dst, dry_run=dry_run, timeout=timeout)

    def _copyto_explicit(
        self,
        local_path: Path,
        remote_dst: str,
        dry_run: bool,
        timeout: Optional[int] = None,
    ) -> RcloneResult:
        cmd = [
            self.rclone_path,
            "copyto",
            str(local_path),
            remote_dst,
            "--checksum",
        ]
        if dry_run:
            cmd.append("--dry-run")

        prefix = "[onedrive dry-run]" if dry_run else "[onedrive]"
        self.log(f"    {prefix} copyto {local_path} -> {remote_dst}")

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
                False, f"rclone copyto timed out after {effective_timeout}s: {shlex.join(cmd)}"
            )
        except FileNotFoundError:
            return RcloneResult(False, f"rclone binary not found at {self.rclone_path}")

        if result.returncode == 0:
            return RcloneResult(True, f"pushed {local_path} -> {remote_dst}")

        stderr = (result.stderr or result.stdout).strip()
        return RcloneResult(False, f"rclone exit {result.returncode}: {stderr}")

    def _lsjson(self, args: List[str]) -> LsJsonResult:
        cmd = [self.rclone_path, "lsjson", *args]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
        except subprocess.TimeoutExpired:
            return LsJsonResult(success=False, error=f"lsjson timed out after {self.timeout}s")
        except FileNotFoundError:
            return LsJsonResult(success=False, error=f"rclone binary not found at {self.rclone_path}")
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout).strip()
            return LsJsonResult(
                success=False, error=f"lsjson exit {result.returncode}: {stderr}"
            )
        try:
            return LsJsonResult(success=True, entries=json.loads(result.stdout or "[]"))
        except json.JSONDecodeError as e:
            return LsJsonResult(success=False, error=f"lsjson JSON parse failure: {e}")

    def _deletefile(self, remote_path: str) -> RcloneResult:
        cmd = [self.rclone_path, "deletefile", remote_path]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
        except subprocess.TimeoutExpired:
            return RcloneResult(False, f"rclone deletefile timed out after {self.timeout}s")
        except FileNotFoundError:
            return RcloneResult(False, f"rclone binary not found at {self.rclone_path}")
        if result.returncode == 0:
            return RcloneResult(True, f"deleted {remote_path}")
        stderr = (result.stderr or result.stdout).strip()
        return RcloneResult(False, f"rclone exit {result.returncode}: {stderr}")

    def _looks_like_source_missing(self, returncode: int, stderr: str) -> bool:
        return returncode in (1, 3) and bool(self._DIVERGENCE_PATTERN.search(stderr))

    def _read_recovery_metadata(self, local_src: Path) -> RecoveryMetadata:
        try:
            meta = ID3Handler().read_tags(str(local_src))
        except Exception as e:
            self.log(f"[onedrive] recovery: read_tags failed for {local_src}: {e}")
            return RecoveryMetadata(title=None, track_number=None, duration_seconds=None)

        duration = None
        try:
            audio = MutagenFile(str(local_src))
            if audio is not None and getattr(audio, "info", None) is not None:
                duration = getattr(audio.info, "length", None)
        except Exception:
            duration = None

        return RecoveryMetadata(
            title=meta.title,
            track_number=meta.track_number,
            duration_seconds=duration,
        )

    @staticmethod
    def _normalize_for_match(s: str) -> str:
        s = unicodedata.normalize("NFC", s).casefold()
        s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    # Shims — keep method names on the class so tests using patch.object keep working
    def _confirm_source_missing(self, local_src: Path, local_dst: Path) -> DivergenceConfirmation:
        return _recovery.confirm_source_missing(self, local_src, local_dst)

    def _recover_diverged_rename(self, local_src: Path, local_dst: Path, dry_run: bool) -> MoveResult:
        return _recovery.recover_diverged_rename(self, local_src, local_dst, dry_run)

    def _match_diverged_old_name(
        self, local_src: Path, local_dst: Path, listing: List[dict]
    ) -> Optional[str]:
        return _recovery.match_diverged_old_name(self, local_src, local_dst, listing)
