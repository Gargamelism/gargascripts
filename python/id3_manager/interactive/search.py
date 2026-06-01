"""Search, manual-entry, and match-handling prompts for InteractivePrompts."""

import re
from pathlib import Path
from typing import Optional

from models import (
    ACRCloudResult,
    TrackMetadata,
    NoACRMatchAction,
    NoDiscogsMatchAction,
    TrackNotInReleaseAction,
)


def get_discogs_url_or_id(ui) -> Optional[int]:
    print(f"\n{ui._c('cyan', 'Enter Discogs release URL or ID:')}")
    print(f"  Examples:")
    print(f"    https://www.discogs.com/release/12345-Artist-Album")
    print(f"    https://www.discogs.com/release/12345")
    print(f"    12345")
    print()

    value = input(f"  {ui._c('bold', 'URL or ID:')} ").strip()
    if not value:
        return None

    for pattern in [r"/release/(\d+)", r"^(\d+)$"]:
        match = re.search(pattern, value)
        if match:
            return int(match.group(1))

    print(ui._c("red", "Could not parse release ID from input."))
    return None


def handle_no_acr_match(ui, file_path: str) -> NoACRMatchAction:
    filename = Path(file_path).name
    print(f"\n{ui._c('yellow', f'No ACRCloud match for:')} {filename}")
    print()
    print("  [1] Enter artist/title manually")
    print("  [2] Use existing partial tags for Discogs search")
    print("  [3] Skip this file")
    print("  [q] Quit")
    return ui._prompt_choice(
        "Select option:",
        {
            "1": NoACRMatchAction.MANUAL,
            "2": NoACRMatchAction.EXISTING,
            "3": NoACRMatchAction.SKIP,
            "q": NoACRMatchAction.QUIT,
        },
    )


def handle_no_discogs_match(ui, acr_result: ACRCloudResult) -> NoDiscogsMatchAction:
    print(
        f"\n{ui._c('yellow', 'No Discogs match for:')} "
        f"{acr_result.title} by {', '.join(acr_result.artists)}"
    )
    print()
    print("  [1] Use ACRCloud data only (partial tags)")
    print("  [2] Search Discogs with modified query")
    print("  [3] Enter Discogs URL/ID manually")
    print("  [4] Enter metadata manually")
    print("  [5] Skip this file")
    print("  [q] Quit")
    return ui._prompt_choice(
        "Select option:",
        {
            "1": NoDiscogsMatchAction.ACR_ONLY,
            "2": NoDiscogsMatchAction.RETRY,
            "3": NoDiscogsMatchAction.MANUAL_URL,
            "4": NoDiscogsMatchAction.MANUAL,
            "5": NoDiscogsMatchAction.SKIP,
            "q": NoDiscogsMatchAction.QUIT,
        },
    )


def get_manual_metadata(
    ui, defaults: Optional[TrackMetadata] = None
) -> Optional[TrackMetadata]:
    print(f"\n{ui._c('cyan', 'Enter metadata (press Enter to skip/keep default):')}")

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
        print(ui._c("yellow", "Cancelled - no title or artist entered."))
        return None

    album = prompt_field("Album", defaults.album if defaults else None)
    year = prompt_int("Year", defaults.year if defaults else None)
    track_num = prompt_int("Track #", defaults.track_number if defaults else None)
    total_tracks = prompt_int(
        "Total tracks", defaults.total_tracks if defaults else None
    )
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

    return ui.prompt_missing_fields(metadata, "manual entry")


def prompt_missing_fields(
    ui, metadata: TrackMetadata, filename: str
) -> Optional[TrackMetadata]:
    while True:
        missing = metadata.get_missing_required_fields()
        if not missing:
            return metadata

        if ui.auto_yes:
            print(f"\n{ui._c('yellow', f'Missing required fields for:')} {filename}")
            print(f"  Missing: {', '.join(missing)}")
            print(
                f"  {ui._c('red', '[AUTO] Cannot proceed - missing required fields. Skipping.')}"
            )
            return None

        print(f"\n{ui._c('yellow', f'Missing required fields for:')} {filename}")
        print(f"  Missing: {', '.join(missing)}")
        print()
        print("  [1] Enter missing values")
        print("  [2] Skip this file")

        choice = ui._prompt_choice("Select option:", {"1": "edit", "2": "skip"})
        if choice == "skip":
            return None

        print(f"\n{ui._c('cyan', 'Enter missing values:')}")

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
                    print(ui._c("red", "  Invalid number, try again."))


def get_modified_search_query(ui, default_artist: str, default_track: str) -> tuple:
    print(f"\n{ui._c('cyan', 'Enter modified search query:')}")
    artist = input(f"  Artist [{default_artist}]: ").strip()
    track = input(f"  Track [{default_track}]: ").strip()
    return (artist or default_artist, track or default_track)


def handle_track_not_in_release(
    ui, filename: str, release_title: str
) -> TrackNotInReleaseAction:
    print(f"\n{ui._c('yellow', f'Track not found in release:')} {filename}")
    print(f"  Release: {release_title}")
    print()
    print("  [1] Search Discogs for this file")
    print("  [2] Skip this file")
    print("  [q] Quit")
    return ui._prompt_choice(
        "Select option:",
        {
            "1": TrackNotInReleaseAction.SEARCH,
            "2": TrackNotInReleaseAction.SKIP,
            "q": TrackNotInReleaseAction.QUIT,
        },
    )
