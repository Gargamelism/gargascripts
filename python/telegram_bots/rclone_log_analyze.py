#!/usr/bin/env python3
"""
Parse latest rclone OneDrive sync log, call Claude, save formatted HTML message
to pending file. Triggered by launchd WatchPaths on last-sync-summary.json (~1 AM).
"""

import glob
import json
import logging
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, TypedDict

import requests
from dotenv import load_dotenv


# ─── Constants ────────────────────────────────────────────────────────────────

LOG_DIR = Path("/Users/gargamel/Library/Logs/rclone-onedrive")
SUMMARY_FILE = LOG_DIR / "last-sync-summary.json"
PENDING_FILE = LOG_DIR / "pending-message.html"
SCRIPT_DIR = Path(__file__).parent

MAX_FILES_PER_CATEGORY = 20
MAX_ERRORS = 30
MAX_WARNINGS = 20
CLAUDE_TIMEOUT = 90

STATUS_ICONS = {
    "Success": "\U0001f7e2",          # 🟢
    "Partial success": "\U0001f7e1",  # 🟡
    "Failed": "\U0001f534",           # 🔴
    "Did not run": "\u26aa",          # ⚫
}


# ─── Compiled regexes ─────────────────────────────────────────────────────────

# Filename: sync-20260227-010004.log → groups: year, month, day
RE_LOG_FILENAME_DATE = re.compile(r"sync-(\d{4})(\d{2})(\d{2})-")

# Log line timestamps: "2026-02-27 01:00:04,123 - INFO - Sync attempt"
RE_START_TIME = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ - INFO - Sync attempt")
RE_END_TIME = re.compile(r"Sync completed at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

# Exit code from wrapper log line
RE_EXIT_CODE = re.compile(r"Exit code: (\d+)")

# Error / warning extraction
RE_ERROR_TEXT = re.compile(r"ERROR\s*[: ]+(.+)")
RE_CONFLICT_FILE = re.compile(r"Original file not found for conflict: (.+)")
RE_WARNING_TEXT = re.compile(r"WARNING.*?:\s*(.+)")

# File-change events (rclone INFO lines)
RE_FILE_COPIED_NEW = re.compile(r"INFO\s+:\s+(.+?):\s+Copied \(new\)")
RE_FILE_DELETED = re.compile(r"INFO\s+:\s+(.+?):\s+Deleted$")
RE_FILE_COPIED_MODIFIED = re.compile(r"INFO\s+:\s+(.+?):\s+Copied \(modified\)")

# Retry counter
RE_RETRY = re.compile(r"Retry (\d+)/\d+")

# Final transfer stats: "Transferred: 1.2 GiB / 3.4 GiB, 100%"
RE_BYTES_TRANSFERRED = re.compile(r"Transferred:\s+[\d.]+\s+\S+\s*/\s*([\d.]+\s+\S+),\s*100%")

# JSON schema for Claude structured output (--json-schema flag)
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "STATUS":          {"type": "string", "enum": ["Success", "Partial success", "Failed", "Did not run"]},
        "STATUS_DETAIL":   {"type": "string"},
        "SYNC_STATS":      {"type": "string"},
        "ERRORS_SUMMARY":  {"type": "string"},
        "RESYNC":          {"type": "string"},
        "FOLDERS_SKIPPED": {"type": "string"},
        "CONFLICTS":       {"type": "string"},
        "DURATION":        {"type": "string"},
        "NOTABLE":         {"type": "string"},
    },
    "required": [
        "STATUS", "STATUS_DETAIL", "SYNC_STATS", "ERRORS_SUMMARY",
        "RESYNC", "FOLDERS_SKIPPED", "CONFLICTS", "DURATION", "NOTABLE",
    ],
}


# ─── Configuration ────────────────────────────────────────────────────────────

class Config(TypedDict):
    telegram_bot_token: str
    telegram_chat_id: str


def load_config() -> Config:
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    config = {
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
    }
    missing = [k.upper() for k, v in config.items() if not v]
    if missing:
        raise ValueError(f"Missing required env vars: {', '.join(missing)}")
    return config


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("analyze")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


# ─── Telegram (error notification only) ───────────────────────────────────────

