"""Divergence-recovery helpers for OneDriveSync.

Each function receives the OneDriveSync instance as its first argument so it can
call back into the core methods (_to_remote, _lsjson, _copyto_explicit, etc.)
without creating a circular import.
"""

import re
import unicodedata
from pathlib import Path
from typing import List, Optional

from sync_results import DivergenceConfirmation, MoveResult


def confirm_source_missing(sync, local_src: Path, local_dst: Path) -> DivergenceConfirmation:
    src_parent_remote = sync._to_remote(local_src.parent)
    dst_parent_remote = sync._to_remote(local_dst.parent)

    dst_listing = sync._lsjson([dst_parent_remote, "--no-modtime", "--dirs-only"])
    if not dst_listing.success:
        return DivergenceConfirmation(
            confirmed=False,
            reason=f"dst parent listing failed: {dst_listing.error}",
        )

    src_listing = sync._lsjson([src_parent_remote, "--no-modtime", "--files-only"])
    if not src_listing.success:
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
        return DivergenceConfirmation(
            confirmed=False,
            reason="src exists in listing — likely transient error",
        )
    return DivergenceConfirmation(
        confirmed=True,
        reason="confirmed: src absent from src_parent",
    )


def recover_diverged_rename(sync, local_src: Path, local_dst: Path, dry_run: bool) -> MoveResult:
    sync.log(f"[onedrive] divergence detected: remote source missing for {local_src.name}")

    remote_dst = sync._to_remote(local_dst)
    copy_result = sync._copyto_explicit(local_src, remote_dst, dry_run=dry_run)
    if not copy_result.success:
        return MoveResult(
            success=False,
            message=f"recovery copyto failed: {copy_result.message}",
            mode="failed",
        )
    sync.log(f"[onedrive] recovery: copyto {local_src.name} -> {remote_dst}")

    src_parent_remote = sync._to_remote(local_src.parent)
    listing = sync._lsjson([src_parent_remote, "--no-modtime", "--files-only"])
    if not listing.success:
        sync.log(
            f"[onedrive] recovery: candidate listing failed ({listing.error}); "
            f"orphan may remain at {src_parent_remote}"
        )
        return MoveResult(
            success=True,
            message="recovered: copyto only — could not list to find old name",
            mode="recovered",
        )

    old_name = sync._match_diverged_old_name(local_src, local_dst, listing.entries)
    if old_name is None:
        sync.log(f"[onedrive] recovery: no unique match — orphan may remain at {src_parent_remote}")
        return MoveResult(
            success=True,
            message="recovered: copyto only — no unique old-name match",
            mode="recovered",
        )

    if dry_run:
        sync.log(f"[onedrive] recovery: would deletefile {src_parent_remote}/{old_name} (dry-run)")
        return MoveResult(
            success=True,
            message=f"DRY-RUN: would recover via copyto + delete {old_name}",
            mode="recovered",
        )

    delete_result = sync._deletefile(f"{src_parent_remote}/{old_name}")
    if not delete_result.success:
        sync.log(f"[onedrive] recovery: deletefile failed ({delete_result.message}); orphan may remain")
        return MoveResult(
            success=True,
            message=f"recovered: copyto OK; deletefile failed: {delete_result.message}",
            mode="recovered",
        )

    sync.log(f"[onedrive] recovery: matched {old_name}; deleted")
    return MoveResult(
        success=True,
        message=f"recovered: copyto + deleted {old_name}",
        mode="recovered",
    )


def match_diverged_old_name(
    sync, local_src: Path, local_dst: Path, listing: List[dict]
) -> Optional[str]:
    meta = sync._read_recovery_metadata(local_src)
    if not meta.title or meta.track_number is None:
        sync.log(
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
            continue
        candidates.append(name_nfc)

    title_norm = sync._normalize_for_match(meta.title)
    if len(title_norm) < 3:
        sync.log(f"[onedrive] recovery: title {meta.title!r} too short for safe matching")
        sync.log(f"[onedrive] recovery: candidates in {local_src.parent}: {candidates}")
        return None

    track_re = re.compile(rf"(?<!\d)0*{meta.track_number}(?!\d)")

    matches = [
        name_nfc
        for name_nfc in candidates
        if title_norm in sync._normalize_for_match(name_nfc)
        and track_re.search(name_nfc)
    ]

    if len(matches) == 1:
        sync.log(f"[onedrive] recovery: matched {matches[0]} (unique)")
        return matches[0]

    if not matches:
        sync.log(
            f"[onedrive] recovery: no candidates matched "
            f"title={meta.title!r} + track={meta.track_number}"
        )
        sync.log(f"[onedrive] recovery: candidates in {local_src.parent}: {candidates}")
        return None

    sync.log(f"[onedrive] recovery: ambiguous — {len(matches)} candidates matched: {matches}")
    sync.log(
        f"[onedrive] recovery: skipping delete to avoid wrong-file deletion; "
        f"user must clean up manually"
    )
    return None
