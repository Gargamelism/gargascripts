#!/usr/bin/env python3
"""
Rclone OneDrive Bisync with intelligent conflict resolution.

Runs rclone bisync and handles conflicts by comparing modification times,
preferring the newer file. When timestamps are equal, both files are preserved.
"""

import argparse
import json
import logging
import re
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class SyncConfig:
    """Configuration for rclone bisync operation."""

    local_path: Path
    remote_path: str
    filter_file: Path
    log_dir: Path
    max_logs: int = 20
    dry_run: bool = False
    verbose: bool = False
    resync: bool = False
    max_retries: int = 3
    retry_delay: int = 30
    rclone_path: str = "/opt/homebrew/bin/rclone"


@dataclass
class FileIssue:
    """Represents a file that had issues during sync."""

    path: str
    issue_type: str  # "conflict", "error", "skipped"
    message: str
    local_mtime: Optional[datetime] = None
    remote_mtime: Optional[datetime] = None


@dataclass
class Resolution:
    """Result of resolving a conflict."""

    path: str
    action: str  # "kept_local", "kept_remote", "kept_both", "error"
    message: str


@dataclass
class SyncResult:
    """Result of the sync operation."""

    exit_code: int
    conflicts_found: list[str] = field(default_factory=list)
    conflicts_resolved: list[Resolution] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class RcloneSyncManager:
    """Manages rclone bisync with conflict resolution."""

    # Rclone exit codes
    EXIT_SUCCESS = 0
    EXIT_RETRYABLE = 1
    EXIT_USAGE_ERROR = 2
    EXIT_CRITICAL = 7

    def __init__(self, config: SyncConfig):
        self.config = config
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_file: Path = self.config.log_dir / f"sync-{timestamp}.log"
        self.logger = self._setup_logging()
        self._interrupted = False
        signal.signal(signal.SIGINT, self._handle_interrupt)
        self._validate_config()

    def _handle_interrupt(self, _signum, _frame) -> None:
        """Handle SIGINT for graceful shutdown."""
        self.logger.warning("Interrupt received, finishing current operation...")
        self._interrupted = True

    def _validate_config(self) -> None:
        """Validate configuration before running sync."""
        errors = []

        if not self.config.local_path.exists():
            errors.append(f"Local path does not exist: {self.config.local_path}")

        if not self.config.filter_file.exists():
            errors.append(f"Filter file does not exist: {self.config.filter_file}")

        rclone = Path(self.config.rclone_path)
        if not rclone.exists():
            errors.append(f"rclone not found at: {self.config.rclone_path}")

        if errors:
            for e in errors:
                self.logger.error(e)
            raise ValueError("Configuration validation failed")

    def _build_remote_path(self, file_path: str) -> str:
        """Build properly formatted remote path."""
        remote_base = self.config.remote_path.rstrip("/")
        file_part = file_path.lstrip("/")
        return f"{remote_base}/{file_part}"

    def _get_lock_file_path(self) -> Path:
        """Get the bisync lock file path for this sync pair."""
        # Rclone stores lock files in ~/Library/Caches/rclone/bisync/ (macOS)
        # Format: {sanitized_path1}..{sanitized_path2}_.lck
        cache_dir = Path.home() / "Library/Caches/rclone/bisync"

        # Sanitize paths the same way rclone does (replace / with _)
        local_sanitized = str(self.config.local_path).replace("/", "_").lstrip("_")
        remote_sanitized = self.config.remote_path.rstrip(":").replace(":", "_")

        lock_name = f"{local_sanitized}..{remote_sanitized}_.lck"
        return cache_dir / lock_name

    def _cleanup_lock_file(self) -> None:
        """Delete the bisync lock file if it exists."""
        lock_path = self._get_lock_file_path()
        if lock_path.exists():
            self.logger.debug(f"Cleaning up lock file: {lock_path}")
            try:
                lock_path.unlink()
            except Exception as e:
                self.logger.warning(f"Failed to delete lock file: {e}")

    def _setup_logging(self) -> logging.Logger:
        """Configure logging with file and console handlers."""

        logger = logging.getLogger("rclone_sync")
        logger.setLevel(logging.DEBUG if self.config.verbose else logging.INFO)
        logger.handlers.clear()

        # File handler
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if self.config.verbose else logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(console_handler)

        return logger

    def run_bisync(self) -> SyncResult:
        """Execute rclone bisync with conflict resolution."""
        self.logger.info("=" * 60)
        self.logger.info(f"Sync started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Local: {self.config.local_path}")
        self.logger.info(f"Remote: {self.config.remote_path}")
        self.logger.info(f"Filter file: {self.config.filter_file}")
        self.logger.info("=" * 60)

        cmd = [
            self.config.rclone_path,
            "bisync",
            str(self.config.local_path),
            self.config.remote_path,
            f"--filter-from={self.config.filter_file}",
            f"--log-file={self.log_file}",
            "--resilient",
            "--recover",
            "--check-access",
            "--metadata",
            "--retries", "3",
            "--retries-sleep", "10s",
            "--tpslimit", "4",
            "--transfers", "2",
            "--onedrive-chunk-size", "5M",
            "--low-level-retries", "10",
            "--conflict-resolve", "newer",
            "--conflict-loser", "num",
            "--max-lock", "30m",
            "--no-update-dir-modtime",
        ]

        # Add verbosity based on config
        if self.config.verbose:
            cmd.append("-vv")
        else:
            cmd.append("-v")

        if self.config.resync:
            cmd.append("--resync")
            self.logger.info("RESYNC MODE - rebuilding sync state")

        if self.config.dry_run:
            cmd.append("--dry-run")
            self.logger.info("DRY RUN MODE - no changes will be made")

        self.logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            exit_code = process.returncode
        except Exception as e:
            self.logger.error(f"Failed to run rclone: {e}")
            return SyncResult(exit_code=1, errors=[str(e)])
        finally:
            # Always clean up lock file after sync attempt
            self._cleanup_lock_file()

        self.logger.info(f"Rclone exited with code: {exit_code}")

        # Handle critical exit code
        if exit_code == self.EXIT_CRITICAL:
            self.logger.error(
                "Bisync state is corrupted. Run with --resync flag to recover."
            )

        # Parse log for issues
        issues = self.parse_rclone_output()
        result = SyncResult(
            exit_code=exit_code,
            conflicts_found=[i.path for i in issues if i.issue_type == "conflict"],
            errors=[i.message for i in issues if i.issue_type == "error"],
        )

        # Handle any remaining conflicts
        if exit_code in (self.EXIT_SUCCESS, self.EXIT_RETRYABLE):
            result.conflicts_resolved = self.resolve_remaining_conflicts()

        self.logger.info(f"Sync completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"Exit code: {exit_code}")
        self.logger.info(f"Conflicts found: {len(result.conflicts_found)}")
        self.logger.info(f"Conflicts resolved: {len(result.conflicts_resolved)}")
        self.logger.info(f"Errors: {len(result.errors)}")

        return result

    def run_sync_with_retry(self) -> SyncResult:
        """Run bisync with automatic retry on transient failures."""
        attempt = 0

        while True:
            attempt += 1
            if self.config.max_retries > 0:
                self.logger.info(f"Sync attempt {attempt}/{self.config.max_retries}")
            else:
                self.logger.info(f"Sync attempt {attempt} (unlimited retries)")

            result = self.run_bisync()

            # Success - done
            if result.exit_code == 0:
                return result

            # Handle critical error (exit code 7) - try to recover
            if result.exit_code == self.EXIT_CRITICAL and not self.config.resync:
                # Check if it's just metadata errors (transfers completed successfully)
                if self._check_transfers_completed():
                    self.logger.info(
                        "Transfers completed successfully, only metadata errors occurred"
                    )
                    self.logger.info("Running --resync to recover bisync state...")
                    self.config.resync = True
                    resync_result = self.run_bisync()
                    self.config.resync = False

                    # Check for any copy failures and retry with direct copy
                    copy_failures = self._parse_copy_failures()
                    if copy_failures:
                        self.logger.info(
                            f"Found {len(copy_failures)} files that failed during bisync, "
                            "retrying with direct copy..."
                        )
                        direct_results = self._retry_with_direct_copy(copy_failures)
                        successes = sum(1 for r in direct_results if r.action in ("pushed", "pulled"))
                        self.logger.info(f"Direct copy: {successes}/{len(copy_failures)} files succeeded")

                    return resync_result

                # Check for failed file transfers
                failed_files = self._parse_failed_files()
                if failed_files:
                    self.logger.info(
                        f"Found {len(failed_files)} files that failed with transient errors"
                    )
                    self.logger.info("Retrying failed files individually...")
                    retry_results = self._retry_failed_transfers(failed_files)

                    # Check if all retries succeeded
                    failures = [r for r in retry_results if r.action == "error"]
                    if not failures:
                        self.logger.info(
                            "All file retries succeeded, running --resync to recover state..."
                        )
                        self.config.resync = True
                        resync_result = self.run_bisync()
                        self.config.resync = False  # Reset for future calls

                        # Check for any copy failures and retry with direct copy
                        copy_failures = self._parse_copy_failures()
                        if copy_failures:
                            self.logger.info(
                                f"Found {len(copy_failures)} files that failed during bisync, "
                                "retrying with direct copy..."
                            )
                            direct_results = self._retry_with_direct_copy(copy_failures)
                            successes = sum(1 for r in direct_results if r.action in ("pushed", "pulled"))
                            self.logger.info(f"Direct copy: {successes}/{len(copy_failures)} files succeeded")

                        return resync_result
                    else:
                        self.logger.error(
                            f"{len(failures)} file retries failed, manual intervention needed"
                        )
                        return result

            # Check if retryable
            is_retryable = self._is_retryable_error(result)

            if not is_retryable:
                self.logger.error("Non-retryable error, stopping")

                # Before giving up, try direct copy for any files that failed
                copy_failures = self._parse_copy_failures()
                if copy_failures:
                    self.logger.info(
                        f"Found {len(copy_failures)} files that failed during bisync, "
                        "retrying with direct copy..."
                    )
                    direct_results = self._retry_with_direct_copy(copy_failures)
                    successes = sum(1 for r in direct_results if r.action in ("pushed", "pulled"))
                    self.logger.info(f"Direct copy: {successes}/{len(copy_failures)} files succeeded")

                return result

            # Check max retries (0 = unlimited)
            if self.config.max_retries > 0 and attempt >= self.config.max_retries:
                self.logger.error(f"Max retries ({self.config.max_retries}) reached, stopping")
                return result

            # Check for interrupt
            if self._interrupted:
                self.logger.warning("Interrupted, stopping retries")
                return result

            # Wait and retry
            self.logger.info(f"Retrying in {self.config.retry_delay} seconds...")
            time.sleep(self.config.retry_delay)

    def _is_retryable_error(self, result: SyncResult) -> bool:
        """Check if the error is transient and worth retrying."""
        # Exit code 1 = retryable error
        if result.exit_code == 1:
            return True

        # Exit code 7 with "retryable without --resync" in log = network/transient error
        if result.exit_code == 7:
            for error in result.errors:
                if "retryable without --resync" in error.lower():
                    return True

        return False

    def parse_rclone_output(self) -> list[FileIssue]:
        """Parse rclone log file for conflicts and errors."""
        issues: list[FileIssue] = []

        if not self.log_file or not self.log_file.exists():
            return issues

        conflict_pattern = re.compile(
            r"WARNING.*New or changed in both paths.*: (.+)"
        )
        error_pattern = re.compile(r"ERROR\s*:\s*(.+)")

        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    # Check for conflicts
                    match = conflict_pattern.search(line)
                    if match:
                        issues.append(
                            FileIssue(
                                path=match.group(1).strip(),
                                issue_type="conflict",
                                message=line.strip(),
                            )
                        )
                        continue

                    # Check for errors
                    match = error_pattern.search(line)
                    if match:
                        issues.append(
                            FileIssue(
                                path="",
                                issue_type="error",
                                message=match.group(1).strip(),
                            )
                        )
        except Exception as e:
            self.logger.warning(f"Failed to parse log file: {e}")

        return issues

    def _check_transfers_completed(self) -> bool:
        """Check if all file transfers completed successfully (only metadata errors remain)."""
        if not self.log_file or not self.log_file.exists():
            return False

        # Look for the final transfer summary line like:
        # "Transferred:          312 / 312, 100%"
        transfer_pattern = re.compile(r"Transferred:\s+(\d+)\s*/\s*(\d+),\s*100%")
        has_metadata_errors = False
        transfers_complete = False

        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    # Check for 100% transfer completion
                    match = transfer_pattern.search(line)
                    if match:
                        transferred = int(match.group(1))
                        total = int(match.group(2))
                        if transferred == total and total > 0:
                            transfers_complete = True

                    # Check for metadata errors (not file transfer errors)
                    if "Failed to update directory timestamp or metadata" in line:
                        has_metadata_errors = True
                    if "error updating metadata" in line:
                        has_metadata_errors = True

        except Exception as e:
            self.logger.warning(f"Failed to check transfer completion: {e}")
            return False

        return transfers_complete and has_metadata_errors

    def _parse_failed_files(self) -> list[str]:
        """Parse log file to find files that failed with transient errors (EOF, 500, etc)."""
        failed_files: list[str] = []

        if not self.log_file or not self.log_file.exists():
            return failed_files

        # Pattern matches: "ERROR : <filepath>: Couldn't move: EOF" or similar transient errors
        error_pattern = re.compile(
            r"ERROR\s*:\s*(.+?):\s*(?:Couldn't move|Failed to copy|error copying).*"
            r"(?:EOF|500|502|503|504|timeout|connection|invalidRequest)",
            re.IGNORECASE,
        )

        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    match = error_pattern.search(line)
                    if match:
                        file_path = match.group(1).strip()
                        if file_path and file_path not in failed_files:
                            failed_files.append(file_path)
        except Exception as e:
            self.logger.warning(f"Failed to parse log for failed files: {e}")

        return failed_files

    def _parse_copy_failures(self) -> list[str]:
        """Parse log file for files that failed to copy during bisync."""
        failed_files: set[str] = set()

        if not self.log_file or not self.log_file.exists():
            return []

        pattern = re.compile(r"ERROR\s*:\s*(.+?):\s*Failed to copy")

        try:
            with open(self.log_file, "r") as f:
                for line in f:
                    match = pattern.search(line)
                    if match:
                        file_path = match.group(1).strip()
                        if file_path:
                            failed_files.add(file_path)
        except Exception as e:
            self.logger.warning(f"Failed to parse log for copy failures: {e}")

        return list(failed_files)

    def _retry_with_direct_copy(self, failed_files: list[str]) -> list[Resolution]:
        """Retry failed files using direct rclone copyto (bypasses bisync issues)."""
        resolutions: list[Resolution] = []

        for file_path in failed_files:
            if self._interrupted:
                self.logger.warning("Interrupt detected, stopping direct copy retry")
                break

            self.logger.info(f"Retrying with direct copy: {file_path}")
            resolution = self._sync_single_file(file_path)
            resolutions.append(resolution)

            if resolution.action in ("pushed", "pulled"):
                self.logger.info(f"Direct copy succeeded: {file_path}")
            else:
                self.logger.warning(f"Direct copy failed: {file_path} - {resolution.message}")

        return resolutions

    def resolve_remaining_conflicts(self) -> list[Resolution]:
        """Find and resolve any .conflict* files left after sync."""
        resolutions: list[Resolution] = []

        # Find all conflict files (rclone pattern: file.txt.conflict1)
        conflict_files = list(self.config.local_path.rglob("*.conflict[0-9]*"))

        for conflict_file in conflict_files:
            if self._interrupted:
                self.logger.warning("Interrupt detected, stopping conflict resolution")
                break
            resolution = self._resolve_single_conflict(conflict_file)
            if resolution:
                resolutions.append(resolution)
                self.logger.info(f"Resolved conflict: {resolution.path} -> {resolution.action}")

        return resolutions

    def _get_original_from_conflict(self, conflict_file: Path) -> Optional[Path]:
        """Extract original filename from conflict file."""
        name = conflict_file.name
        # Rclone pattern: filename.ext.conflict1 or filename.ext.conflict2
        match = re.match(r"(.+)\.conflict\d+$", name)
        if match:
            original_name = match.group(1)
            return conflict_file.parent / original_name
        return None

    def _resolve_single_conflict(self, conflict_file: Path) -> Optional[Resolution]:
        """Resolve a single conflict file by comparing local vs actual remote mtime."""
        original_file = self._get_original_from_conflict(conflict_file)

        if not original_file:
            self.logger.warning(f"Could not parse conflict filename: {conflict_file}")
            return None

        if not original_file.exists():
            self.logger.warning(f"Original file not found for conflict: {original_file}")
            return None

        relative_path = str(original_file.relative_to(self.config.local_path))

        try:
            # Get LOCAL file's mtime (this is the "local" version)
            local_mtime_ns = original_file.stat().st_mtime_ns

            # Get REMOTE file's actual mtime via rclone lsjson
            remote_mtime_ns = self._get_remote_mtime(relative_path)

            if remote_mtime_ns is None:
                self.logger.warning(f"Could not get remote mtime for {relative_path}, skipping")
                return None

            if self.config.dry_run:
                if local_mtime_ns > remote_mtime_ns:
                    return Resolution(
                        path=relative_path,
                        action="would_keep_local",
                        message=f"Local is newer ({local_mtime_ns} > {remote_mtime_ns})",
                    )
                elif remote_mtime_ns > local_mtime_ns:
                    return Resolution(
                        path=relative_path,
                        action="would_keep_remote",
                        message=f"Remote is newer ({remote_mtime_ns} > {local_mtime_ns})",
                    )
                else:
                    return Resolution(
                        path=relative_path,
                        action="would_keep_both",
                        message="Timestamps equal, would keep both files",
                    )

            # Actually resolve the conflict
            if local_mtime_ns > remote_mtime_ns:
                # Local is newer - delete conflict file, push local to remote
                conflict_file.unlink()
                self._copy_to_remote(relative_path)
                return Resolution(
                    path=relative_path,
                    action="kept_local",
                    message=f"Local is newer, pushed to remote ({local_mtime_ns} > {remote_mtime_ns})",
                )
            elif remote_mtime_ns > local_mtime_ns:
                # Remote is newer - replace local with conflict file (which has remote content)
                original_file.unlink()
                conflict_file.rename(original_file)
                return Resolution(
                    path=relative_path,
                    action="kept_remote",
                    message=f"Remote is newer, replaced local ({remote_mtime_ns} > {local_mtime_ns})",
                )
            else:
                # Equal timestamps - keep both with descriptive names
                date_suffix = datetime.now().strftime("%Y%m%d")
                ext = original_file.suffix
                stem = original_file.stem

                local_name = f"{stem}.local-{date_suffix}{ext}"
                remote_name = f"{stem}.remote-{date_suffix}{ext}"

                local_path = original_file.parent / local_name
                remote_path_local = original_file.parent / remote_name

                original_file.rename(local_path)
                conflict_file.rename(remote_path_local)

                return Resolution(
                    path=relative_path,
                    action="kept_both",
                    message=f"Timestamps equal, renamed to {local_name} and {remote_name}",
                )

        except Exception as e:
            self.logger.error(f"Failed to resolve conflict {conflict_file}: {e}")
            return Resolution(
                path=str(conflict_file),
                action="error",
                message=str(e),
            )

    def retry_failed_files(self, files: list[str]) -> list[Resolution]:
        """Retry syncing individual failed files using rclone copyto."""
        resolutions: list[Resolution] = []

        for file_path in files:
            if self._interrupted:
                self.logger.warning("Interrupt detected, stopping retry")
                break

            local_file = self.config.local_path / file_path

            # Get remote file info
            remote_mtime = self._get_remote_mtime(file_path)
            if remote_mtime is None:
                self.logger.warning(f"Could not get remote mtime for {file_path}")
                continue

            local_mtime = None
            if local_file.exists():
                local_mtime = local_file.stat().st_mtime_ns

            # Determine direction
            if local_mtime is None or (remote_mtime and remote_mtime > local_mtime):
                # Pull from remote
                resolution = self._copy_from_remote(file_path)
            elif local_mtime and (remote_mtime is None or local_mtime > remote_mtime):
                # Push to remote
                resolution = self._copy_to_remote(file_path)
            else:
                resolution = Resolution(
                    path=file_path,
                    action="skipped",
                    message="Files have equal timestamps",
                )

            resolutions.append(resolution)

        return resolutions

    def _retry_failed_transfers(self, files: list[str]) -> list[Resolution]:
        """Retry files that failed during transfer with transient errors."""
        resolutions: list[Resolution] = []

        for file_path in files:
            if self._interrupted:
                self.logger.warning("Interrupt detected, stopping retry")
                break

            self.logger.info(f"Retrying failed file: {file_path}")
            resolution = self._sync_single_file(file_path)
            resolutions.append(resolution)
            self.logger.info(f"Retry result for {file_path}: {resolution.action}")

        return resolutions

    def _sync_single_file(self, file_path: str) -> Resolution:
        """Sync a single file, determining direction from mtimes."""
        local_file = self.config.local_path / file_path

        # Get remote mtime
        remote_mtime = self._get_remote_mtime(file_path)

        # Get local mtime if file exists
        local_mtime = None
        if local_file.exists():
            local_mtime = local_file.stat().st_mtime_ns

        # Determine sync direction
        if local_mtime and (not remote_mtime or local_mtime > remote_mtime):
            # Local is newer or remote doesn't exist - push to remote
            return self._copy_to_remote(file_path)
        elif remote_mtime and (not local_mtime or remote_mtime > local_mtime):
            # Remote is newer or local doesn't exist - pull from remote
            return self._copy_from_remote(file_path)
        elif local_mtime and remote_mtime:
            # Equal timestamps
            return Resolution(
                path=file_path,
                action="skipped",
                message="Files have equal timestamps",
            )
        else:
            # Neither exists
            return Resolution(
                path=file_path,
                action="skipped",
                message="File not found on either side",
            )

    def _get_remote_mtime(self, file_path: str) -> Optional[int]:
        """Get modification time of remote file using rclone lsjson."""
        remote_path = self._build_remote_path(file_path)

        try:
            result = subprocess.run(
                [self.config.rclone_path, "lsjson", remote_path],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return None

            data = json.loads(result.stdout)
            if data and len(data) > 0:
                mtime_str = data[0].get("ModTime", "")
                if mtime_str:
                    # Parse ISO 8601 format
                    dt = datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
                    return int(dt.timestamp() * 1_000_000_000)

        except Exception as e:
            self.logger.debug(f"Failed to get remote mtime for {file_path}: {e}")

        return None

    def _copy_from_remote(self, file_path: str) -> Resolution:
        """Copy a file from remote to local using copyto for explicit paths."""
        remote_path = self._build_remote_path(file_path)
        local_file = self.config.local_path / file_path
        local_file.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.config.rclone_path,
            "copyto",
            remote_path,
            str(local_file),
        ]

        if self.config.dry_run:
            return Resolution(
                path=file_path,
                action="would_pull",
                message="Would copy from remote (remote is newer)",
            )

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return Resolution(
                    path=file_path,
                    action="pulled",
                    message="Copied from remote (remote is newer)",
                )
            else:
                return Resolution(
                    path=file_path,
                    action="error",
                    message=f"Failed to copy from remote: {result.stderr}",
                )
        except Exception as e:
            return Resolution(
                path=file_path,
                action="error",
                message=str(e),
            )

    def _copy_to_remote(self, file_path: str) -> Resolution:
        """Copy a file from local to remote using copyto for explicit paths."""
        local_file = self.config.local_path / file_path
        remote_path = self._build_remote_path(file_path)

        cmd = [
            self.config.rclone_path,
            "copyto",
            str(local_file),
            remote_path,
        ]

        if self.config.dry_run:
            return Resolution(
                path=file_path,
                action="would_push",
                message="Would copy to remote (local is newer)",
            )

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return Resolution(
                    path=file_path,
                    action="pushed",
                    message="Copied to remote (local is newer)",
                )
            else:
                return Resolution(
                    path=file_path,
                    action="error",
                    message=f"Failed to copy to remote: {result.stderr}",
                )
        except Exception as e:
            return Resolution(
                path=file_path,
                action="error",
                message=str(e),
            )

    def rotate_logs(self) -> None:
        """Keep only the most recent max_logs log files."""
        log_files = sorted(
            self.config.log_dir.glob("sync-*.log"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        for old_log in log_files[self.config.max_logs:]:
            try:
                old_log.unlink()
                self.logger.debug(f"Deleted old log: {old_log}")
            except Exception as e:
                self.logger.warning(f"Failed to delete old log {old_log}: {e}")

    def write_summary(self, result: SyncResult) -> None:
        """Write a JSON summary of the sync result."""
        summary_file = self.config.log_dir / "last-sync-summary.json"

        summary = {
            "timestamp": datetime.now().isoformat(),
            "exit_code": result.exit_code,
            "conflicts_found": result.conflicts_found,
            "conflicts_resolved": [
                {"path": r.path, "action": r.action, "message": r.message}
                for r in result.conflicts_resolved
            ],
            "errors": result.errors,
            "log_file": str(self.log_file) if self.log_file else None,
        }

        try:
            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to write summary: {e}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Rclone OneDrive bisync with intelligent conflict resolution.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Use all defaults
  %(prog)s --dry-run                # Show what would be done
  %(prog)s --local /path/to/local   # Custom local path
  %(prog)s -v                       # Verbose output
        """,
    )

    parser.add_argument(
        "--local",
        type=Path,
        default=Path("/Volumes/data_2/onedrive"),
        help="Local directory path (default: /Volumes/data_2/onedrive)",
    )
    parser.add_argument(
        "--remote",
        default="onedrive:",
        help="Remote rclone path (default: onedrive:)",
    )
    parser.add_argument(
        "--filter",
        type=Path,
        default=Path.home() / ".config/rclone/bisync-filters.txt",
        help="Filter file path (default: ~/.config/rclone/bisync-filters.txt)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path.home() / "Library/Logs/rclone-onedrive",
        help="Log directory (default: ~/Library/Logs/rclone-onedrive)",
    )
    parser.add_argument(
        "--max-logs",
        type=int,
        default=20,
        help="Maximum number of log files to keep (default: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--resync",
        action="store_true",
        help="Force resync to recover from corrupted bisync state",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum sync retry attempts on failure (default: 3, 0 = unlimited)",
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=30,
        help="Seconds to wait between retries (default: 30)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Increase output verbosity",
    )
    parser.add_argument(
        "--rclone-path",
        default="/opt/homebrew/bin/rclone",
        help="Path to rclone binary (default: /opt/homebrew/bin/rclone)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    config = SyncConfig(
        local_path=args.local,
        remote_path=args.remote,
        filter_file=args.filter,
        log_dir=args.log_dir,
        max_logs=args.max_logs,
        dry_run=args.dry_run,
        verbose=args.verbose,
        resync=args.resync,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        rclone_path=args.rclone_path,
    )

    try:
        manager = RcloneSyncManager(config)
    except ValueError:
        # Validation error already logged
        return 2

    # Run the sync
    result = manager.run_sync_with_retry()

    # Retry any files that had conflicts but weren't auto-resolved
    if result.conflicts_found and result.exit_code in (0, 1):
        retry_results = manager.retry_failed_files(result.conflicts_found)
        result.conflicts_resolved.extend(retry_results)

    # Write summary and rotate logs
    manager.write_summary(result)
    manager.rotate_logs()

    return result.exit_code


if __name__ == "__main__":
    exit(main())