def _esc(s: str) -> str:
    """Escape HTML special characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram_message(message: str, bot_token: str, chat_id: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")


def send_error_notification(bot_token: str, chat_id: str, error: str) -> None:
    try:
        msg = f"\U0001f534 <b>analyze.py failed</b>\n\n<pre>{_esc(error[:800])}</pre>"
        send_telegram_message(msg, bot_token, chat_id)
    except Exception:
        pass


# ─── Claude binary discovery ──────────────────────────────────────────────────

def find_claude_binary() -> Optional[str]:
    """Find the latest installed claude CLI binary (from VSCode extension)."""
    pattern = os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"
    )
    binaries = glob.glob(pattern)
    if not binaries:
        return None
    return max(binaries, key=os.path.getmtime)


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class LogDigest:
    log_file: str = ""
    log_date: str = ""
    start_time: str = ""
    end_time: str = ""
    duration_minutes: float = 0.0
    exit_code: int = -1
    bisync_outcome: str = "unknown"  # success | critical_error | retryable_error | unknown
    files_copied_new: int = 0
    files_copied_modified: int = 0
    files_deleted: int = 0
    bytes_transferred: str = ""
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    resync_performed: bool = False
    resync_reason: str = ""
    folders_not_deleted: list = field(default_factory=list)
    conflicts_found: list = field(default_factory=list)
    conflicts_resolved: list = field(default_factory=list)
    retry_count: int = 0
    raw_final_stats: str = ""
    new_files: list = field(default_factory=list)
    deleted_files: list = field(default_factory=list)
    modified_files: list = field(default_factory=list)


# ─── Log discovery ────────────────────────────────────────────────────────────

def find_log_from_summary() -> Optional[Path]:
    """
    Read the log path from last-sync-summary.json (authoritative).
    Falls back to globbing for the most recent sync-*.log.
    Returns None if no log can be found.
    """
    if SUMMARY_FILE.exists():
        try:
            with open(SUMMARY_FILE) as f:
                summary = json.load(f)
            log_path_str = summary.get("log_file")
            if log_path_str:
                log_path = Path(log_path_str)
                if log_path.exists():
                    return log_path
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    # Fallback: newest sync-*.log
    log_files = sorted(LOG_DIR.glob("sync-*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    return log_files[0] if log_files else None


# ─── Log pre-parser ───────────────────────────────────────────────────────────

def extract_log_digest(log_path: Path) -> LogDigest:
    """
    Single-pass line reader that extracts signal lines from the rclone sync log.
    Skips periodic progress-bar noise (Transferred: 0 B / 0 B lines during listing).
    """
    digest = LogDigest(log_file=log_path.name)

    # Extract date from filename: sync-20260227-010004.log
    m = RE_LOG_FILENAME_DATE.match(log_path.name)
    if m:
        y, mo, d = m.groups()
        digest.log_date = f"{y}-{mo}-{d}"

    errors_seen: set = set()
    warnings_seen: set = set()
    folders_not_deleted_seen: set = set()

    # Sliding window to capture the last "Elapsed time:" stats block
    recent_lines: list = []
    last_stats_block: list = []

    with open(log_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip()
            recent_lines.append(line)
            if len(recent_lines) > 8:
                recent_lines.pop(0)

            # ── Start/end timestamps ──────────────────────────────────────────
            if not digest.start_time:
                m = RE_START_TIME.match(line)
                if m:
                    digest.start_time = m.group(1)

            m = RE_END_TIME.search(line)
            if m:
                digest.end_time = m.group(1)

            # ── Bisync outcome ────────────────────────────────────────────────
            if "Bisync successful" in line:
                digest.bisync_outcome = "success"
            elif "Bisync critical error" in line:
                digest.bisync_outcome = "critical_error"
            elif "Bisync aborted" in line and "retryable" in line.lower():
                digest.bisync_outcome = "retryable_error"

            # ── Exit code (from Python wrapper log line) ──────────────────────
            m = RE_EXIT_CODE.search(line)
            if m:
                digest.exit_code = int(m.group(1))

            # ── Errors (deduplicated) ─────────────────────────────────────────
            if " ERROR " in line or "ERROR:" in line:
                m = RE_ERROR_TEXT.search(line)
                if m:
                    err_text = m.group(1).strip()
                    if err_text not in errors_seen and len(digest.errors) < MAX_ERRORS:
                        errors_seen.add(err_text)
                        digest.errors.append(err_text)

            # ── Warnings (deduplicated) ───────────────────────────────────────
            if "Original file not found for conflict" in line:
                m = RE_CONFLICT_FILE.search(line)
                if m:
                    warn_text = f"Original file not found: {Path(m.group(1).strip()).name}"
                    if warn_text not in warnings_seen and len(digest.warnings) < MAX_WARNINGS:
                        warnings_seen.add(warn_text)
                        digest.warnings.append(warn_text)
            elif "WARNING" in line:
                m = RE_WARNING_TEXT.search(line)
                if m:
                    warn_text = m.group(1).strip()
                    if warn_text not in warnings_seen and len(digest.warnings) < MAX_WARNINGS:
                        warnings_seen.add(warn_text)
                        digest.warnings.append(warn_text)

            # ── File changes ──────────────────────────────────────────────────
            if "Copied (new)" in line and "INFO" in line:
                m = RE_FILE_COPIED_NEW.search(line)
                if m:
                    digest.files_copied_new += 1
                    if len(digest.new_files) < MAX_FILES_PER_CATEGORY:
                        digest.new_files.append(m.group(1).strip())

            if ": Deleted" in line and "INFO" in line and "not deleting" not in line:
                m = RE_FILE_DELETED.search(line)
                if m:
                    digest.files_deleted += 1
                    if len(digest.deleted_files) < MAX_FILES_PER_CATEGORY:
                        digest.deleted_files.append(m.group(1).strip())

            if "Copied (modified)" in line and "INFO" in line:
                m = RE_FILE_COPIED_MODIFIED.search(line)
                if m:
                    digest.files_copied_modified += 1
                    if len(digest.modified_files) < MAX_FILES_PER_CATEGORY:
                        digest.modified_files.append(m.group(1).strip())

            # ── Resync signals ────────────────────────────────────────────────
            if not digest.resync_performed:
                if "Listings not found. Reverting to prior backup" in line:
                    digest.resync_performed = True
                    digest.resync_reason = "Listings not found, reverted to backup (--recover)"
                elif "--resync" in line and ("Running" in line or "RESYNC" in line):
                    digest.resync_performed = True
                    digest.resync_reason = "Explicit --resync flag triggered"

            # ── Folders not deleted due to IO errors ──────────────────────────
            if "not deleting" in line and "IO errors" in line:
                key = "files" if "not deleting files" in line else "dirs"
                entry = f"Skipped deleting {key} due to IO errors"
                if entry not in folders_not_deleted_seen:
                    folders_not_deleted_seen.add(entry)
                    digest.folders_not_deleted.append(entry)

            # ── Retry count ───────────────────────────────────────────────────
            m = RE_RETRY.search(line)
            if m:
                n = int(m.group(1))
                if n > digest.retry_count:
                    digest.retry_count = n

            # ── Final stats block: capture last "Elapsed time:" window ────────
            if "Elapsed time:" in line:
                last_stats_block = list(recent_lines)

            # ── Bytes transferred (from final 100% line) ──────────────────────
            if "100%" in line and "Transferred:" in line and "/" in line:
                m = RE_BYTES_TRANSFERRED.search(line)
                if m:
                    digest.bytes_transferred = m.group(1)

    if last_stats_block:
        digest.raw_final_stats = "\n".join(last_stats_block)

    # ── Duration ──────────────────────────────────────────────────────────────
    if digest.start_time and digest.end_time:
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            start = datetime.strptime(digest.start_time, fmt)
            end = datetime.strptime(digest.end_time, fmt)
            digest.duration_minutes = (end - start).total_seconds() / 60
        except ValueError:
            pass

    # ── Augment from summary JSON ─────────────────────────────────────────────
    if SUMMARY_FILE.exists():
        try:
            with open(SUMMARY_FILE) as f:
                summary = json.load(f)
            # Only use if this summary matches the log we're parsing
            summary_log = summary.get("log_file", "")
            if summary_log and Path(summary_log).name == log_path.name:
                digest.exit_code = summary.get("exit_code", digest.exit_code)
                digest.conflicts_found = summary.get("conflicts_found", digest.conflicts_found)
                digest.conflicts_resolved = [
                    r.get("path", "") for r in summary.get("conflicts_resolved", [])
                ]
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    return digest


# ─── Claude analysis ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a concise technical assistant reviewing daily rclone OneDrive bisync logs. "
    "Analyze the pre-parsed digest and produce a structured summary. "
    "Be brief and factual. Do not repeat information. "
    "If everything went fine, say so without padding. "
    "If there were errors, explain what likely went wrong in one sentence. "
    "For ERRORS_SUMMARY use a bullet list with '- ' prefix per error, or 'None'. "
    "For RESYNC use 'Yes - <reason>' or 'No'. "
    "For DURATION use e.g. '33 min 24 sec'. "
    "For fields with nothing to report use 'None'."
)


def _build_user_message(digest: LogDigest) -> str:
    def fmt_list(items: list, cap: int = MAX_FILES_PER_CATEGORY) -> str:
        if not items:
            return "None"
        shown = items[:cap]
        result = "\n  - " + "\n  - ".join(shown)
        if len(items) > cap:
            result += f"\n  ... and {len(items) - cap} more"
        return result

    return f"""Review this rclone bisync log digest for {digest.log_date}:

