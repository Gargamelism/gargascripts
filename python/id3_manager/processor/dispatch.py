"""Per-file and per-batch processing dispatch."""

import sys
from pathlib import Path
from typing import List, Optional, Set

from config import eprint
from models import (
    AudioFile, TrackMetadata, ConfirmAction, CollisionMap,
)
from id3_handler import ID3Handler


def process_files(proc, audio_files: List[AudioFile]) -> None:
    from models import DiscogsRelease
    folder_release: Optional[DiscogsRelease] = None

    for i, af in enumerate(audio_files):
        proc.prompts.show_progress(i + 1, len(audio_files), Path(af.file_path).name)
        folder_release = proc._process_single_file_obj(af, folder_release)
        proc.stats.files_processed += 1

    proc._backfill_disc_info(audio_files)

    conflicting: Set[AudioFile] = set()
    collisions: CollisionMap = proc._detect_track_collisions(audio_files)
    while collisions:
        action: str = proc.prompts.confirm_collision_resolution(collisions)
        if action == "quit":
            sys.exit(0)
        if action == "edit":
            proc.prompts.edit_collision_files(collisions)
            collisions = proc._detect_track_collisions(audio_files)
            continue
        if action == "skip":
            conflicting = {af for grp in collisions.values() for af in grp}
            for af in conflicting:
                af.proposed_tags = None
            proc.stats.files_skipped += len(conflicting)
        break

    files_with_changes = [af for af in audio_files if af.has_actual_changes]

    if files_with_changes:
        for af in files_with_changes:
            proc.prompts.show_file_comparison(af)

        result = proc.prompts.confirm_tag_changes(files_with_changes)

        match result:
            case ConfirmAction.APPLY:
                proc._apply_tag_changes(files_with_changes)
            case ConfirmAction.QUIT:
                sys.exit(0)
            case _:
                proc.stats.files_skipped += len(files_with_changes)

    if not proc.args.no_file_rename:
        files_only_needing_rename = [
            af for af in audio_files
            if not af.has_actual_changes and af.needs_rename and af not in conflicting
        ]
        if files_only_needing_rename:
            proc._handle_file_renames(files_only_needing_rename)


def process_single_file(proc, file_path: str) -> None:
    if not ID3Handler.is_supported(file_path):
        eprint(f"Unsupported format: {file_path}")
        return

    af = AudioFile(
        file_path=file_path,
        format=ID3Handler.get_format(file_path) or "unknown",
        current_tags=proc.id3_handler.read_tags(file_path)
    )

    if proc.args.rename_only:
        if af.needs_rename:
            proc._handle_file_renames([af])
        return

    proc._process_single_file_obj(af)

    if af.has_actual_changes:
        proc.prompts.show_file_comparison(af)
        result = proc.prompts.confirm_tag_changes([af])

        match result:
            case ConfirmAction.APPLY:
                proc._apply_tag_changes([af])
            case ConfirmAction.QUIT:
                sys.exit(0)
    elif not proc.args.no_file_rename and af.needs_rename:
        proc._handle_file_renames([af])


def process_single_file_obj(proc, af: AudioFile, folder_release=None):
    proc.stats.total_files += 1

    if not af.needs_processing and not proc.args.force:
        return folder_release

    acr_result = None
    if proc.acr_client:
        proc.prompts.print(f"\n  Identifying: {Path(af.file_path).name}")
        acr_result = proc.acr_client.recognize_with_retry(af.file_path)
        proc.stats.acr_lookups += 1
        af.acr_result = acr_result

        if acr_result:
            proc.prompts.show_acr_result(acr_result)

    if not acr_result and proc.acr_client:
        action = proc.prompts.handle_no_acr_match(af.file_path)

        if action == "manual":
            manual_tags = proc.prompts.get_manual_metadata(af.current_tags)
            if manual_tags:
                af.proposed_tags = manual_tags
            else:
                proc.stats.files_skipped += 1
            return folder_release
        elif action == "existing":
            title = af.current_tags.title or ""
            artist = af.current_tags.artist or ""
            album = af.current_tags.album

            if not artist:
                proc.prompts.print(
                    f"  Existing tags — title: '{title}', album: '{album or ''}'"
                )
                artist, title = proc.prompts.get_modified_search_query(artist, title)

            if artist:
                acr_result = type("ACRResult", (), {
                    "title": title,
                    "artists": [artist],
                    "album": album,
                    "confidence": 0.0
                })()
            else:
                proc.prompts.print("  No artist provided, skipping.")
                proc.stats.files_skipped += 1
                return folder_release
        elif action == "skip":
            proc.stats.files_skipped += 1
            return folder_release
        elif action == "quit":
            sys.exit(0)

    if not acr_result:
        return folder_release

    if proc.discogs_client:
        if folder_release:
            if proc._match_track_from_cached_release(af, folder_release, acr_result):
                return folder_release
            else:
                action = proc.prompts.handle_track_not_in_release(
                    Path(af.file_path).name, folder_release.title
                )
                if action == "search":
                    selected_release = proc._search_and_match_discogs(af, acr_result)
                    return selected_release or folder_release
                elif action == "skip":
                    proc.stats.files_skipped += 1
                    return folder_release
                elif action == "quit":
                    sys.exit(0)
        else:
            selected_release = proc._search_and_match_discogs(af, acr_result)
            return selected_release
    else:
        af.proposed_tags = TrackMetadata(
            title=acr_result.title,
            artist=acr_result.artists[0] if acr_result.artists else None,
            album=acr_result.album,
        )

    return folder_release
