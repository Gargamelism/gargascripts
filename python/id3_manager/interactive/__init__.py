"""Interactive user prompts and confirmations."""

from pathlib import Path
from typing import List, Optional

from models import (
    AudioFile,
    TrackMetadata,
    DiscogsRelease,
    ProcessingStats,
    ACRCloudResult,
    ConfirmAction,
    CollisionMap,
)
from . import display as _display
from . import editing as _editing
from . import search as _search


class InteractivePrompts:
    """Handles user interaction and confirmations."""

    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "cyan": "\033[96m",
        "dim": "\033[2m",
    }

    def __init__(
        self, no_color: bool = False, auto_yes: bool = False, quiet: bool = False
    ):
        self.no_color = no_color
        self.auto_yes = auto_yes
        self.quiet = quiet
        if no_color:
            self.COLORS = {k: "" for k in self.COLORS}

    def _c(self, color: str, text: str) -> str:
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"

    def _prompt_choice(self, prompt: str, valid_choices: dict, default=None):
        while True:
            choice = input(f"\n{self._c('bold', prompt)} ").strip().lower()
            if choice == "" and default is not None:
                return default
            if choice in valid_choices:
                return valid_choices[choice]
            valid_keys = sorted(set(valid_choices.keys()))
            print(self._c("red", f"Invalid choice. Enter {', '.join(valid_keys)}"))

    def print(self, *args, **kwargs):
        if not self.quiet:
            print(*args, **kwargs)

    # --- Confirmations (stay here) ---

    def confirm_tag_changes(self, audio_files: List[AudioFile]) -> ConfirmAction:
        if self.auto_yes:
            return ConfirmAction.APPLY

        files_with_changes = [af for af in audio_files if af.proposed_tags]

        while True:
            print(
                f"\n{self._c('yellow', f'Ready to apply changes to {len(files_with_changes)} file(s).')}"
            )
            choice = self._prompt_choice(
                "Apply changes? [y/N/r(eview)/e(dit)/a(lbum edit)/q(uit)]:",
                {
                    "y": ConfirmAction.APPLY,
                    "yes": ConfirmAction.APPLY,
                    "n": ConfirmAction.SKIP,
                    "no": ConfirmAction.SKIP,
                    "r": ConfirmAction.REVIEW,
                    "e": ConfirmAction.EDIT,
                    "a": ConfirmAction.ALBUM_EDIT,
                    "q": ConfirmAction.QUIT,
                },
                default=ConfirmAction.SKIP,
            )
            match choice:
                case ConfirmAction.REVIEW:
                    for af in files_with_changes:
                        self.show_file_comparison(af)
                case ConfirmAction.EDIT:
                    self._handle_edit_track(files_with_changes)
                    for af in files_with_changes:
                        self.show_file_comparison(af)
                case ConfirmAction.ALBUM_EDIT:
                    self._handle_edit_album(files_with_changes)
                    for af in files_with_changes:
                        self.show_file_comparison(af)
                case _:
                    return choice

    def confirm_folder_rename(self, current_name: str, new_name: str) -> bool:
        if self.auto_yes:
            return True
        print(f"\n{self._c('cyan', 'Folder Rename:')}")
        print(f"  Current: {current_name}")
        print(f"  New:     {self._c('green', new_name)}")
        return self._prompt_choice(
            "Rename folder? [y/N]:",
            {"y": True, "yes": True, "n": False, "no": False},
            default=False,
        )

    def confirm_collision_resolution(self, collisions: CollisionMap) -> str:
        print(f"\n{self._c('red', 'Track-number collisions detected:')}")
        for key, files in sorted(collisions.items()):
            print(self._c("yellow", f"  Disc {key.disc}, track {key.track}:"))
            for af in files:
                tags = af.proposed_tags or af.current_tags
                print(f"    {Path(af.file_path).name}  ->  {tags.title}")
        if self.auto_yes:
            print(
                self._c(
                    "red", "[AUTO] Collision detected - skipping conflicting files."
                )
            )
            return "skip"
        return self._prompt_choice(
            "Resolve collisions? [s]kip conflicting / [e]dit fields / [a]pply anyway / [q]uit:",
            {
                "s": "skip",
                "skip": "skip",
                "e": "edit",
                "edit": "edit",
                "a": "apply",
                "apply": "apply",
                "q": "quit",
                "quit": "quit",
            },
            default="skip",
        )

    def confirm_force_override(
        self,
        af: AudioFile,
        filename: str,
        current: TrackMetadata,
        proposed: TrackMetadata,
    ) -> bool:
        if self.auto_yes:
            print(
                self._c(
                    "red",
                    f"[AUTO] Keeping existing tags for {filename} (force override not auto-applied).",
                )
            )
            return False
        while True:
            print(
                f"\n{self._c('yellow', f'--force changes already-complete tags for {filename}:')}"
            )
            print(f"  track#:  {current.track_number}  ->  {proposed.track_number}")
            print(f"  title:   {current.title}  ->  {proposed.title}")
            choice = self._prompt_choice(
                f"Override existing tags for {filename}? [y/e(dit)/N]:",
                {
                    "y": "accept",
                    "yes": "accept",
                    "e": "edit",
                    "edit": "edit",
                    "n": "decline",
                    "no": "decline",
                },
                default="decline",
            )
            if choice == "accept":
                return True
            if choice == "decline":
                return False
            prev = af.proposed_tags
            af.proposed_tags = proposed
            self._edit_track_fields(af)
            af.proposed_tags = prev

    def confirm_file_renames(self, renames: list) -> bool:
        if self.auto_yes:
            return True
        if not renames:
            return True
        print(f"\n{self._c('cyan', f'File renames ({len(renames)} files):')}")
        for current_path, new_name in renames:
            self.show_file_rename(Path(current_path).name, new_name)
        return self._prompt_choice(
            "Apply file renames? [y/N]:",
            {"y": True, "yes": True, "n": False, "no": False},
            default=False,
        )

    # --- Display shims ---
    def show_file_comparison(self, audio_file: AudioFile) -> None:
        return _display.show_file_comparison(self, audio_file)

    def show_acr_result(self, result: ACRCloudResult) -> None:
        return _display.show_acr_result(self, result)

    def show_discogs_candidates(
        self, releases: List[DiscogsRelease]
    ) -> Optional[int | str]:
        return _display.show_discogs_candidates(self, releases)

    def show_file_rename(self, current_name: str, new_name: str) -> None:
        return _display.show_file_rename(self, current_name, new_name)

    def show_progress(self, current: int, total: int, message: str = "") -> None:
        return _display.show_progress(self, current, total, message)

    def show_summary(self, stats: ProcessingStats) -> None:
        return _display.show_summary(self, stats)

    def show_folder_status(
        self,
        folder_path: str,
        file_count: int,
        needs_tag_update: int,
        needs_rename: int,
    ) -> None:
        return _display.show_folder_status(
            self, folder_path, file_count, needs_tag_update, needs_rename
        )

    # --- Search / manual-entry shims ---
    def get_discogs_url_or_id(self) -> Optional[int]:
        return _search.get_discogs_url_or_id(self)

    def handle_no_acr_match(self, file_path: str) -> str:
        return _search.handle_no_acr_match(self, file_path)

    def handle_no_discogs_match(self, acr_result: ACRCloudResult) -> str:
        return _search.handle_no_discogs_match(self, acr_result)

    def get_manual_metadata(
        self, defaults: Optional[TrackMetadata] = None
    ) -> Optional[TrackMetadata]:
        return _search.get_manual_metadata(self, defaults)

    def prompt_missing_fields(
        self, metadata: TrackMetadata, filename: str
    ) -> Optional[TrackMetadata]:
        return _search.prompt_missing_fields(self, metadata, filename)

    def get_modified_search_query(
        self, default_artist: str, default_track: str
    ) -> tuple:
        return _search.get_modified_search_query(self, default_artist, default_track)

    def handle_track_not_in_release(self, filename: str, release_title: str) -> str:
        return _search.handle_track_not_in_release(self, filename, release_title)

    # --- Editing shims ---
    def _handle_edit_track(self, audio_files: List[AudioFile]) -> None:
        return _editing.handle_edit_track(self, audio_files)

    def edit_collision_files(self, collisions: CollisionMap) -> None:
        return _editing.edit_collision_files(self, collisions)

    def _handle_edit_album(self, audio_files: List[AudioFile]) -> None:
        return _editing.handle_edit_album(self, audio_files)

    def _edit_track_fields(self, audio_file: AudioFile) -> None:
        return _editing.edit_track_fields(self, audio_file)
