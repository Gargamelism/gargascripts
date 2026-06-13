"""Tag application, file/folder renames, collision detection, and discovery."""

from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Dict, List

from config import eprint
from models import AudioFile, CollisionMap, DiscTrack
from id3_handler import ID3Handler


def apply_tag_changes(proc, audio_files: List[AudioFile]) -> None:
    write_failed = False
    for af in audio_files:
        if af.proposed_tags:
            if proc.args.dry_run:
                proc.prompts.print(
                    f"  [DRY RUN] Would update: {Path(af.file_path).name}"
                )
            else:
                try:
                    success = proc.id3_handler.write_tags(
                        af.file_path, af.proposed_tags, preserve_existing=True
                    )
                except RuntimeError as e:
                    proc.stats.errors.append(str(e))
                    proc.prompts.print(f"  Error: {e}")
                    write_failed = True
                    break
                if success:
                    proc.prompts.print(f"  Updated: {Path(af.file_path).name}")
                    proc.stats.tagged_files.append(af)
                else:
                    proc.stats.errors.append(f"Failed to write tags: {af.file_path}")

    if not write_failed and not proc.args.no_file_rename:
        proc._handle_file_renames(audio_files)

    if proc.stats.tagged_files and not proc.args.dry_run:
        proc._push_tag_writes_to_onedrive(proc.stats.tagged_files)


def push_tag_writes_to_onedrive(proc, files: List[AudioFile]) -> None:
    onedrive = proc.folder_manager.onedrive_sync
    if onedrive is None:
        return
    for af in files:
        result = onedrive.copyto(Path(af.file_path), dry_run=proc.args.dry_run)
        if not result.success:
            proc.stats.errors.append(
                f"OneDrive push failed for {af.file_path}: {result.message}"
            )
            proc.prompts.print(
                f"  OneDrive push failed: {Path(af.file_path).name} - {result.message}"
            )
        elif not result.message.startswith("skipped"):
            proc.prompts.print(f"  Pushed: {Path(af.file_path).name}")


def detect_track_collisions(proc, audio_files: List[AudioFile]) -> CollisionMap:
    buckets: Dict[DiscTrack, List[AudioFile]] = defaultdict(list)
    for af in audio_files:
        tags = af.proposed_tags or af.current_tags
        if tags.track_number is None:
            continue
        disc = tags.disc_number if tags.disc_number is not None else 1
        buckets[DiscTrack(disc=disc, track=tags.track_number)].append(af)
    return {key: files for key, files in buckets.items() if len(files) > 1}


def backfill_disc_info(proc, audio_files: List[AudioFile]) -> None:
    for af in audio_files:
        tags = af.proposed_tags or af.current_tags
        if tags.disc_number and tags.total_discs and tags.total_discs > 1:
            continue
        disc_info = proc.folder_manager.infer_disc_info_from_path(af.file_path)
        if disc_info:
            af.proposed_tags = replace(
                tags,
                disc_number=tags.disc_number or disc_info[0],
                total_discs=disc_info[1],
            )


def handle_file_renames(proc, audio_files: List[AudioFile]) -> None:
    renames = []
    for af in audio_files:
        metadata = af.proposed_tags or af.current_tags
        if not proc.folder_manager.should_rename_file(af.file_path, metadata):
            continue
        extension = Path(af.file_path).suffix.lower()
        new_name = proc.folder_manager.generate_filename(metadata, extension)
        if new_name:
            renames.append((af, new_name))

    if not renames:
        return

    if not proc.prompts.confirm_file_renames(
        [(af.file_path, new_name) for af, new_name in renames]
    ):
        return

    for af, new_name in renames:
        file_path = af.file_path
        if proc.args.dry_run:
            proc.prompts.print(
                f"  [DRY RUN] Would rename: {Path(file_path).name} -> {new_name}"
            )
        else:
            commit = proc.folder_manager.rename_audio_file(file_path, new_name)
            if commit.success:
                if commit.message == "File already has correct name":
                    proc.prompts.print(
                        f"  Skipped (already correct): {Path(file_path).name}"
                    )
                else:
                    af.file_path = str(Path(file_path).parent / new_name)
                    proc.prompts.print(
                        f"  Renamed: {Path(file_path).name} -> {new_name}"
                    )
            else:
                proc.prompts.print(
                    f"  Failed: {Path(file_path).name} - {commit.message}"
                )
                proc.stats.errors.append(
                    f"Failed to rename {file_path}: {commit.message}"
                )


def handle_folder_rename(proc, folder_path: str, audio_files: List[AudioFile]) -> None:
    year, album = proc.folder_manager.get_album_info_from_files(audio_files)

    if not year or not album:
        if proc.folder_manager.is_folder_properly_named(folder_path):
            return
        proc.prompts.print("\nCannot determine album year/name for folder rename.")
        return

    expected_name = proc.folder_manager.generate_folder_name(year, album)
    if Path(folder_path).name == expected_name:
        return

    total_discs = proc.folder_manager.detect_multi_disc_from_metadata(audio_files)

    if total_discs > 1:
        new_name = proc.folder_manager.generate_folder_name(year, album)
        current_name = Path(folder_path).name

        if proc.prompts.confirm_folder_rename(
            current_name, f"{new_name}/CD1-CD{total_discs}"
        ):
            if proc.args.dry_run:
                proc.prompts.print(f"  [DRY RUN] Would reorganize to: {new_name}/")
            else:
                success, msg = proc.folder_manager.reorganize_multi_disc_album(
                    folder_path, audio_files, year, album, proc.args.dry_run
                )
                if success:
                    proc.stats.renamed_folders.append(folder_path)
                    proc.prompts.print(f"  Reorganized to: {msg}")
                else:
                    proc.stats.errors.append(msg)
    else:
        new_name = proc.folder_manager.generate_folder_name(year, album)
        current_name = Path(folder_path).name

        if current_name != new_name:
            if proc.prompts.confirm_folder_rename(current_name, new_name):
                if proc.args.dry_run:
                    proc.prompts.print(f"  [DRY RUN] Would rename to: {new_name}")
                else:
                    commit = proc.folder_manager.rename_folder(folder_path, new_name)
                    if commit.success:
                        proc.stats.renamed_folders.append(new_name)
                        proc.prompts.print(f"  Renamed to: {new_name}")
                    else:
                        proc.stats.errors.append(commit.message)


def discover_audio_files(proc, folder_path: str) -> List[AudioFile]:
    audio_files = []
    folder = Path(folder_path)

    for file_path in folder.iterdir():
        if file_path.is_file() and ID3Handler.is_supported(str(file_path)):
            try:
                current_tags = proc.id3_handler.read_tags(str(file_path))
                af = AudioFile(
                    file_path=str(file_path),
                    format=ID3Handler.get_format(str(file_path)) or "unknown",
                    current_tags=current_tags,
                )
                audio_files.append(af)
            except Exception as e:
                proc.stats.malformed_files.append(str(file_path))
                eprint(f"Malformed file (skipping): {file_path.name} - {e}")

    audio_files.sort(
        key=lambda af: (
            af.current_tags.disc_number or 0,
            af.current_tags.track_number or 999,
            Path(af.file_path).name,
        )
    )

    return audio_files
