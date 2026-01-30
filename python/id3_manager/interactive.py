"""Interactive user prompts and confirmations."""

import sys
from pathlib import Path
from typing import List, Optional

from models import (
    AudioFile, TrackMetadata, DiscogsRelease, ProcessingStats, ACRCloudResult
)


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

    def __init__(self, no_color: bool = False, auto_yes: bool = False,
                 quiet: bool = False):
        """
        Initialize interactive prompts.

        Args:
            no_color: Disable colored output
            auto_yes: Auto-confirm all changes
            quiet: Suppress non-essential output
        """
        self.no_color = no_color
        self.auto_yes = auto_yes
        self.quiet = quiet

        if no_color:
            self.COLORS = {k: "" for k in self.COLORS}

    def _c(self, color: str, text: str) -> str:
        """Apply color to text."""
        return f"{self.COLORS.get(color, '')}{text}{self.COLORS['reset']}"

    def print(self, *args, **kwargs):
        """Print unless quiet mode."""
        if not self.quiet:
            print(*args, **kwargs)

    def show_file_comparison(self, audio_file: AudioFile) -> None:
        """Display current vs proposed tags for a file."""
        filename = Path(audio_file.file_path).name

        print(f"\n{self._c('bold', 'File:')} {filename}")
        print("-" * 60)

        current = audio_file.current_tags
        proposed = audio_file.proposed_tags

        fields = [
            ("Title", current.title, proposed.title if proposed else None),
            ("Artist", current.artist, proposed.artist if proposed else None),
            ("Album", current.album, proposed.album if proposed else None),
            ("Album Artist", current.album_artist, proposed.album_artist if proposed else None),
            ("Track #",
             f"{current.track_number or '?'}/{current.total_tracks or '?'}" if current.track_number else None,
             f"{proposed.track_number or '?'}/{proposed.total_tracks or '?'}" if proposed and proposed.track_number else None),
            ("Disc #",
             f"{current.disc_number or '?'}/{current.total_discs or '?'}" if current.disc_number else None,
             f"{proposed.disc_number or '?'}/{proposed.total_discs or '?'}" if proposed and proposed.disc_number else None),
            ("Year", current.year, proposed.year if proposed else None),
            ("Genre", current.genre, proposed.genre if proposed else None),
        ]

        print(f"{'Field':<14} {'Current':<22} {'Proposed':<22}")
        print(f"{'=' * 14} {'=' * 22} {'=' * 22}")

        for field, curr, prop in fields:
            curr_str = str(curr) if curr else self._c("dim", "(empty)")
            if prop is None:
                prop_str = self._c("dim", "(unchanged)")
            elif str(prop) != str(curr):
                prop_str = self._c("green", str(prop))
            else:
                prop_str = str(prop)

            # Truncate long values
            TRUNCATE_LEN = 40
            if len(curr_str) > TRUNCATE_LEN:
                curr_str = curr_str[:TRUNCATE_LEN - 3] + "..."
            if len(prop_str) > TRUNCATE_LEN:
                prop_str = prop_str[:TRUNCATE_LEN - 3] + "..."

            print(f"{field:<14} {curr_str:<22} {prop_str:<22}")

    def show_acr_result(self, result: ACRCloudResult) -> None:
        """Display ACRCloud recognition result."""
        print(f"\n{self._c('cyan', 'ACRCloud Match:')}")
        print(f"  Title:      {result.title}")
        print(f"  Artist:     {', '.join(result.artists)}")
        if result.album:
            print(f"  Album:      {result.album}")
        print(f"  Confidence: {result.confidence:.0%}")

    def show_discogs_candidates(self,
                                releases: List[DiscogsRelease]) -> Optional[int | str]:
        """
        Display Discogs search results and get user selection.

        Args:
            releases: List of Discogs releases

        Returns:
            Selected index, 'manual_url' for manual entry, or None if skipped
        """
        if self.auto_yes and releases:
            return 0  # Auto-select first result

        print(f"\n{self._c('cyan', 'Discogs Search Results:')}")
        print("-" * 60)

        for i, release in enumerate(releases, 1):
            artists = ", ".join(release.artists)
            discogs_url = f"https://www.discogs.com/release/{release.release_id}"
            print(f"  [{i}] {release.title} ({release.year})")
            print(f"      Artists: {artists}")
            print(f"      Tracks: {len(release.tracklist)}, "
                  f"Discs: {release.total_discs}")
            if release.genres:
                print(f"      Genres: {', '.join(release.genres[:3])}")
            print(f"      {self._c('dim', discogs_url)}")
            print()

        print(f"  [u] Enter Discogs URL/ID manually")
        print(f"  [s] Skip this file")
        print(f"  [q] Quit processing")

        while True:
            choice = input(f"\n{self._c('bold', f'Select release [1-{len(releases)}/u/s/q]: ')} ").strip()

            if choice.lower() == "s":
                return None
            if choice.lower() == "q":
                sys.exit(0)
            if choice.lower() == "u":
                return "manual_url"

            try:
                idx = int(choice)
                if 1 <= idx <= len(releases):
                    return idx - 1
            except ValueError:
                pass

            print(self._c("red", "Invalid selection. Try again."))

    def get_discogs_url_or_id(self) -> Optional[int]:
        """
        Prompt user for a Discogs release URL or ID.

        Returns:
            Release ID as integer, or None if cancelled
        """
        import re

        print(f"\n{self._c('cyan', 'Enter Discogs release URL or ID:')}")
        print(f"  Examples:")
        print(f"    https://www.discogs.com/release/12345-Artist-Album")
        print(f"    https://www.discogs.com/release/12345")
        print(f"    12345")
        print()

        value = input(f"  {self._c('bold', 'URL or ID:')} ").strip()

        if not value:
            return None

        # Try to extract release ID from URL or direct input
        # Pattern matches: /release/12345 or /release/12345-anything or just 12345
        patterns = [
            r'/release/(\d+)',  # URL with /release/ID
            r'^(\d+)$',          # Just the ID
        ]

        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                return int(match.group(1))

        print(self._c("red", "Could not parse release ID from input."))
        return None

    def confirm_tag_changes(self, audio_files: List[AudioFile]) -> str:
        """
        Confirm batch tag changes.

        Args:
            audio_files: Files with proposed changes

        Returns:
            'apply', 'skip', or 'quit'
        """
        if self.auto_yes:
            return "apply"

        files_with_changes = [af for af in audio_files if af.proposed_tags]

        while True:
            print(f"\n{self._c('yellow', f'Ready to apply changes to {len(files_with_changes)} file(s).')}")
            choice = input(f"{self._c('bold', 'Apply changes? [y/N/r(eview)/e(dit)/q(uit)]: ')} ").strip().lower()

            if choice == "r":
                for af in files_with_changes:
                    self.show_file_comparison(af)
                continue
            elif choice == "e":
                self._handle_edit_track(files_with_changes)
                for af in files_with_changes:
                    self.show_file_comparison(af)
                continue
            elif choice == "y":
                return "apply"
            elif choice == "n" or choice == "":
                return "skip"
            elif choice == "q":
                return "quit"

            print(self._c("red", "Invalid choice. Enter y, n, r, e, or q."))

    def _handle_edit_track(self, audio_files: List[AudioFile]) -> None:
        """Allow user to select and edit a track's proposed tags."""
        # Filter to only files with proposed tags
        editable_files = [af for af in audio_files if af.proposed_tags]

        if not editable_files:
            print(self._c("yellow", "No files with proposed tags to edit."))
            return

        # Display numbered list of tracks
        print(f"\n{self._c('cyan', 'Select track to edit:')}")
        for i, af in enumerate(editable_files, 1):
            filename = Path(af.file_path).name
            title = af.proposed_tags.title if af.proposed_tags else "(no proposed tags)"
            print(f"  [{i}] {filename}")
            print(f"      Proposed title: {title}")

        print(f"  [c] Cancel")

        # Get track selection
        while True:
            choice = input(f"\n{self._c('bold', f'Select track [1-{len(editable_files)}/c]: ')} ").strip().lower()

            if choice == "c":
                return

            try:
                idx = int(choice)
                if 1 <= idx <= len(editable_files):
                    selected_file = editable_files[idx - 1]
                    self._edit_track_fields(selected_file)
                    return
            except ValueError:
                pass

            print(self._c("red", "Invalid selection. Try again."))

    def _edit_track_fields(self, audio_file: AudioFile) -> None:
        """Edit specific fields of a track's proposed tags."""
        if not audio_file.proposed_tags:
            print(self._c("yellow", "This file has no proposed tags to edit."))
            return

        proposed = audio_file.proposed_tags
        filename = Path(audio_file.file_path).name

        # Field mapping: key -> (display_name, attribute_name, is_int)
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
            # Show current proposed values
            print(f"\n{self._c('bold', 'Editing:')} {filename}")
            print(f"\n{self._c('cyan', 'Current proposed values:')}")
            for key, (display_name, attr_name, _) in fields.items():
                value = getattr(proposed, attr_name)
                value_str = str(value) if value is not None else self._c("dim", "(empty)")
                print(f"  [{key}] {display_name}: {value_str}")

            print(f"  [x] Done editing this track")

            choice = input(f"\n{self._c('bold', 'Select field to edit: ')} ").strip()

            if choice == "x":
                return

            if choice not in fields:
                print(self._c("red", "Invalid selection. Try again."))
                continue

            display_name, attr_name, is_int = fields[choice]
            current_value = getattr(proposed, attr_name)

            # Prompt for new value
            default_str = f" [{current_value}]" if current_value is not None else ""
            new_value = input(f"  {display_name}{default_str}: ").strip()

            if not new_value and current_value is not None:
                # Keep current value
                continue

            if not new_value:
                # Set to None
                setattr(proposed, attr_name, None)
            elif is_int:
                try:
                    setattr(proposed, attr_name, int(new_value))
                except ValueError:
                    print(self._c("red", "Invalid number. Value not changed."))
                    continue
            else:
                setattr(proposed, attr_name, new_value)

            print(self._c("green", f"  {display_name} updated."))

    def confirm_folder_rename(self, current_name: str, new_name: str) -> bool:
        """
        Confirm folder rename.

        Args:
            current_name: Current folder name
            new_name: Proposed new name

        Returns:
            True if confirmed
        """
        if self.auto_yes:
            return True

        print(f"\n{self._c('cyan', 'Folder Rename:')}")
        print(f"  Current: {current_name}")
        print(f"  New:     {self._c('green', new_name)}")

        choice = input(f"{self._c('bold', 'Rename folder? [y/N]: ')} ").strip().lower()
        return choice == "y"

    def handle_no_acr_match(self, file_path: str) -> str:
        """
        Handle case when ACRCloud returns no match.

        Args:
            file_path: Path to unidentified file

        Returns:
            'manual', 'existing', 'skip', or 'quit'
        """
        filename = Path(file_path).name

        print(f"\n{self._c('yellow', f'No ACRCloud match for:')} {filename}")
        print()
        print("  [1] Enter artist/title manually")
        print("  [2] Use existing partial tags for Discogs search")
        print("  [3] Skip this file")
        print("  [q] Quit")

        while True:
            choice = input(f"\n{self._c('bold', 'Select option: ')} ").strip().lower()

            if choice == "1":
                return "manual"
            elif choice == "2":
                return "existing"
            elif choice == "3":
                return "skip"
            elif choice == "q":
                return "quit"

            print(self._c("red", "Invalid selection."))

    def handle_no_discogs_match(self, acr_result: ACRCloudResult) -> str:
        """
        Handle case when Discogs returns no results.

        Args:
            acr_result: ACRCloud result that found no Discogs match

        Returns:
            'acr_only', 'retry', 'manual', 'manual_url', 'skip', or 'quit'
        """
        print(f"\n{self._c('yellow', 'No Discogs match for:')} "
              f"{acr_result.title} by {', '.join(acr_result.artists)}")
        print()
        print("  [1] Use ACRCloud data only (partial tags)")
        print("  [2] Search Discogs with modified query")
        print("  [3] Enter Discogs URL/ID manually")
        print("  [4] Enter metadata manually")
        print("  [5] Skip this file")
        print("  [q] Quit")

        while True:
            choice = input(f"\n{self._c('bold', 'Select option: ')} ").strip().lower()

            if choice == "1":
                return "acr_only"
            elif choice == "2":
                return "retry"
            elif choice == "3":
                return "manual_url"
            elif choice == "4":
                return "manual"
            elif choice == "5":
                return "skip"
            elif choice == "q":
                return "quit"

            print(self._c("red", "Invalid selection."))

    def get_manual_metadata(self, defaults: Optional[TrackMetadata] = None) -> Optional[TrackMetadata]:
        """
        Prompt user for manual metadata entry.

        Args:
            defaults: Optional default values to show

        Returns:
            TrackMetadata with user-entered values, or None if cancelled
        """
        print(f"\n{self._c('cyan', 'Enter metadata (press Enter to skip/keep default):')}")

        def prompt_field(name: str, default: Optional[str] = None) -> Optional[str]:
            default_str = f" [{default}]" if default else ""
            value = input(f"  {name}{default_str}: ").strip()
            if not value and default:
                return default
            return value if value else None

        def prompt_int(name: str, default: Optional[int] = None) -> Optional[int]:
            default_str = f" [{default}]" if default else ""
            value = input(f"  {name}{default_str}: ").strip()
            if not value and default:
                return default
            try:
                return int(value) if value else None
            except ValueError:
                return None

        title = prompt_field("Title", defaults.title if defaults else None)
        artist = prompt_field("Artist", defaults.artist if defaults else None)

        if not title and not artist:
            print(self._c("yellow", "Cancelled - no title or artist entered."))
            return None

        album = prompt_field("Album", defaults.album if defaults else None)
        year = prompt_int("Year", defaults.year if defaults else None)
        track_num = prompt_int("Track #", defaults.track_number if defaults else None)
        total_tracks = prompt_int("Total tracks", defaults.total_tracks if defaults else None)
        disc_num = prompt_int("Disc #", defaults.disc_number if defaults else None)
        total_discs = prompt_int("Total discs", defaults.total_discs if defaults else None)
        genre = prompt_field("Genre", defaults.genre if defaults else None)

        metadata = TrackMetadata(
            title=title,
            artist=artist,
            album=album,
            year=year,
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_num,
            total_discs=total_discs,
            genre=genre,
        )

        # Validate required fields - loop until complete or user skips
        return self.prompt_missing_fields(metadata, "manual entry")

    def prompt_missing_fields(self, metadata: TrackMetadata,
                              filename: str) -> Optional[TrackMetadata]:
        """
        Prompt user to fill in missing required fields.

        Loops until all required fields are filled or user explicitly skips.

        Args:
            metadata: TrackMetadata with some fields possibly missing
            filename: Name of the file being processed (for display)

        Returns:
            TrackMetadata with all required fields filled, or None if user skips
        """
        while True:
            missing = metadata.get_missing_required_fields()

            if not missing:
                return metadata  # All required fields present

            if self.auto_yes:
                # In auto-yes mode, cannot proceed without required fields
                print(f"\n{self._c('yellow', f'Missing required fields for:')} {filename}")
                print(f"  Missing: {', '.join(missing)}")
                print(f"  {self._c('red', '[AUTO] Cannot proceed - missing required fields. Skipping.')}")
                return None

            print(f"\n{self._c('yellow', f'Missing required fields for:')} {filename}")
            print(f"  Missing: {', '.join(missing)}")
            print()
            print("  [1] Enter missing values")
            print("  [2] Skip this file")

            while True:
                choice = input(f"\n{self._c('bold', 'Select option: ')} ").strip()

                if choice == "1":
                    break
                elif choice == "2":
                    return None  # Explicit skip

                print(self._c("red", "Invalid selection."))

            # Prompt for missing fields only
            print(f"\n{self._c('cyan', 'Enter missing values:')}")

            if "title" in missing:
                value = input(f"  Title: ").strip()
                if value:
                    metadata.title = value

            if "artist" in missing:
                value = input(f"  Artist: ").strip()
                if value:
                    metadata.artist = value

            if "album" in missing:
                value = input(f"  Album: ").strip()
                if value:
                    metadata.album = value

            if "track_number" in missing:
                value = input(f"  Track #: ").strip()
                if value:
                    try:
                        metadata.track_number = int(value)
                    except ValueError:
                        print(self._c("red", "  Invalid number, try again."))

            # Loop continues - will check again if still missing

    def get_modified_search_query(self, default_artist: str,
                                  default_track: str) -> tuple:
        """
        Get modified search query from user.

        Args:
            default_artist: Default artist name
            default_track: Default track title

        Returns:
            (artist, track) tuple
        """
        print(f"\n{self._c('cyan', 'Enter modified search query:')}")

        artist = input(f"  Artist [{default_artist}]: ").strip()
        track = input(f"  Track [{default_track}]: ").strip()

        return (artist or default_artist, track or default_track)

    def show_file_rename(self, current_name: str, new_name: str) -> None:
        """Display file rename operation."""
        print(f"  {current_name}")
        print(f"    -> {self._c('green', new_name)}")

    def confirm_file_renames(self, renames: list) -> bool:
        """
        Confirm batch file renames.

        Args:
            renames: List of (current_path, new_name) tuples

        Returns:
            True if confirmed
        """
        if self.auto_yes:
            return True

        if not renames:
            return True

        print(f"\n{self._c('cyan', f'File renames ({len(renames)} files):')}")
        for current_path, new_name in renames:
            current_name = Path(current_path).name
            self.show_file_rename(current_name, new_name)

        choice = input(f"\n{self._c('bold', 'Apply file renames? [y/N]: ')} ").strip().lower()
        return choice == "y"

    def show_progress(self, current: int, total: int,
                      message: str = "") -> None:
        """Display progress indicator."""
        if self.quiet:
            return

        bar_width = 30
        filled = int(bar_width * current / total) if total > 0 else 0
        bar = "=" * filled + "-" * (bar_width - filled)
        pct = (current / total * 100) if total > 0 else 0

        print(f"\r[{bar}] {pct:5.1f}% ({current}/{total}) {message}\033[K",
              end="", flush=True)

        if current == total:
            print()

    def show_summary(self, stats: ProcessingStats) -> None:
        """Display final processing summary."""
        print(f"\n{self._c('bold', '=' * 60)}")
        print(f"{self._c('bold', 'Processing Summary')}")
        print("=" * 60)

        print(f"Files processed:     {stats.total_files}")
        print(f"Tags updated:        {self._c('green', str(stats.tags_updated))}")
        print(f"Files skipped:       {stats.files_skipped}")
        print(f"ACRCloud lookups:    {stats.acr_lookups}")
        print(f"Discogs lookups:     {stats.discogs_lookups}")
        print(f"Folders renamed:     {stats.folders_renamed}")

        if stats.malformed_files:
            print(f"\n{self._c('yellow', f'Malformed files ({len(stats.malformed_files)}):')}")
            for malformed in stats.malformed_files[:10]:  # Limit displayed files
                print(f"  - {Path(malformed).name}")
            if len(stats.malformed_files) > 10:
                print(f"  ... and {len(stats.malformed_files) - 10} more")

        if stats.errors:
            print(f"\n{self._c('red', 'Errors:')}")
            for error in stats.errors[:10]:  # Limit displayed errors
                print(f"  - {error}")
            if len(stats.errors) > 10:
                print(f"  ... and {len(stats.errors) - 10} more errors")

    def show_folder_status(self, folder_path: str, file_count: int,
                           needs_tag_update: int, needs_rename: int) -> None:
        """Show folder processing status."""
        print(f"\n{self._c('bold', 'Processing folder:')} {folder_path}")
        print(f"  Files found: {file_count}")
        print(f"  Need tag update: {needs_tag_update}")
        print(f"  Need rename: {needs_rename}")

    def handle_track_not_in_release(self, filename: str, release_title: str) -> str:
        """
        Handle case when a track doesn't match the cached release.

        Args:
            filename: Name of the file being processed
            release_title: Title of the cached release

        Returns:
            'search', 'skip', or 'quit'
        """
        print(f"\n{self._c('yellow', f'Track not found in release:')} {filename}")
        print(f"  Release: {release_title}")
        print()
        print("  [1] Search Discogs for this file")
        print("  [2] Skip this file")
        print("  [q] Quit")

        while True:
            choice = input(f"\n{self._c('bold', 'Select option: ')} ").strip().lower()

            if choice == "1":
                return "search"
            elif choice == "2":
                return "skip"
            elif choice == "q":
                return "quit"

            print(self._c("red", "Invalid selection."))
