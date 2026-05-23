"""Editing dialogs for InteractivePrompts."""

import dataclasses
from pathlib import Path
from typing import List

from models import AudioFile, CollisionMap


def handle_edit_track(ui, audio_files: List[AudioFile]) -> None:
    editable_files = [af for af in audio_files if af.proposed_tags]
    if not editable_files:
        print(ui._c("yellow", "No files with proposed tags to edit."))
        return

    print(f"\n{ui._c('cyan', 'Select track to edit:')}")
    for i, af in enumerate(editable_files, 1):
        filename = Path(af.file_path).name
        title = af.proposed_tags.title if af.proposed_tags else "(no proposed tags)"
        print(f"  [{i}] {filename}")
        print(f"      Proposed title: {title}")
    print(f"  [c] Cancel")

    while True:
        choice = input(
            f"\n{ui._c('bold', f'Select track [1-{len(editable_files)}/c]: ')} "
        ).strip().lower()
        if choice == "c":
            return
        try:
            idx = int(choice)
            if 1 <= idx <= len(editable_files):
                ui._edit_track_fields(editable_files[idx - 1])
                return
        except ValueError:
            pass
        print(ui._c("red", "Invalid selection. Try again."))


def edit_collision_files(ui, collisions: CollisionMap) -> None:
    files: List[AudioFile] = list({af for files in collisions.values() for af in files})

    print(f"\n{ui._c('cyan', 'Select a file to edit:')}")
    for i, af in enumerate(files, 1):
        tags = af.proposed_tags or af.current_tags
        print(f"  [{i}] {Path(af.file_path).name}  ->  track {tags.track_number}, {tags.title}")
    print(f"  [c] Cancel (back to collision menu)")

    while True:
        choice = input(
            f"\n{ui._c('bold', f'Select file [1-{len(files)}/c]: ')} "
        ).strip().lower()
        if choice == "c":
            return
        try:
            idx = int(choice)
            if 1 <= idx <= len(files):
                af = files[idx - 1]
                if af.proposed_tags is None:
                    af.proposed_tags = dataclasses.replace(af.current_tags)
                ui._edit_track_fields(af)
                return
        except ValueError:
            pass
        print(ui._c("red", "Invalid selection. Try again."))


def handle_edit_album(ui, audio_files: List[AudioFile]) -> None:
    editable_files = [af for af in audio_files if af.proposed_tags]
    if not editable_files:
        print(ui._c("yellow", "No files with proposed tags to edit."))
        return

    fields = {
        'b': ('Album',        'album',        False),
        'l': ('Album Artist', 'album_artist', False),
        'y': ('Year',         'year',         True),
        'g': ('Genre',        'genre',        False),
        'N': ('Total Tracks', 'total_tracks', True),
        'D': ('Total Discs',  'total_discs',  True),
    }

    ref = editable_files[0].proposed_tags

    while True:
        print(f"\n{ui._c('cyan', 'Album edit — changes apply to all tracks:')}")
        for key, (display_name, attr_name, _) in fields.items():
            value = getattr(ref, attr_name)
            value_str = str(value) if value is not None else ui._c("dim", "(empty)")
            print(f"  [{key}] {display_name}: {value_str}")
        print(f"  [x] Done")

        choice = input(f"\n{ui._c('bold', 'Select field to edit: ')} ").strip()
        if choice == "x":
            return
        if choice not in fields:
            print(ui._c("red", "Invalid selection. Try again."))
            continue

        display_name, attr_name, is_int = fields[choice]
        current_value = getattr(ref, attr_name)
        default_str = f" [{current_value}]" if current_value is not None else ""
        new_value = input(f"  {display_name}{default_str}: ").strip()

        if not new_value and current_value is not None:
            continue

        if not new_value:
            parsed = None
        elif is_int:
            try:
                parsed = int(new_value)
            except ValueError:
                print(ui._c("red", "Invalid number. Value not changed."))
                continue
        else:
            parsed = new_value

        for af in editable_files:
            setattr(af.proposed_tags, attr_name, parsed)
        print(ui._c("green", f"  {display_name} updated on {len(editable_files)} track(s)."))


def edit_track_fields(ui, audio_file: AudioFile) -> None:
    if not audio_file.proposed_tags:
        print(ui._c("yellow", "This file has no proposed tags to edit."))
        return

    proposed = audio_file.proposed_tags
    filename = Path(audio_file.file_path).name

    fields = {
        't': ('Title', 'title', False),
        'a': ('Artist', 'artist', False),
        'b': ('Album', 'album', False),
        'l': ('Album Artist', 'album_artist', False),
        'n': ('Track Number', 'track_number', True),
        'N': ('Total Tracks', 'total_tracks', True),
        'd': ('Disc Number', 'disc_number', True),
        'D': ('Total Discs', 'total_discs', True),
        'y': ('Year', 'year', True),
        'g': ('Genre', 'genre', False),
    }

    while True:
        print(f"\n{ui._c('bold', 'Editing:')} {filename}")
        print(f"\n{ui._c('cyan', 'Current proposed values:')}")
        for key, (display_name, attr_name, _) in fields.items():
            value = getattr(proposed, attr_name)
            value_str = str(value) if value is not None else ui._c("dim", "(empty)")
            print(f"  [{key}] {display_name}: {value_str}")
        print(f"  [x] Done editing this track")

        choice = input(f"\n{ui._c('bold', 'Select field to edit: ')} ").strip()
        if choice == "x":
            return
        if choice not in fields:
            print(ui._c("red", "Invalid selection. Try again."))
            continue

        display_name, attr_name, is_int = fields[choice]
        current_value = getattr(proposed, attr_name)
        default_str = f" [{current_value}]" if current_value is not None else ""
        new_value = input(f"  {display_name}{default_str}: ").strip()

        if not new_value and current_value is not None:
            continue
        if not new_value:
            setattr(proposed, attr_name, None)
        elif is_int:
            try:
                setattr(proposed, attr_name, int(new_value))
            except ValueError:
                print(ui._c("red", "Invalid number. Value not changed."))
                continue
        else:
            setattr(proposed, attr_name, new_value)
        print(ui._c("green", f"  {display_name} updated."))