LOG FILE: {digest.log_file}
EXIT CODE: {digest.exit_code}
BISYNC OUTCOME: {digest.bisync_outcome}

=== FINAL STATS ===
{digest.raw_final_stats or "Not available"}

=== ERRORS ({len(digest.errors)}) ===
{chr(10).join("- " + e for e in digest.errors) or "None"}

=== WARNINGS ({len(digest.warnings)}) ===
{chr(10).join("- " + w for w in digest.warnings) or "None"}

=== FILE CHANGES ===
New files ({digest.files_copied_new}): {fmt_list(digest.new_files)}
Deleted ({digest.files_deleted}): {fmt_list(digest.deleted_files)}
Modified ({digest.files_copied_modified}): {fmt_list(digest.modified_files)}

=== CONFLICTS ===
Found ({len(digest.conflicts_found)}): {fmt_list(digest.conflicts_found, 10)}
Resolved ({len(digest.conflicts_resolved)}): {fmt_list(digest.conflicts_resolved, 10)}

=== RESYNC INFO ===
Resync performed: {digest.resync_performed}
Reason: {digest.resync_reason or "N/A"}
Folders not deleted (IO errors): {fmt_list(digest.folders_not_deleted)}

=== RETRY INFO ===
Retries attempted: {digest.retry_count}

