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
        *,
        allow_recovery: bool = True,
    ) -> MoveResult:
        """Rename src → dst on the remote via `rclone moveto`.

        On non-zero exit that looks like a OneDrive itemNotFound/directoryNotFound,
        and `allow_recovery=True`, attempt a recovery via copyto + best-effort
        delete of the diverged old name (see `_recover_diverged_rename`).
        """
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
            # shlex.join here is only for the human-readable error message.
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
        """Push local content to its matching remote path via `rclone copyto`.

        Used after an in-place ID3 write so the remote `quickXorHash` and mtime
        match the freshly-edited local file. Without this, the next bisync
        sees mismatched checksums and emits `quickxor differ`.

        --checksum makes rclone skip the upload when content already matches
        (e.g. when preserve_existing left the file byte-identical). The OneDrive
        backend preserves local mtime via fileSystemInfo on upload, so we don't
        pass --metadata: that flag also tries to ship macOS xattrs (com.apple.*)
        which Graph rejects with `invalidRequest: Invalid request`.
        """
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
        """Like copyto() but takes an explicit remote destination (not derived from local_path)."""
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
        """Run `rclone lsjson <args>`. On success, .entries is the parsed list. On failure, .error is set."""
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
        # rclone returns exit 3 ("directory not found") for OneDrive Graph itemNotFound.
        # Also accept exit 1 if the stderr text is unambiguous (rclone has been inconsistent
        # across versions about which exit code OneDrive 404s map to).
        return returncode in (1, 3) and bool(self._DIVERGENCE_PATTERN.search(stderr))

    def _confirm_source_missing(
        self, local_src: Path, local_dst: Path
    ) -> DivergenceConfirmation:
        src_parent_remote = self._to_remote(local_src.parent)
        dst_parent_remote = self._to_remote(local_dst.parent)

        # Probe 1: dst parent must exist (otherwise this is "wrong destination", not divergence).
        dst_listing = self._lsjson([dst_parent_remote, "--no-modtime", "--dirs-only"])
        if not dst_listing.success:
            return DivergenceConfirmation(
                confirmed=False,
                reason=f"dst parent listing failed: {dst_listing.error}",
            )

        # Probe 2: src parent listing — does it contain a file with the exact local_src.name?
        src_listing = self._lsjson([src_parent_remote, "--no-modtime", "--files-only"])
        if not src_listing.success:
            # If src_parent is also missing, the divergence is at folder level — out of scope.
            return DivergenceConfirmation(
                confirmed=False,
                reason=f"src parent listing failed: {src_listing.error}",
            )

        target_name_nfc = unicodedata.normalize("NFC", local_src.name)
        found = any(
            unicodedata.normalize("NFC", entry.get("Name", "")) == target_name_nfc
            for entry in src_listing.entries
        )
        if found:
            # rclone said "not found" but the listing shows it — likely a transient 5xx. Don't recover.
            return DivergenceConfirmation(
                confirmed=False,
                reason="src exists in listing — likely transient error",
            )
        return DivergenceConfirmation(
            confirmed=True,
            reason="confirmed: src absent from src_parent",
        )

    def _recover_diverged_rename(
        self, local_src: Path, local_dst: Path, dry_run: bool
    ) -> MoveResult:
        self.log(f"[onedrive] divergence detected: remote source missing for {local_src.name}")

        # Step 1: copyto to NEW remote path. We need to upload the bytes that ARE at local_src
        # to a remote dst that maps from local_dst. Use _copyto_explicit with explicit remote_dst.
        remote_dst = self._to_remote(local_dst)
        copy_result = self._copyto_explicit(local_src, remote_dst, dry_run=dry_run)
        if not copy_result.success:
            return MoveResult(
                success=False,
                message=f"recovery copyto failed: {copy_result.message}",
                mode="failed",
            )
        self.log(f"[onedrive] recovery: copyto {local_src.name} -> {remote_dst}")

        # Step 2: list candidates in src_parent_remote and identify the OLD diverged remote name.
        src_parent_remote = self._to_remote(local_src.parent)
        listing = self._lsjson([src_parent_remote, "--no-modtime", "--files-only"])
        if not listing.success:
            self.log(
                f"[onedrive] recovery: candidate listing failed ({listing.error}); "
                f"orphan may remain at {src_parent_remote}"
            )
            return MoveResult(
                success=True,
                message="recovered: copyto only — could not list to find old name",
                mode="recovered",
            )

        old_name = self._match_diverged_old_name(local_src, local_dst, listing.entries)
        if old_name is None:
            self.log(f"[onedrive] recovery: no unique match — orphan may remain at {src_parent_remote}")
            return MoveResult(
                success=True,
                message="recovered: copyto only — no unique old-name match",
                mode="recovered",
            )

        if dry_run:
            self.log(f"[onedrive] recovery: would deletefile {src_parent_remote}/{old_name} (dry-run)")
            return MoveResult(
                success=True,
                message=f"DRY-RUN: would recover via copyto + delete {old_name}",
                mode="recovered",
            )

        # Step 3: deletefile.
        delete_result = self._deletefile(f"{src_parent_remote}/{old_name}")
        if not delete_result.success:
            self.log(f"[onedrive] recovery: deletefile failed ({delete_result.message}); orphan may remain")
            return MoveResult(
                success=True,
                message=f"recovered: copyto OK; deletefile failed: {delete_result.message}",
                mode="recovered",
            )

        self.log(f"[onedrive] recovery: matched {old_name}; deleted")
        return MoveResult(
            success=True,
            message=f"recovered: copyto + deleted {old_name}",
            mode="recovered",
        )

    def _match_diverged_old_name(
        self, local_src: Path, local_dst: Path, listing: List[dict]
    ) -> Optional[str]:
        meta = self._read_recovery_metadata(local_src)
        if not meta.title or meta.track_number is None:
            self.log(
                f"[onedrive] recovery: insufficient metadata to match "
                f"(title={meta.title!r}, track={meta.track_number})"
            )
            return None

        src_ext = local_src.suffix.lower()
        dst_name_nfc = unicodedata.normalize("NFC", local_dst.name)
        src_name_nfc = unicodedata.normalize("NFC", local_src.name)

        candidates = []
        for entry in listing:
            name = entry.get("Name", "")
            if not name:
                continue
            name_nfc = unicodedata.normalize("NFC", name)
            if Path(name_nfc).suffix.lower() != src_ext:
                continue
            if name_nfc == dst_name_nfc or name_nfc == src_name_nfc:
                continue  # Exclude the file we just copyto'd and (defensive) the canonical OLD name.
            candidates.append(name_nfc)

        title_norm = self._normalize_for_match(meta.title)
        if len(title_norm) < 3:
            self.log(f"[onedrive] recovery: title {meta.title!r} too short for safe matching")
            self.log(f"[onedrive] recovery: candidates in {local_src.parent}: {candidates}")
            return None

        track_re = re.compile(rf"(?<!\d)0*{meta.track_number}(?!\d)")

        matches = [
            name_nfc
            for name_nfc in candidates
            if title_norm in self._normalize_for_match(name_nfc)
            and track_re.search(name_nfc)
        ]

        if len(matches) == 1:
            self.log(f"[onedrive] recovery: matched {matches[0]} (unique)")
            return matches[0]

        if not matches:
            self.log(
                f"[onedrive] recovery: no candidates matched "
                f"title={meta.title!r} + track={meta.track_number}"
            )
            self.log(f"[onedrive] recovery: candidates in {local_src.parent}: {candidates}")
            return None

        # 2+ matches: duration tiebreaker would require fetching remote tags (expensive).
        # Skip delete on ambiguity.
        self.log(f"[onedrive] recovery: ambiguous — {len(matches)} candidates matched: {matches}")
        self.log(
            f"[onedrive] recovery: skipping delete to avoid wrong-file deletion; "
            f"user must clean up manually"
        )
        return None

    def _read_recovery_metadata(self, local_src: Path) -> RecoveryMetadata:
        """Return RecoveryMetadata(title, track_number, duration_seconds) from the local file."""
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
        """NFC → casefold → strip non-alphanumeric → collapse whitespace."""
        s = unicodedata.normalize("NFC", s).casefold()
        s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
        s = re.sub(r"\s+", " ", s).strip()
        return s
