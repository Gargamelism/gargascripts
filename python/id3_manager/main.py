#!/usr/bin/env python3
"""
ID3 Manager - Audio tag management with ACRCloud and Discogs integration.

Usage:
    python main.py /path/to/album [options]
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from config import (
    load_config, validate_config, eprint,
    get_discogs_token_instructions, get_acrcloud_instructions
)
from models import (
    AudioFile, TrackMetadata, ProcessingStats, AlbumFolder, TagStatus
)
from acrcloud_client import ACRCloudClient
from discogs_client import DiscogsClient
from id3_handler import ID3Handler
from folder_manager import FolderManager
from interactive import InteractivePrompts


class ID3Processor:
    """Main processor for ID3 tag management."""

    def __init__(self, config: dict, args: argparse.Namespace,
                 prompts: InteractivePrompts):
        """
        Initialize processor.

        Args:
            config: Configuration dictionary
            args: CLI arguments
            prompts: Interactive prompts handler
        """
        self.config = config
        self.args = args
        self.prompts = prompts
        self.stats = ProcessingStats()

        # Initialize clients
        self.id3_handler = ID3Handler()
        self.folder_manager = FolderManager()

        self.acr_client = None
        if not args.skip_acr and config.get("acrcloud_host"):
            self.acr_client = ACRCloudClient(
                config["acrcloud_host"],
                config["acrcloud_access_key"],
                config["acrcloud_access_secret"]
            )

        self.discogs_client = None
        if not args.skip_discogs and config.get("discogs_user_token"):
            self.discogs_client = DiscogsClient(config["discogs_user_token"])

    def process(self, path: str) -> None:
        """
        Main entry point for processing.

        Args:
            path: Path to process (file or folder)
        """
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

        self.prompts.show_summary(self.stats)

    def _filter_folders_from_start(
        self,
        folders: List[str],
        start_at: Optional[Path]
    ) -> List[str]:
        """Filter folder list to start from a specific folder.

        Args:
            folders: Sorted list of folder paths to process
            start_at: Folder path to start from, or None to include all

        Returns:
            List of folders from start_at onwards (or all if start_at is None)
        """
        if start_at is None:
            return folders

        start_at_resolved = start_at.resolve()

        for i, folder in enumerate(folders):
            folder_resolved = Path(folder).resolve()
            if folder_resolved == start_at_resolved:
                skipped = i
                if skipped > 0:
                    self.prompts.print(f"Skipping {skipped} folder(s) before: {start_at.name}")
                return folders[i:]

        # start_at folder not found in list
        self.prompts.print(f"Warning: Start folder not found in scan: {start_at}")
        return []

    def _process_recursive(self, base_path: str) -> None:
        """Process all subfolders recursively."""
        base = Path(base_path)

        # Find all folders containing audio files
        folders_to_process = set()

        for ext in ID3Handler.SUPPORTED_EXTENSIONS:
            for audio_file in base.rglob(f"*{ext}"):
                folders_to_process.add(str(audio_file.parent))

        # Skip root folder unless --include-root is specified
        if not self.args.include_root:
            base_str = str(base.resolve())
            folders_to_process = {f for f in folders_to_process
                                  if str(Path(f).resolve()) != base_str}

        folders_to_process = sorted(folders_to_process)

        # Filter to start from specified folder if --start-at is provided
        start_at = Path(self.args.start_at) if self.args.start_at else None
        folders_to_process = self._filter_folders_from_start(folders_to_process, start_at)

        self.prompts.print(f"\nFound {len(folders_to_process)} folder(s) to process\n")

        for folder in folders_to_process:
            self._process_folder(folder)

    def _process_folder(self, folder_path: str) -> None:
        """Process a single folder (album)."""
        # Discover audio files
        audio_files = self._discover_audio_files(folder_path)

        if not audio_files:
            self.prompts.print(f"No audio files found in: {folder_path}")
            return

        # Check for multi-disc structure
        disc_folders = self.folder_manager.detect_multi_disc_structure(folder_path)

        if len(disc_folders) > 1:
            # Normalize disc folder names to CD{N} format
            for i, disc_folder in enumerate(disc_folders):
                if disc_folder.detected_disc_number is not None:
                    success, result = self.folder_manager.normalize_disc_folder_name(
                        disc_folder.folder_path,
                        disc_folder.detected_disc_number,
                        dry_run=self.args.dry_run
                    )
                    if success and result != disc_folder.folder_path:
                        if not self.args.dry_run:
                            # Update the folder path in the AlbumFolder object
                            disc_folders[i] = AlbumFolder(
                                folder_path=result,
                                detected_disc_number=disc_folder.detected_disc_number,
                                parent_folder=disc_folder.parent_folder
                            )
                        self.prompts.print(f"  Renamed disc folder: {result}")

            # Process each disc folder separately
            for disc_folder in disc_folders:
                disc_files = self._discover_audio_files(disc_folder.folder_path)
                if disc_files:
                    self._process_disc(disc_folder, disc_files)
        else:
            # Single folder processing
            needs_tag_update = [af for af in audio_files if af.needs_processing]
            needs_rename = [af for af in audio_files if af.needs_rename] if not self.args.no_file_rename else []
            self.prompts.show_folder_status(
                folder_path, len(audio_files), len(needs_tag_update), len(needs_rename)
            )

            # Process files needing either tag updates or renaming
            files_needing_work = {af for af in audio_files if af.needs_processing or af.needs_rename}
            if files_needing_work or self.args.force:
                files_to_process = audio_files if self.args.force else list(files_needing_work)
                self._process_files(files_to_process)

        # Handle folder renaming
        if not self.args.no_rename:
            self._handle_folder_rename(folder_path, audio_files)

    def _process_disc(self, disc_folder: AlbumFolder,
                      audio_files: List[AudioFile]) -> None:
        """Process a single disc of a multi-disc album."""
        needs_tag_update = [af for af in audio_files if af.needs_processing]
        needs_rename = [af for af in audio_files if af.needs_rename] if not self.args.no_file_rename else []

        self.prompts.print(f"\n  Disc {disc_folder.detected_disc_number}: "
                          f"{len(audio_files)} files, {len(needs_tag_update)} need tags, "
                          f"{len(needs_rename)} need rename")

        # Process files needing either tag updates or renaming
        files_needing_work = {af for af in audio_files if af.needs_processing or af.needs_rename}
        if files_needing_work or self.args.force:
            files_to_process = audio_files if self.args.force else list(files_needing_work)

            # Set disc number for files needing tag updates
            for af in files_to_process:
                if af.needs_processing and af.current_tags.disc_number is None:
                    if af.proposed_tags is None:
                        af.proposed_tags = TrackMetadata()
                    af.proposed_tags.disc_number = disc_folder.detected_disc_number

            self._process_files(files_to_process)

    def _process_files(self, audio_files: List[AudioFile]) -> None:
        """Process a list of audio files."""
        from models import DiscogsRelease
        folder_release: Optional[DiscogsRelease] = None  # Cached release for folder

        for i, af in enumerate(audio_files):
            self.prompts.show_progress(i + 1, len(audio_files),
                                       Path(af.file_path).name)
            folder_release = self._process_single_file_obj(af, folder_release)
            self.stats.files_processed += 1

        # Confirm and apply changes
        files_with_changes = [af for af in audio_files if af.proposed_tags]

        if files_with_changes:
            # Show all proposed changes
            for af in files_with_changes:
                self.prompts.show_file_comparison(af)

            result = self.prompts.confirm_tag_changes(files_with_changes)

            if result == "apply":
                self._apply_tag_changes(files_with_changes)
            elif result == "quit":
                sys.exit(0)
            else:
                self.stats.files_skipped += len(files_with_changes)

        # Handle files that only need renaming (complete tags, no proposed changes)
        if not self.args.no_file_rename:
            files_only_needing_rename = [
                af for af in audio_files
                if not af.proposed_tags and af.needs_rename
            ]
            if files_only_needing_rename:
                self._handle_file_renames(files_only_needing_rename)

    def _process_single_file(self, file_path: str) -> None:
        """Process a single audio file."""
        if not ID3Handler.is_supported(file_path):
            eprint(f"Unsupported format: {file_path}")
            return

        af = AudioFile(
            file_path=file_path,
            format=ID3Handler.get_format(file_path) or "unknown",
            current_tags=self.id3_handler.read_tags(file_path)
        )

        self._process_single_file_obj(af)

        if af.proposed_tags:
            self.prompts.show_file_comparison(af)
            result = self.prompts.confirm_tag_changes([af])

            if result == "apply":
                self._apply_tag_changes([af])
            elif result == "quit":
                sys.exit(0)
        elif not self.args.no_file_rename and af.needs_rename:
            # File has complete tags but needs renaming
            self._handle_file_renames([af])

    def _process_single_file_obj(self, af: AudioFile,
                                  folder_release=None):
        """
        Process a single AudioFile object.

        Args:
            af: Audio file to process
            folder_release: Cached DiscogsRelease from previous file in folder

        Returns:
            The selected DiscogsRelease for caching, or the existing folder_release
        """
        self.stats.total_files += 1

        # Skip tag lookups if file only needs renaming (tags already complete)
        if not af.needs_processing and not self.args.force:
            # File has complete tags, just needs rename - skip ACRCloud/Discogs
            return folder_release

        # Try ACRCloud recognition
        acr_result = None
        if self.acr_client:
            self.prompts.print(f"\n  Identifying: {Path(af.file_path).name}")
            acr_result = self.acr_client.recognize_with_retry(af.file_path)
            self.stats.acr_lookups += 1
            af.acr_result = acr_result

            if acr_result:
                self.prompts.show_acr_result(acr_result)

        # Handle no ACRCloud match
        if not acr_result and self.acr_client:
            action = self.prompts.handle_no_acr_match(af.file_path)

            if action == "manual":
                manual_tags = self.prompts.get_manual_metadata(af.current_tags)
                if manual_tags:
                    af.proposed_tags = manual_tags
                else:
                    self.stats.files_skipped += 1
                return folder_release
            elif action == "existing":
                # Use existing tags for Discogs search
                if af.current_tags.artist:
                    acr_result = type("ACRResult", (), {
                        "title": af.current_tags.title or "",
                        "artists": [af.current_tags.artist],
                        "album": af.current_tags.album,
                        "confidence": 0.0
                    })()
                else:
                    self.stats.files_skipped += 1
                    return folder_release
            elif action == "skip":
                self.stats.files_skipped += 1
                return folder_release
            elif action == "quit":
                sys.exit(0)

        if not acr_result:
            return folder_release

        # Search Discogs
        if self.discogs_client:
            # Try cached release first
            if folder_release:
                if self._match_track_from_cached_release(af, folder_release, acr_result):
                    return folder_release  # Matched - keep using this release
                else:
                    # No match in cached release - offer options
                    action = self.prompts.handle_track_not_in_release(
                        Path(af.file_path).name, folder_release.title
                    )
                    if action == "search":
                        # Do fresh Discogs search
                        selected_release = self._search_and_match_discogs(af, acr_result)
                        return selected_release or folder_release
                    elif action == "skip":
                        self.stats.files_skipped += 1
                        return folder_release
                    elif action == "quit":
                        sys.exit(0)
            else:
                # First file - do full search
                selected_release = self._search_and_match_discogs(af, acr_result)
                return selected_release
        else:
            # ACRCloud only - create basic tags
            af.proposed_tags = TrackMetadata(
                title=acr_result.title,
                artist=acr_result.artists[0] if acr_result.artists else None,
                album=acr_result.album,
            )

        return folder_release

    def _match_track_from_cached_release(self, af: AudioFile,
                                          release,
                                          acr_result) -> bool:
        """
        Try to match file to a track in the cached release.

        Args:
            af: Audio file to process
            release: Cached DiscogsRelease to match against
            acr_result: ACRCloud result for the file

        Returns:
            True if match found and proposed_tags set
        """
        # Try matching with ACRCloud title first
        track = self.discogs_client.match_track_to_release(release, acr_result.title)

        # If no match, try with existing file title tag
        if (not track or not track.track_number) and af.current_tags.title:
            track = self.discogs_client.match_track_to_release(
                release, af.current_tags.title
            )

        if track and track.track_number:
            af.discogs_release = release
            af.discogs_track = track

            # Build proposed tags
            proposed = TrackMetadata(
                title=track.title,
                artist=release.artists[0] if release.artists else None,
                album=release.title,
                album_artist=release.artists[0] if release.artists else None,
                track_number=track.track_number,
                total_tracks=len(release.tracklist),
                disc_number=track.disc_number,
                total_discs=release.total_discs if release.total_discs > 1 else None,
                year=release.year,
                genre=release.genres[0] if release.genres else None,
            )

            # Check for missing required fields and prompt user
            proposed = self.prompts.prompt_missing_fields(
                proposed, Path(af.file_path).name
            )

            if proposed:
                af.proposed_tags = proposed
                return True

        return False

    def _search_and_match_discogs(self, af: AudioFile, acr_result):
        """
        Search Discogs and match track.

        Args:
            af: Audio file to process
            acr_result: ACRCloud result for the file

        Returns:
            Selected DiscogsRelease for caching, or None
        """
        artist = acr_result.artists[0] if acr_result.artists else None
        if not artist:
            return None

        releases = self.discogs_client.find_best_release(
            artist=artist,
            album=acr_result.album,
            track=acr_result.title
        )
        self.stats.discogs_lookups += 1

        if not releases:
            action = self.prompts.handle_no_discogs_match(acr_result)

            if action == "acr_only":
                af.proposed_tags = TrackMetadata(
                    title=acr_result.title,
                    artist=artist,
                    album=acr_result.album,
                )
                return None
            elif action == "retry":
                new_artist, new_track = self.prompts.get_modified_search_query(
                    artist, acr_result.title
                )
                releases = self.discogs_client.find_best_release(
                    artist=new_artist, track=new_track
                )
                self.stats.discogs_lookups += 1
            elif action == "manual_url":
                release_id = self.prompts.get_discogs_url_or_id()
                if release_id:
                    release = self.discogs_client.get_release(release_id)
                    self.stats.discogs_lookups += 1
                    if release:
                        releases = [release]
                        discogs_url = f"https://www.discogs.com/release/{release.release_id}"
                        self.prompts.print(f"  Fetched: {release.title} ({release.year})")
                        self.prompts.print(f"  {discogs_url}")
                    else:
                        self.prompts.print("  Could not fetch release.")
                        self.stats.files_skipped += 1
                        return None
                else:
                    self.stats.files_skipped += 1
                    return None
            elif action == "manual":
                manual_tags = self.prompts.get_manual_metadata()
                if manual_tags:
                    af.proposed_tags = manual_tags
                return None
            elif action == "skip":
                self.stats.files_skipped += 1
                return None
            elif action == "quit":
                sys.exit(0)

        if not releases:
            return None

        # Filter releases to only those where we can match the track
        matchable_releases = []
        for release in releases:
            track = self.discogs_client.match_track_to_release(release, acr_result.title)
            if track and track.track_number:
                matchable_releases.append((release, track))

        while not matchable_releases:
            # No releases with matching tracks - treat as no match
            action = self.prompts.handle_no_discogs_match(acr_result)

            if action == "acr_only":
                proposed = TrackMetadata(
                    title=acr_result.title,
                    artist=artist,
                    album=acr_result.album,
                )
                # Merge with existing tags and validate
                proposed = proposed.merge_with(af.current_tags)
                proposed = self.prompts.prompt_missing_fields(proposed, Path(af.file_path).name)
                if proposed is None:
                    self.stats.files_skipped += 1
                    return None
                af.proposed_tags = proposed
                return None
            elif action == "manual_url":
                release_id = self.prompts.get_discogs_url_or_id()
                if release_id:
                    release = self.discogs_client.get_release(release_id)
                    self.stats.discogs_lookups += 1
                    if release:
                        # Try to match track in manually entered release
                        track = self.discogs_client.match_track_to_release(release, acr_result.title)
                        matchable_releases = [(release, track)]
                    else:
                        self.prompts.print("  Could not fetch release.")
                else:
                    continue
            elif action == "retry":
                new_artist, new_track = self.prompts.get_modified_search_query(
                    artist, acr_result.title
                )
                releases = self.discogs_client.find_best_release(
                    artist=new_artist, track=new_track
                )
                self.stats.discogs_lookups += 1
                # Re-filter releases to only those where we can match the track
                matchable_releases = []
                for release in releases:
                    track = self.discogs_client.match_track_to_release(release, acr_result.title)
                    if track and track.track_number:
                        matchable_releases.append((release, track))
                # If still no matchable releases, loop will continue and show menu again
                if not matchable_releases:
                    self.prompts.print("  No matching releases found.")
            elif action == "manual":
                manual_tags = self.prompts.get_manual_metadata(af.current_tags)
                if manual_tags:
                    af.proposed_tags = manual_tags
                else:
                    self.stats.files_skipped += 1
                return None
            elif action == "skip":
                self.stats.files_skipped += 1
                return None
            elif action == "quit":
                sys.exit(0)
            else:
                return None

        # Extract just releases for display
        display_releases = [r for r, _ in matchable_releases]

        # Let user select release
        selected = self.prompts.show_discogs_candidates(display_releases)

        if selected is None:
            self.stats.files_skipped += 1
            return None

        # Handle manual URL entry
        if selected == "manual_url":
            release_id = self.prompts.get_discogs_url_or_id()
            if release_id:
                release = self.discogs_client.get_release(release_id)
                self.stats.discogs_lookups += 1
                if release:
                    discogs_url = f"https://www.discogs.com/release/{release.release_id}"
                    self.prompts.print(f"  Fetched: {release.title} ({release.year})")
                    self.prompts.print(f"  {discogs_url}")
                    track = self.discogs_client.match_track_to_release(release, acr_result.title)
                else:
                    self.prompts.print("  Could not fetch release.")
                    self.stats.files_skipped += 1
                    return None
            else:
                self.stats.files_skipped += 1
                return None
        else:
            # Use pre-matched release and track
            release, track = matchable_releases[selected]

        af.discogs_release = release
        af.discogs_track = track

        # Build proposed tags
        proposed = TrackMetadata(
            title=track.title if track else acr_result.title,
            artist=release.artists[0] if release.artists else artist,
            album=release.title,
            album_artist=release.artists[0] if release.artists else None,
            track_number=track.track_number if track else None,
            total_tracks=len(release.tracklist),
            disc_number=track.disc_number if track else None,
            total_discs=release.total_discs if release.total_discs > 1 else None,
            year=release.year,
            genre=release.genres[0] if release.genres else None,
        )

        # Check for missing required fields and prompt user
        filename = Path(af.file_path).name
        proposed = self.prompts.prompt_missing_fields(proposed, filename)

        if proposed is None:
            # User chose to skip
            self.stats.files_skipped += 1
            return None

        af.proposed_tags = proposed
        return release  # Return selected release for caching

    def _apply_tag_changes(self, audio_files: List[AudioFile]) -> None:
        """Apply proposed tag changes to files."""
        for af in audio_files:
            if af.proposed_tags:
                if self.args.dry_run:
                    self.prompts.print(f"  [DRY RUN] Would update: {Path(af.file_path).name}")
                else:
                    success = self.id3_handler.write_tags(
                        af.file_path, af.proposed_tags, preserve_existing=True
                    )
                    if success:
                        self.stats.tags_updated += 1
                        self.prompts.print(f"  Updated: {Path(af.file_path).name}")
                    else:
                        self.stats.errors.append(f"Failed to write tags: {af.file_path}")

        # Handle file renaming (unless disabled)
        if not self.args.no_file_rename:
            self._handle_file_renames(audio_files)

    def _handle_file_renames(self, audio_files: List[AudioFile]) -> None:
        """Handle file renaming based on metadata."""
        # Collect files that need renaming
        renames = []
        for af in audio_files:
            # Use proposed tags if available, else current tags
            metadata = af.proposed_tags or af.current_tags

            # Check if file needs renaming
            if not self.folder_manager.should_rename_file(af.file_path, metadata):
                continue

            extension = Path(af.file_path).suffix
            new_name = self.folder_manager.generate_filename(metadata, extension)

            if new_name:
                renames.append((af.file_path, new_name))

        if not renames:
            return

        # Confirm renames
        if not self.prompts.confirm_file_renames(renames):
            return

        # Apply renames
        for file_path, new_name in renames:
            if self.args.dry_run:
                self.prompts.print(f"  [DRY RUN] Would rename: {Path(file_path).name} -> {new_name}")
            else:
                success, result = self.folder_manager.rename_audio_file(
                    file_path, new_name
                )
                if success:
                    if result == "File already has correct name":
                        self.prompts.print(f"  Skipped (already correct): {Path(file_path).name}")
                    else:
                        self.prompts.print(f"  Renamed: {Path(file_path).name} -> {new_name}")
                else:
                    self.prompts.print(f"  Failed: {Path(file_path).name} - {result}")
                    self.stats.errors.append(f"Failed to rename {file_path}: {result}")

    def _handle_folder_rename(self, folder_path: str,
                              audio_files: List[AudioFile]) -> None:
        """Handle folder renaming after processing."""
        if self.folder_manager.is_folder_properly_named(folder_path):
            return

        # Get album info from processed files
        year, album = self.folder_manager.get_album_info_from_files(audio_files)

        if not year or not album:
            self.prompts.print("\nCannot determine album year/name for folder rename.")
            return

        # Check for multi-disc from metadata
        total_discs = self.folder_manager.detect_multi_disc_from_metadata(audio_files)

        if total_discs > 1:
            # Multi-disc album - may need restructuring
            new_name = self.folder_manager.generate_folder_name(year, album)
            current_name = Path(folder_path).name

            if self.prompts.confirm_folder_rename(current_name, f"{new_name}/CD1-CD{total_discs}"):
                if self.args.dry_run:
                    self.prompts.print(f"  [DRY RUN] Would reorganize to: {new_name}/")
                else:
                    success, msg = self.folder_manager.reorganize_multi_disc_album(
                        folder_path, audio_files, year, album, self.args.dry_run
                    )
                    if success:
                        self.stats.folders_renamed += 1
                        self.prompts.print(f"  Reorganized to: {msg}")
                    else:
                        self.stats.errors.append(msg)
        else:
            # Single disc - simple rename
            new_name = self.folder_manager.generate_folder_name(year, album)
            current_name = Path(folder_path).name

            if current_name != new_name:
                if self.prompts.confirm_folder_rename(current_name, new_name):
                    if self.args.dry_run:
                        self.prompts.print(f"  [DRY RUN] Would rename to: {new_name}")
                    else:
                        success, msg = self.folder_manager.rename_folder(
                            folder_path, new_name
                        )
                        if success:
                            self.stats.folders_renamed += 1
                            self.prompts.print(f"  Renamed to: {new_name}")
                        else:
                            self.stats.errors.append(msg)

    def _discover_audio_files(self, folder_path: str) -> List[AudioFile]:
        """Discover and load audio files from folder."""
        audio_files = []
        folder = Path(folder_path)

        for file_path in folder.iterdir():
            if file_path.is_file() and ID3Handler.is_supported(str(file_path)):
                try:
                    current_tags = self.id3_handler.read_tags(str(file_path))
                    af = AudioFile(
                        file_path=str(file_path),
                        format=ID3Handler.get_format(str(file_path)) or "unknown",
                        current_tags=current_tags
                    )
                    audio_files.append(af)
                except Exception as e:
                    # Track malformed/unreadable files
                    self.stats.malformed_files.append(str(file_path))
                    eprint(f"Malformed file (skipping): {file_path.name} - {e}")

        # Sort by track number if available, else by filename
        audio_files.sort(key=lambda af: (
            af.current_tags.disc_number or 0,
            af.current_tags.track_number or 999,
            Path(af.file_path).name
        ))

        return audio_files


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="ID3 tag manager: identify songs via ACRCloud, "
                    "fetch metadata from Discogs, and organize album folders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single album folder
  python -m id3_manager /path/to/album

  # Process with auto-confirmation
  python -m id3_manager /path/to/album --yes

  # Dry run to preview changes
  python -m id3_manager /path/to/album --dry-run

  # Process recursively
  python -m id3_manager /path/to/music --recursive

  # Skip folder renaming
  python -m id3_manager /path/to/album --no-rename
"""
    )

    # Required arguments
    parser.add_argument(
        "path",
        help="Path to audio file or folder to process"
    )

    # Processing options
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Recursively process all subfolders"
    )

    parser.add_argument(
        "--include-root",
        action="store_true",
        help="Include files in root folder when using --recursive (skipped by default)"
    )

    parser.add_argument(
        "--start-at",
        help="When using --recursive, start processing from this folder path (skips earlier folders)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying them"
    )

    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Auto-confirm all changes (non-interactive)"
    )

    # Tag handling
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process files even if they have complete tags"
    )

    parser.add_argument(
        "--skip-acr",
        action="store_true",
        help="Skip ACRCloud lookup (use existing tags for Discogs search)"
    )

    parser.add_argument(
        "--skip-discogs",
        action="store_true",
        help="Skip Discogs lookup (use ACRCloud results only)"
    )

    # Folder handling
    parser.add_argument(
        "--no-rename",
        action="store_true",
        help="Skip folder renaming step"
    )

    parser.add_argument(
        "--no-file-rename",
        action="store_true",
        help="Skip file renaming step"
    )

    # Configuration
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: ./.env)"
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )

    # Verbosity
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-essential output"
    )

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate path
    if not os.path.exists(args.path):
        parser.error(f"Path does not exist: {args.path}")

    # Validate --start-at usage
    if args.start_at:
        if not args.recursive:
            eprint("Warning: --start-at has no effect without --recursive")
        elif not os.path.exists(args.start_at):
            parser.error(f"Start folder does not exist: {args.start_at}")
        elif not os.path.isdir(args.start_at):
            parser.error(f"Start path is not a folder: {args.start_at}")

    # Load configuration
    config = load_config(args.env_file)
    missing = validate_config(config, args.skip_acr, args.skip_discogs)

    if missing:
        eprint(f"\nMissing required credentials: {', '.join(missing)}")
        if "DISCOGS_USER_TOKEN" in missing:
            eprint(get_discogs_token_instructions())
        if any("ACRCLOUD" in m for m in missing):
            eprint(get_acrcloud_instructions())
        eprint("Use --skip-acr or --skip-discogs to proceed without them.\n")
        sys.exit(1)

    # Initialize prompts
    prompts = InteractivePrompts(
        no_color=args.no_color,
        auto_yes=args.yes,
        quiet=args.quiet
    )

    # Run processor
    processor = ID3Processor(config, args, prompts)

    try:
        processor.process(args.path)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
