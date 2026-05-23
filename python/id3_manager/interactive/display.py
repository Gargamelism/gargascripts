"""Display-only methods for InteractivePrompts."""

import sys
from pathlib import Path
from typing import List, Optional

from models import AudioFile, ACRCloudResult, DiscogsRelease, ProcessingStats


def show_file_comparison(ui, audio_file: AudioFile) -> None:
    filename = Path(audio_file.file_path).name
    print(f"\n{ui._c('bold', 'File:')} {filename}")
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

    TRUNCATE_LEN = 40
    for field, curr, prop in fields:
        curr_str = str(curr) if curr else ui._c("dim", "(empty)")
        if prop is None:
            prop_str = ui._c("dim", "(unchanged)")
        elif str(prop) != str(curr):
            prop_str = ui._c("green", str(prop))
        else:
            prop_str = str(prop)
        if len(curr_str) > TRUNCATE_LEN:
            curr_str = curr_str[:TRUNCATE_LEN - 3] + "..."
        if len(prop_str) > TRUNCATE_LEN:
            prop_str = prop_str[:TRUNCATE_LEN - 3] + "..."
        print(f"{field:<14} {curr_str:<22} {prop_str:<22}")


def show_acr_result(ui, result: ACRCloudResult) -> None:
    print(f"\n{ui._c('cyan', 'ACRCloud Match:')}")
    print(f"  Title:      {result.title}")
    print(f"  Artist:     {', '.join(result.artists)}")
    if result.album:
        print(f"  Album:      {result.album}")
    print(f"  Confidence: {result.confidence:.0%}")


def show_discogs_candidates(ui, releases: List[DiscogsRelease]) -> Optional[int | str]:
    if ui.auto_yes and releases:
        return 0

    print(f"\n{ui._c('cyan', 'Discogs Search Results:')}")
    print("-" * 60)

    for i, release in enumerate(releases, 1):
        artists = ", ".join(release.artists)
        discogs_url = f"https://www.discogs.com/release/{release.release_id}"
        print(f"  [{i}] {release.title} ({release.year})")
        print(f"      Artists: {artists}")
        print(f"      Tracks: {len(release.tracklist)}, Discs: {release.total_discs}")
        if release.genres:
            print(f"      Genres: {', '.join(release.genres[:3])}")
        print(f"      {ui._c('dim', discogs_url)}")
        print()

    print(f"  [u] Enter Discogs URL/ID manually")
    print(f"  [s] Skip this file")
    print(f"  [q] Quit processing")

    while True:
        choice = input(f"\n{ui._c('bold', f'Select release [1-{len(releases)}/u/s/q]: ')} ").strip()
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
        print(ui._c("red", "Invalid selection. Try again."))


def show_file_rename(ui, current_name: str, new_name: str) -> None:
    print(f"  {current_name}")
    print(f"    -> {ui._c('green', new_name)}")


def show_progress(ui, current: int, total: int, message: str = "") -> None:
    if ui.quiet:
        return
    bar_width = 30
    filled = int(bar_width * current / total) if total > 0 else 0
    bar = "=" * filled + "-" * (bar_width - filled)
    pct = (current / total * 100) if total > 0 else 0
    print(f"\r[{bar}] {pct:5.1f}% ({current}/{total}) {message}\033[K", end="", flush=True)
    if current == total:
        print()


def show_summary(ui, stats: ProcessingStats) -> None:
    print(f"\n{ui._c('bold', '=' * 60)}")
    print(f"{ui._c('bold', 'Processing Summary')}")
    print("=" * 60)
    print(f"Files processed:     {stats.total_files}")
    print(f"Tags updated:        {ui._c('green', str(stats.tags_updated))}")
    print(f"Files skipped:       {stats.files_skipped}")
    print(f"ACRCloud lookups:    {stats.acr_lookups}")
    print(f"Discogs lookups:     {stats.discogs_lookups}")
    print(f"Folders renamed:     {stats.folders_renamed}")
    if stats.malformed_files:
        print(f"\n{ui._c('yellow', f'Malformed files ({len(stats.malformed_files)}):')}")
        for malformed in stats.malformed_files[:10]:
            print(f"  - {Path(malformed).name}")
        if len(stats.malformed_files) > 10:
            print(f"  ... and {len(stats.malformed_files) - 10} more")
    if stats.errors:
        print(f"\n{ui._c('red', 'Errors:')}")
        for error in stats.errors[:10]:
            print(f"  - {error}")
        if len(stats.errors) > 10:
            print(f"  ... and {len(stats.errors) - 10} more errors")


def show_folder_status(ui, folder_path: str, file_count: int,
                       needs_tag_update: int, needs_rename: int) -> None:
    print(f"\n{ui._c('bold', 'Processing folder:')} {folder_path}")
    print(f"  Files found: {file_count}")
    print(f"  Need tag update: {needs_tag_update}")
    print(f"  Need rename: {needs_rename}")
