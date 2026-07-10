"""Queueing and flushing of OneDrive folder syncs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List

from models import AudioFile

if TYPE_CHECKING:
    from processor import ID3Processor

logger = logging.getLogger(__name__)


def push_tag_writes_to_onedrive(proc: ID3Processor, files: List[AudioFile]) -> None:
    if proc.folder_manager.onedrive_sync is None:
        return
    for af in files:
        proc.folder_manager.queue_sync(Path(af.file_path).parent)


def maybe_flush_pending_sync(proc: ID3Processor) -> None:
    onedrive = proc.folder_manager.onedrive_sync
    pending = proc.folder_manager.pending_sync
    if onedrive is None or not pending:
        return

    if not proc.prompts.confirm_sync_pending(pending):
        return

    still_pending = []
    for folder in pending:
        result = onedrive.sync_folder(folder, dry_run=proc.args.dry_run)
        if result.success:
            proc.prompts.print(f"  Synced: {folder}")
        else:
            still_pending.append(folder)
            proc.stats.errors.append(
                f"OneDrive sync failed for {folder}: {result.message}"
            )
            proc.prompts.print(f"  OneDrive sync failed: {folder} - {result.message}")

    proc.folder_manager.pending_sync = still_pending
    logger.info(f"OneDrive sync completed. Pending folders: {len(still_pending)}")
    logger.debug(f"Pending folders: {still_pending}")