=== TIMING ===
Start: {digest.start_time}
End: {digest.end_time}
Duration: {digest.duration_minutes:.1f} minutes"""


def analyze_with_claude(digest: LogDigest, logger: logging.Logger) -> Optional[dict]:
    """
    Call the claude CLI with the digest prompt.
    Returns parsed dict, or None on failure.
    """
    claude_bin = find_claude_binary()
    if not claude_bin:
        logger.warning("claude binary not found")
        return None

    prompt = f"{SYSTEM_PROMPT}\n\n{_build_user_message(digest)}"

    try:
        result = subprocess.run(
            [
                claude_bin,
                "--print",
                "--model", "haiku",
                "--no-session-persistence",
                "--tools", "",
                "--output-format", "json",
                "--json-schema", json.dumps(ANALYSIS_SCHEMA),
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
        )
        if result.returncode != 0:
            logger.warning(f"claude exited {result.returncode}: {result.stderr[:200]}")
            return None

        return json.loads(result.stdout)["structured_output"]

    except subprocess.TimeoutExpired:
        logger.warning(f"claude timed out after {CLAUDE_TIMEOUT}s")
        return None
    except Exception as e:
        logger.warning(f"claude call failed: {e}")
        return None


# ─── Fallback analysis ────────────────────────────────────────────────────────

def build_fallback_analysis(digest: LogDigest) -> dict:
    """Build a minimal structured analysis from LogDigest without calling Claude."""
    if digest.exit_code == 0 and digest.bisync_outcome == "success":
        status = "Success"
        detail = "Bisync completed with exit code 0."
    elif digest.exit_code == 7 or digest.bisync_outcome == "critical_error":
        status = "Failed"
        detail = f"Bisync critical error (exit code {digest.exit_code}). Manual check needed."
    elif digest.exit_code == 0:
        status = "Partial success"
        detail = f"Exited 0 but bisync outcome was '{digest.bisync_outcome}'."
    elif digest.exit_code == -1:
        status = "Did not run"
        detail = "Could not determine exit code from log."
    else:
        status = "Failed"
        detail = f"Exited with code {digest.exit_code}."

    stats_parts = []
    if digest.files_copied_new:
        stats_parts.append(f"{digest.files_copied_new} new")
    if digest.files_copied_modified:
        stats_parts.append(f"{digest.files_copied_modified} modified")
    if digest.files_deleted:
        stats_parts.append(f"{digest.files_deleted} deleted")
    if digest.bytes_transferred:
        stats_parts.append(f"({digest.bytes_transferred})")
    sync_stats = ", ".join(stats_parts) if stats_parts else "No file changes"

    duration_str = "Unknown"
    if digest.duration_minutes > 0:
        mins = int(digest.duration_minutes)
        secs = int((digest.duration_minutes - mins) * 60)
        duration_str = f"{mins} min {secs} sec"

    conflicts_str = "None"
    if digest.conflicts_found:
        conflicts_str = f"{len(digest.conflicts_found)} found, {len(digest.conflicts_resolved)} resolved"

    return {
        "STATUS": status,
        "STATUS_DETAIL": detail + " (AI analysis unavailable)",
        "SYNC_STATS": sync_stats,
        "ERRORS_SUMMARY": "\n".join(f"- {e}" for e in digest.errors) or "None",
        "RESYNC": (f"Yes - {digest.resync_reason}" if digest.resync_performed else "No"),
        "FOLDERS_SKIPPED": "\n".join(digest.folders_not_deleted) or "None",
        "CONFLICTS": conflicts_str,
        "DURATION": duration_str,
        "NOTABLE": "None",
    }


# ─── Telegram message formatting ──────────────────────────────────────────────

def format_telegram_message(analysis: dict, digest: LogDigest) -> str:
    """Build an HTML-formatted Telegram message from Claude's analysis."""
    status = analysis.get("STATUS", "Unknown")
    icon = STATUS_ICONS.get(status, "\u2753")
    date_str = digest.log_date or datetime.now().strftime("%Y-%m-%d")

    errors_raw = analysis.get("ERRORS_SUMMARY", "None")
    if errors_raw.strip().lower() == "none":
        errors_section = "None"
    else:
        errors_section = f"<pre>{_esc(errors_raw)}</pre>"

    parts = [
        f"<b>{icon} OneDrive Sync - {date_str}</b>",
        "",
        f"<b>Status:</b> {_esc(status)}",
        f"<i>{_esc(analysis.get('STATUS_DETAIL', ''))}</i>",
        "",
        f"<b>Sync stats:</b> {_esc(analysis.get('SYNC_STATS', 'N/A'))}",
        f"<b>Duration:</b> {_esc(analysis.get('DURATION', 'N/A'))}",
        "",
        f"<b>Errors:</b> {errors_section}",
        f"<b>Resync:</b> {_esc(analysis.get('RESYNC', 'No'))}",
        f"<b>Folders skipped:</b> {_esc(analysis.get('FOLDERS_SKIPPED', 'None'))}",
        f"<b>Conflicts:</b> {_esc(analysis.get('CONFLICTS', 'None'))}",
    ]

    notable = analysis.get("NOTABLE", "None")
    if notable and notable.strip().lower() != "none":
        parts += ["", f"<b>Notable:</b> {_esc(notable)}"]

    parts += ["", f"<code>{_esc(digest.log_file)}</code>"]

    message = "\n".join(parts)

    if len(message) > 4000:
        message = message[:3950] + "\n\n<i>(message truncated)</i>"

    return message


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    logger = setup_logging()
    config: Optional[Config] = None

    try:
        config = load_config()

        log_path = find_log_from_summary()
        if log_path is None:
            logger.warning("No sync log found. Nothing to analyze.")
            return 0

        logger.info(f"Parsing log: {log_path.name}")
        digest = extract_log_digest(log_path)

        logger.info("Analyzing with Claude...")
        analysis = analyze_with_claude(digest, logger)
        if analysis is None:
            logger.warning("Claude unavailable, using fallback analysis")
            analysis = build_fallback_analysis(digest)
        else:
            logger.info(f"Claude status: {analysis.get('STATUS')}")

        message = format_telegram_message(analysis, digest)

        PENDING_FILE.write_text(message, encoding="utf-8")
        logger.info(f"Saved pending message to {PENDING_FILE}")
        return 0

    except Exception:
        tb = traceback.format_exc()
        logger.error(f"Fatal error:\n{tb}")
        if config and config.get("telegram_bot_token") and config.get("telegram_chat_id"):
            send_error_notification(
                config["telegram_bot_token"], config["telegram_chat_id"], tb
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())
