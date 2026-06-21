"""ID3Processor — orchestrates tag management across files and folders."""

import sys
import unicodedata
from pathlib import Path
from typing import List, Optional

from audio_handler import LibrosaHandler
from models import (
    AudioFile,
    TrackMetadata,
    ProcessingStats,
    AlbumFolder,
    CollisionMap,
    ConfirmAction,
)
from id3_handler import ID3Handler
from folder_manager import FolderManager
from config import AppArgs, AppConfig
from interactive import InteractivePrompts
from onedrive_sync.protocols import RemoteSync
from acrcloud_client import ACRCloudClient
from discogs_client import DiscogsClient

from . import dispatch as _dispatch
from . import matching as _matching
from . import finalize as _finalize


class ID3Processor:
    """Main processor for ID3 tag management."""

    def __init__(
        self,
        config: AppConfig,
        args: AppArgs,
        prompts: InteractivePrompts,
        onedrive_sync: Optional[RemoteSync] = None,
    ):
        self.config = config
        self.args = args
        self.prompts = prompts
        self.stats = ProcessingStats()

        self.id3_handler = ID3Handler()
        self.folder_manager = FolderManager(onedrive_sync=onedrive_sync)

        self.acr_client = None
        if not args.skip_acr and config.get("acrcloud_host"):
            self.acr_client = ACRCloudClient(
                config["acrcloud_host"],
                config["acrcloud_access_key"],
                config["acrcloud_access_secret"],
                LibrosaHandler(),
            )

        self.discogs_client = None
        if not args.skip_discogs and config.get("discogs_user_token"):
            self.discogs_client = DiscogsClient(config["discogs_user_token"])

    def process(self, path: str) -> None:
        from config import eprint

        path_obj = Path(path)

        if path_obj.is_file():
            self._process_single_file(path)
        elif path_obj.is_dir():
            if self.args.recursive:
                self._process_recursive(path)
            else:
                self._process_folder(path)
        else:
            eprint(f"Path not found: {path}")
            sys.exit(1)

        self._review_skipped_files()
        self.prompts.show_summary(self.stats)

    def _filter_folders_from_start(
        self, folders: List[str], start_at: Optional[Path]
    ) -> List[str]:
        if start_at is None:
            return folders

        def _norm(p):
            return unicodedata.normalize("NFC", str(p))

        start_at_resolved = start_at.resolve()

        for i, folder in enumerate(folders):
            folder_resolved = Path(folder).resolve()
            if _norm(folder_resolved) == _norm(start_at_resolved):
                skipped = i
                if skipped > 0:
                    self.prompts.print(
                        f"Skipping {skipped} folder(s) before: {start_at.name}"
                    )
                return folders[i:]

        for i, folder in enumerate(folders):
            folder_resolved = Path(folder).resolve()
            if any(
                _norm(p) == _norm(start_at_resolved) for p in folder_resolved.parents
            ):
                skipped = i
                if skipped > 0:
                    self.prompts.print(
                        f"Skipping {skipped} folder(s) before: {start_at.name}"
                    )
                return folders[i:]

        self.prompts.print(f"Warning: Start folder not found in scan: {start_at}")
        return []

    def _process_recursive(self, base_path: str) -> None:
        base = Path(base_path)

        folders_to_process = set()
        for ext in ID3Handler.SUPPORTED_EXTENSIONS:
            for audio_file in base.rglob(f"*{ext}", case_sensitive=False):
                folders_to_process.add(str(audio_file.parent))

        if not self.args.include_root:
            base_str = str(base.resolve())
            folders_to_process = {
                f for f in folders_to_process if str(Path(f).resolve()) != base_str
            }

        folders_to_process = sorted(folders_to_process)

        start_at = Path(self.args.start_at) if self.args.start_at else None
        folders_to_process = self._filter_folders_from_start(
            folders_to_process, start_at
        )

        self.prompts.print(f"\nFound {len(folders_to_process)} folder(s) to process\n")

        for folder in folders_to_process:
            self._process_folder(folder)

    def _process_folder(self, folder_path: str) -> None:
        audio_files = self._discover_audio_files(folder_path)

        if not audio_files:
            self.prompts.print(f"No audio files found in: {folder_path}")
            return

        if self.args.rename_only:
            needs_rename = [af for af in audio_files if af.needs_rename]
            self.prompts.show_folder_status(
                folder_path, len(audio_files), 0, len(needs_rename)
            )
            if needs_rename:
                self._handle_file_renames(needs_rename)
            if not self.args.no_rename:
                self._handle_folder_rename(folder_path, audio_files)
            return

        disc_folders = self.folder_manager.detect_multi_disc_structure(folder_path)

        if len(disc_folders) > 1:
            for i, disc_folder in enumerate(disc_folders):
                if disc_folder.detected_disc_number is not None:
                    result = self.folder_manager.normalize_disc_folder_name(
                        disc_folder.folder_path,
                        disc_folder.detected_disc_number,
                        dry_run=self.args.dry_run,
                    )
                    if result.success and result.message != disc_folder.folder_path:
                        if not self.args.dry_run:
                            disc_folders[i] = AlbumFolder(
                                folder_path=result.message,
                                detected_disc_number=disc_folder.detected_disc_number,
                                parent_folder=disc_folder.parent_folder,
                            )
                        self.prompts.print(f"  Renamed disc folder: {result.message}")

            for disc_folder in disc_folders:
                disc_files = self._discover_audio_files(disc_folder.folder_path)
                if disc_files:
                    self._process_disc(disc_folder, disc_files)
        else:
            needs_tag_update = [af for af in audio_files if af.needs_processing]
            needs_rename = (
                [af for af in audio_files if af.needs_rename]
                if not self.args.no_file_rename
                else []
            )
            self.prompts.show_folder_status(
                folder_path, len(audio_files), len(needs_tag_update), len(needs_rename)
            )

            files_needing_work = {
                af for af in audio_files if af.needs_processing or af.needs_rename
            }
            if files_needing_work or self.args.force:
                files_to_process = (
                    audio_files if self.args.force else list(files_needing_work)
                )
                self._process_files(files_to_process)

        if not self.args.no_rename:
            self._handle_folder_rename(folder_path, audio_files)

    def _process_disc(
        self, disc_folder: AlbumFolder, audio_files: List[AudioFile]
    ) -> None:
        needs_tag_update = [af for af in audio_files if af.needs_processing]
        needs_rename = (
            [af for af in audio_files if af.needs_rename]
            if not self.args.no_file_rename
            else []
        )

        self.prompts.print(
            f"\n  Disc {disc_folder.detected_disc_number}: "
            f"{len(audio_files)} files, {len(needs_tag_update)} need tags, "
            f"{len(needs_rename)} need rename"
        )

        files_needing_work = {
            af for af in audio_files if af.needs_processing or af.needs_rename
        }
        if files_needing_work or self.args.force:
            files_to_process = (
                audio_files if self.args.force else list(files_needing_work)
            )

            for af in files_to_process:
                if af.needs_processing and af.current_tags.disc_number is None:
                    if af.proposed_tags is None:
                        af.proposed_tags = TrackMetadata()
                    af.proposed_tags.disc_number = disc_folder.detected_disc_number

            self._process_files(files_to_process)

    def _review_skipped_files(self) -> None:
        skipped = self.stats.skipped_files
        if not skipped:
            return
        self.prompts.review_skipped_files(skipped)

        files_with_changes = [af for af in skipped if af.has_actual_changes]
        if files_with_changes:
            for af in files_with_changes:
                self.prompts.show_file_comparison(af)
            result = self.prompts.confirm_tag_changes(files_with_changes)
            match result:
                case ConfirmAction.APPLY:
                    _finalize.apply_tag_changes(self, files_with_changes)
                case ConfirmAction.QUIT:
                    import sys

                    sys.exit(0)

    # --- Dispatch shims ---

    def _process_files(self, audio_files: List[AudioFile]) -> None:
        return _dispatch.process_files(self, audio_files)

    def _process_single_file(self, file_path: str) -> None:
        return _dispatch.process_single_file(self, file_path)

    def _process_single_file_obj(self, af: AudioFile, folder_release=None):
        return _dispatch.process_single_file_obj(self, af, folder_release)

    # --- Matching shims ---

    def _match_track_from_cached_release(
        self, af: AudioFile, release, acr_result
    ) -> bool:
        return _matching.match_track_from_cached_release(self, af, release, acr_result)

    def _search_and_match_discogs(self, af: AudioFile, acr_result):
        return _matching.search_and_match_discogs(self, af, acr_result)

    # --- Finalize shims ---

    def _apply_tag_changes(self, audio_files: List[AudioFile]) -> None:
        return _finalize.apply_tag_changes(self, audio_files)

    def _push_tag_writes_to_onedrive(self, files: List[AudioFile]) -> None:
        return _finalize.push_tag_writes_to_onedrive(self, files)

    def _detect_track_collisions(self, audio_files: List[AudioFile]) -> CollisionMap:
        return _finalize.detect_track_collisions(self, audio_files)

    def _backfill_disc_info(self, audio_files: List[AudioFile]) -> None:
        return _finalize.backfill_disc_info(self, audio_files)

    def _handle_file_renames(self, audio_files: List[AudioFile]) -> None:
        return _finalize.handle_file_renames(self, audio_files)

    def _handle_folder_rename(
        self, folder_path: str, audio_files: List[AudioFile]
    ) -> None:
        return _finalize.handle_folder_rename(self, folder_path, audio_files)

    def _discover_audio_files(self, folder_path: str) -> List[AudioFile]:
        return _finalize.discover_audio_files(self, folder_path)
