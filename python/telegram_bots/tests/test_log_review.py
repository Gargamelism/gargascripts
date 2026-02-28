"""
Tests for log_review.py — focused on pure-Python functions that don't touch
Claude or Telegram (no network calls, no subprocess).
"""

import sys
from pathlib import Path

import pytest

# Allow importing log_review from the parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from rclone_log_analyze import (
    LogDigest,
    build_fallback_analysis,
    extract_log_digest,
    format_telegram_message,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def write_log(tmp_path: Path, content: str) -> Path:
    """Write a fake sync log file with a valid filename."""
    log_file = tmp_path / "sync-20260227-010004.log"
    log_file.write_text(content, encoding="utf-8")
    return log_file


# ─── extract_log_digest tests ─────────────────────────────────────────────────

class TestExtractLogDigest:

    def test_successful_sync(self, tmp_path):
        content = (
            "2026-02-27 01:00:04,806 - INFO - Sync attempt 1/3\n"
            "2026/02/27 01:00:06 INFO  : Documents/file1.txt: Copied (new)\n"
            "2026/02/27 01:00:07 INFO  : Documents/file2.txt: Copied (new)\n"
            "2026/02/27 01:10:00 INFO  : Music/old.mp3: Deleted\n"
            "2026/02/27 01:33:28 INFO  : Bisync successful\n"
            "2026-02-27 01:33:31,917 - INFO - Sync completed at 2026-02-27 01:33:31\n"
            "2026-02-27 01:33:31,917 - INFO - Exit code: 0\n"
            "2026/02/27 01:33:29 INFO  : \n"
            "Transferred:   52 MiB / 52 MiB, 100%, 1 MiB/s, ETA 0s\n"
            "Checks:        100 / 100, 100%\n"
            "Elapsed time:  33m27s\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert digest.bisync_outcome == "success"
        assert digest.files_copied_new == 2
        assert digest.files_deleted == 1
        assert digest.exit_code == 0
        assert digest.log_date == "2026-02-27"
        assert digest.duration_minutes == pytest.approx(33.45, abs=0.1)

    def test_error_detection_and_deduplication(self, tmp_path):
        content = (
            "2026/02/13 01:34:33 ERROR : Music/file.mp3: Failed to set modification time: EOF\n"
            "2026/02/13 01:34:34 ERROR : Documents/other.pdf: Failed to copy: connection reset\n"
            "2026/02/13 01:34:35 ERROR : Music/file.mp3: Failed to set modification time: EOF\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert len(digest.errors) == 2  # duplicate removed

    def test_resync_detection(self, tmp_path):
        content = (
            "2026-02-16 01:00:03 NOTICE: Listings not found. Reverting to prior backup as --recover is set.\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert digest.resync_performed is True
        assert digest.resync_reason != ""

    def test_folders_not_deleted(self, tmp_path):
        content = (
            "2026/02/13 01:36:37 ERROR : OneDrive root '': not deleting files as there were IO errors\n"
            "2026/02/13 01:36:37 ERROR : OneDrive root '': not deleting directories as there were IO errors\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert len(digest.folders_not_deleted) == 2

    def test_retry_count(self, tmp_path):
        content = (
            "2026/02/13 01:34:33 NOTICE: Retry 1/3\n"
            "2026/02/13 01:35:00 NOTICE: Retry 2/3\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert digest.retry_count == 2

    def test_critical_error(self, tmp_path):
        content = (
            "2026/01/21 06:00:07 ERROR : Bisync critical error: cannot find prior Path1 or Path2 listings\n"
            "2026/01/21 06:00:07 NOTICE: Failed to bisync: bisync aborted\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert digest.bisync_outcome == "critical_error"

    def test_warning_deduplication(self, tmp_path):
        same_warning = "2026-02-27 01:33:31,916 - WARNING - Something went wrong: bad state\n"
        content = same_warning * 3
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert len(digest.warnings) == 1

    def test_file_change_cap(self, tmp_path):
        lines = [
            f"2026/02/27 01:00:0{i % 10} INFO  : Documents/file{i:03d}.txt: Copied (new)\n"
            for i in range(25)
        ]
        log_file = write_log(tmp_path, "".join(lines))
        digest = extract_log_digest(log_file)

        assert digest.files_copied_new == 25
        assert len(digest.new_files) == 20  # capped at MAX_FILES_PER_CATEGORY

    def test_duration_calculation(self, tmp_path):
        content = (
            "2026-02-27 01:00:04,806 - INFO - Sync attempt 1/3\n"
            "2026-02-27 01:33:31,917 - INFO - Sync completed at 2026-02-27 01:33:31\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert digest.duration_minutes == pytest.approx(33.45, abs=0.1)

    def test_hebrew_filenames(self, tmp_path):
        content = (
            "2026/02/27 01:00:06 INFO  : Documents/מטלה 1.musx: Copied (new)\n"
        )
        log_file = write_log(tmp_path, content)
        # Should not raise, and Hebrew filename should be captured
        digest = extract_log_digest(log_file)
        assert digest.files_copied_new == 1
        assert any("מטלה" in f for f in digest.new_files)

    def test_log_date_parsed_from_filename(self, tmp_path):
        content = ""
        log_file = tmp_path / "sync-20260227-010004.log"
        log_file.write_text(content)
        digest = extract_log_digest(log_file)
        assert digest.log_date == "2026-02-27"

    def test_no_duplicate_deleted_and_not_deleting(self, tmp_path):
        """Lines with 'not deleting' should not be counted as deleted files."""
        content = (
            "2026/02/13 01:36:37 ERROR : OneDrive root '': not deleting files as there were IO errors\n"
            "2026/02/27 01:10:00 INFO  : Music/old.mp3: Deleted\n"
        )
        log_file = write_log(tmp_path, content)
        digest = extract_log_digest(log_file)

        assert digest.files_deleted == 1
        assert len(digest.folders_not_deleted) == 1


# ─── format_telegram_message tests ───────────────────────────────────────────

def _make_analysis(**overrides) -> dict:
    base = {
        "STATUS": "Success",
        "STATUS_DETAIL": "All good.",
        "SYNC_STATS": "5 new, 0 modified, 2 deleted",
        "ERRORS_SUMMARY": "None",
        "RESYNC": "No",
        "FOLDERS_SKIPPED": "None",
        "CONFLICTS": "None",
        "DURATION": "10 min 0 sec",
        "NOTABLE": "None",
    }
    base.update(overrides)
    return base


def _make_digest(**overrides) -> LogDigest:
    d = LogDigest(log_file="sync-20260227-010004.log", log_date="2026-02-27")
    for k, v in overrides.items():
        setattr(d, k, v)
    return d


class TestFormatTelegramMessage:

    def test_success_has_green_icon(self):
        msg = format_telegram_message(_make_analysis(STATUS="Success"), _make_digest())
        assert "\U0001f7e2" in msg  # 🟢

    def test_failed_has_red_icon(self):
        msg = format_telegram_message(_make_analysis(STATUS="Failed"), _make_digest())
        assert "\U0001f534" in msg  # 🔴

    def test_partial_has_yellow_icon(self):
        msg = format_telegram_message(_make_analysis(STATUS="Partial success"), _make_digest())
        assert "\U0001f7e1" in msg  # 🟡

    def test_did_not_run_has_grey_icon(self):
        msg = format_telegram_message(_make_analysis(STATUS="Did not run"), _make_digest())
        assert "\u26aa" in msg  # ⚫

    def test_html_escaping_in_errors(self):
        analysis = _make_analysis(ERRORS_SUMMARY="- Failed: <path/to/file> error & more")
        msg = format_telegram_message(analysis, _make_digest())
        assert "&lt;path/to/file&gt;" in msg
        assert "&amp;" in msg
        assert "<path/to/file>" not in msg

    def test_long_message_truncated(self):
        # Generate a very long errors section (500 lines × ~16 chars each = ~8000 chars)
        long_errors = "\n".join(f"- error line {i}" for i in range(500))
        analysis = _make_analysis(ERRORS_SUMMARY=long_errors)
        msg = format_telegram_message(analysis, _make_digest())
        assert len(msg) <= 4000
        assert "truncated" in msg

    def test_notable_included_when_not_none(self):
        analysis = _make_analysis(NOTABLE="7 stale conflict files remain")
        msg = format_telegram_message(analysis, _make_digest())
        assert "7 stale conflict files remain" in msg

    def test_notable_excluded_when_none(self):
        analysis = _make_analysis(NOTABLE="None")
        msg = format_telegram_message(analysis, _make_digest())
        assert "<b>Notable:</b>" not in msg

    def test_log_filename_included(self):
        msg = format_telegram_message(_make_analysis(), _make_digest())
        assert "sync-20260227-010004.log" in msg


# ─── build_fallback_analysis tests ───────────────────────────────────────────

class TestBuildFallbackAnalysis:

    def test_fallback_success(self):
        d = LogDigest(exit_code=0, bisync_outcome="success")
        result = build_fallback_analysis(d)
        assert result["STATUS"] == "Success"

    def test_fallback_critical_error_exit_7(self):
        d = LogDigest(exit_code=7)
        result = build_fallback_analysis(d)
        assert result["STATUS"] == "Failed"
        assert "7" in result["STATUS_DETAIL"]

    def test_fallback_critical_error_bisync_outcome(self):
        d = LogDigest(exit_code=0, bisync_outcome="critical_error")
        result = build_fallback_analysis(d)
        assert result["STATUS"] == "Failed"

    def test_fallback_unknown_exit(self):
        d = LogDigest(exit_code=-1)
        result = build_fallback_analysis(d)
        assert result["STATUS"] == "Did not run"

    def test_fallback_resync(self):
        d = LogDigest(exit_code=0, bisync_outcome="success",
                      resync_performed=True, resync_reason="listings missing")
        result = build_fallback_analysis(d)
        assert result["RESYNC"].startswith("Yes")
        assert "listings missing" in result["RESYNC"]

    def test_fallback_sync_stats(self):
        d = LogDigest(exit_code=0, bisync_outcome="success",
                      files_copied_new=5, files_deleted=2, bytes_transferred="10 MiB")
        result = build_fallback_analysis(d)
        assert "5 new" in result["SYNC_STATS"]
        assert "2 deleted" in result["SYNC_STATS"]
        assert "10 MiB" in result["SYNC_STATS"]

    def test_fallback_no_file_changes(self):
        d = LogDigest(exit_code=0, bisync_outcome="success")
        result = build_fallback_analysis(d)
        assert result["SYNC_STATS"] == "No file changes"

    def test_fallback_duration(self):
        d = LogDigest(exit_code=0, bisync_outcome="success", duration_minutes=33.5)
        result = build_fallback_analysis(d)
        assert "33 min" in result["DURATION"]

    def test_fallback_conflicts(self):
        d = LogDigest(exit_code=0, bisync_outcome="success",
                      conflicts_found=["file1", "file2", "file3"],
                      conflicts_resolved=["file1"])
        result = build_fallback_analysis(d)
        assert "3 found" in result["CONFLICTS"]
        assert "1 resolved" in result["CONFLICTS"]

    def test_fallback_contains_ai_unavailable_note(self):
        d = LogDigest(exit_code=0, bisync_outcome="success")
        result = build_fallback_analysis(d)
        assert "AI analysis unavailable" in result["STATUS_DETAIL"]
