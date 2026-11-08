#!/usr/bin/env python3
"""Tag the Dvořák "The Masterworks" 40-CD box (Discogs release 2403209).

Expects one folder per disc named "CDnn_..." under --music-root. The disc number comes
from the folder name, the track from the filename's leading number, and the performer
from the Discogs track artist. Tracks Discogs is missing (e.g. CD11 Agnus Dei, CD34
Bohemian Forest) fall back to the "NN- Work - Movement" filename.

Run from the id3_manager directory:
  python one_off/dvorak_masterworks_tagger.py --music-root PATH [--dry-run] [--yes] [--start-at CDnn]
"""

import argparse
import dataclasses
import logging
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import chopin_tagger
from chopin_tagger import (
    apply_plan,
    build_disc_release,
    expected_album_folder_name,
    extract_track_num,
    fetch_release_from_url,
    get_audio_files,
    print_plan,
    rename_album_folder,
    rename_files,
)
from config import load_config
from discogs_client import DiscogsClient
from folder_manager import FolderManager
from id3_handler import ID3Handler
from models import DiscogsRelease, DiscogsTrack, TrackMetadata

logger = logging.getLogger(__name__)

RELEASE_URL = "https://www.discogs.com/release/2403209"
COMPOSER = "Antonín Dvořák"
GENRE = "Classical"

# chopin_tagger's filename builder reads its module-level COMPOSER
chopin_tagger.COMPOSER = COMPOSER

_RE_DISC_FOLDER = re.compile(r"^CD(\d+)", re.IGNORECASE)
# "01- Work - Movement"
_RE_FILENAME = re.compile(r"^\d{1,3}[.\-\s]+(.+?)\s*-\s+(.+)$")


def parse_filename(stem: str) -> Tuple[Optional[str], str]:
    """Split "NN- Work - Movement" into (work, movement)."""
    m = _RE_FILENAME.match(stem)
    return (m.group(1), m.group(2)) if m else (None, stem)


def fallback_track(stem: str, disc_number: int, track_num: int) -> DiscogsTrack:
    """Build a track from the filename for entries missing on Discogs."""
    heading, title = parse_filename(stem)
    return DiscogsTrack(
        position=f"{disc_number}-{track_num}",
        title=title,
        track_number=track_num,
        disc_number=disc_number,
        heading=heading,
    )


def plan_folder(
    folder: Path, release: DiscogsRelease, disc_number: int
) -> List[Tuple[Path, Optional[TrackMetadata], Optional[DiscogsTrack]]]:
    files = get_audio_files(folder)
    by_number = {t.track_number: t for t in release.tracklist}
    total_tracks = max(len(files), len(release.tracklist))
    plans: List[Tuple[Path, Optional[TrackMetadata], Optional[DiscogsTrack]]] = []
    last_artist = COMPOSER

    for f in files:
        track_num = extract_track_num(f.stem)
        if track_num is None:
            plans.append((f, None, None))
            continue

        disc_track = by_number.get(track_num)
        if disc_track is None:
            disc_track = fallback_track(f.stem, disc_number, track_num)
        else:
            # Filename work names beat Discogs headings here (e.g. "Opera In 3 Acts Part I" vs "Rusalka")
            disc_track = dataclasses.replace(
                disc_track, heading=parse_filename(f.stem)[0]
            )
        # Missing tracks inherit the performer of the preceding track on the disc
        artist = disc_track.artist or last_artist
        last_artist = artist

        meta = TrackMetadata(
            title=disc_track.title,
            artist=artist,
            album=release.title,
            album_artist=COMPOSER,
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_number,
            total_discs=release.total_discs,
            year=release.year or None,
            genre=GENRE,
        )
        plans.append((f, meta, disc_track))

    return plans


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Tag the Dvořák Masterworks box")
    parser.add_argument(
        "--music-root",
        required=True,
        metavar="PATH",
        help="Folder containing the CDnn_* disc folders",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show plan without writing tags"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Apply every disc without prompting"
    )
    parser.add_argument(
        "--start-at",
        metavar="FOLDER",
        help="Skip folders before the first one containing this substring",
    )
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    config = load_config(args.env_file)
    token = config.get("discogs_user_token")
    if not token:
        logger.error("DISCOGS_USER_TOKEN not set in .env")
        sys.exit(1)

    client = DiscogsClient(token)
    handler = ID3Handler()
    folder_manager = FolderManager()

    box_release = fetch_release_from_url(client, RELEASE_URL)
    if box_release is None:
        logger.error(f"Could not fetch Discogs release: {RELEASE_URL}")
        sys.exit(1)

    folders = sorted(
        p
        for p in Path(args.music_root).iterdir()
        if p.is_dir() and _RE_DISC_FOLDER.match(p.name)
    )

    skip = bool(args.start_at)
    total_ok = total_err = 0

    for folder in folders:
        if skip:
            if args.start_at in folder.name:
                skip = False
            else:
                print(f"Skipping: {folder.name}")
                continue

        disc_number = int(_RE_DISC_FOLDER.match(folder.name).group(1))
        release = build_disc_release(box_release, disc_number)

        print(f"\n{'=' * 70}")
        print(
            f"Folder: {folder.name}  →  CD{disc_number} ({len(release.tracklist)} Discogs tracks)"
        )

        plans = plan_folder(folder, release, disc_number)
        print_plan(plans, folder, expected_album_folder_name(release, disc_number))

        if not args.yes:
            ans = input("\n  Apply these tags and renames? [y/n/q]: ").strip().lower()
            if ans == "q":
                break
            if ans != "y":
                print("  Skipped.")
                continue

        ok, err = apply_plan(plans, handler, args.dry_run)
        total_ok += ok
        total_err += err

        rename_ok, rename_err = rename_files(plans, folder_manager, args.dry_run)
        total_err += rename_err

        rename_album_folder(folder, release, folder_manager, args.dry_run, disc_number)

        suffix = " (dry-run)" if args.dry_run else ""
        print(
            f"  Tagged {ok} files, {err} errors{suffix}. "
            f"Renamed {rename_ok} files, {rename_err} errors{suffix}."
        )

    print(f"\nDone. Total: {total_ok} tagged, {total_err} errors.")


if __name__ == "__main__":
    main()
