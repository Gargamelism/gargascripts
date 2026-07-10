#!/usr/bin/env python3
"""Tag Chopin albums via Discogs, using folder names to search and filenames for track numbers.

Run from the id3_manager directory:
  python one_off/chopin_tagger.py [--dry-run] [--yes] [--start-at FOLDER] [--folder FOLDER]
"""

import argparse
import dataclasses
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from discogs_client import DiscogsClient
from folder_manager import FolderManager
from folder_manager.naming import (
    generate_disc_folder_name,
    generate_folder_name,
    sanitize_name,
)
from id3_handler import ID3Handler
from models import DiscogsRelease, DiscogsTrack, TrackMetadata

logger = logging.getLogger(__name__)

COMPOSER = "Frédéric Chopin"
GENRE = "Classical"
AUDIO_EXTS = {".mp3", ".flac", ".m4a"}

# Leading track num: "01. ", "1 ", "02-", etc.
_RE_LEADING = re.compile(r"^(\d{1,3})[.\-\s]+")
# Embedded track num: exactly 2 digits preceded by whitespace and followed by whitespace
_RE_EMBEDDED = re.compile(r"(?<=\s)(\d{2})(?=\s)")
# Strip folder sequence prefix: "10. " or "2. "
_RE_FOLDER_SEQ = re.compile(r"^\d+[\.\s]+")


def get_audio_files(folder: Path) -> List[Path]:
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )


def extract_track_num(stem: str) -> Optional[int]:
    m = _RE_LEADING.match(stem)
    if m:
        return int(m.group(1))
    m = _RE_EMBEDDED.search(stem)
    if m:
        return int(m.group(1))
    return None


def extract_performer(stem: str) -> Optional[str]:
    """Return performer from 'Performer - ...' prefix, or None if it looks like the composer."""
    if " - " not in stem:
        return None
    candidate = stem.split(" - ", 1)[0].strip()
    if re.search(r"\bchopin\b", candidate, re.IGNORECASE) or len(candidate.split()) < 2:
        return None
    return candidate


def build_search_queries(folder_name: str) -> List[str]:
    """Return a list of Discogs album search strings to try in order."""
    name = _RE_FOLDER_SEQ.sub("", folder_name).strip()
    # Strip "Chopin - " or "Chopin- " prefix
    name = re.sub(r"^chopin[\s\-]+", "", name, flags=re.IGNORECASE).strip()
    queries = [name]
    # Strip performer ("par X" suffix in French)
    before_par = re.split(r"\s+par\s+", name, flags=re.IGNORECASE)[0].strip()
    if before_par != name:
        queries.append(before_par)
    return queries


def fetch_candidates(
    client: DiscogsClient, queries: List[str], max_candidates: int = 5
) -> List[DiscogsRelease]:
    seen: set = set()
    candidates: List[DiscogsRelease] = []

    for query in queries:
        raw = client.search("Chopin", album=query)
        for r in raw[:10]:
            if len(candidates) >= max_candidates:
                break
            master_id = r.get("master_id")
            rel = None
            key = f"m{master_id}" if master_id else str(r["id"])
            if key in seen:
                continue
            seen.add(key)
            if master_id:
                rel = client.get_master(master_id)
            if rel is None:
                seen.add(str(r["id"]))
                rel = client.get_release(r["id"])
            if rel and rel.tracklist:
                candidates.append(rel)
        if candidates:
            break

    return candidates


def fetch_release_from_url(client: DiscogsClient, url: str) -> Optional[DiscogsRelease]:
    """Parse a Discogs master/release URL and fetch it."""
    m = re.search(r"/master/(\d+)", url)
    if m:
        return client.get_master(int(m.group(1)))
    m = re.search(r"/release/(\d+)", url)
    if m:
        return client.get_release(int(m.group(1)))
    return None


def prompt_url_release(client: DiscogsClient) -> Optional[DiscogsRelease]:
    """Prompt for a Discogs master/release URL and fetch it directly."""
    value = input("  Enter Discogs master/release URL: ").strip()
    rel = fetch_release_from_url(client, value)
    if rel is None:
        print("  Could not parse a master or release URL from input.")
    return rel


def fetch_disc_headings(client: DiscogsClient, release_id: int) -> Dict[int, str]:
    """Best-effort map of disc_number -> heading title, for box-set disc-picker prompts."""
    try:
        resp = client.session.get(
            f"{DiscogsClient.BASE_URL}/releases/{release_id}", timeout=15
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return {}

    headings: Dict[int, str] = {}
    current_heading = ""
    for track_data in resp.json().get("tracklist", []):
        if track_data.get("type_") == "heading":
            current_heading = track_data.get("title") or ""
            continue
        disc_str = track_data.get("position", "").split("-", 1)[0]
        if disc_str.isdigit():
            headings.setdefault(int(disc_str), current_heading)
    return headings


def pick_box_disc(
    box_release: DiscogsRelease, headings: Dict[int, str], folder_name: str
) -> Optional[int]:
    """Prompt the user to identify which disc of a multi-disc box a folder corresponds to."""
    print(f"\n{'=' * 70}")
    print(f"Folder: {folder_name}")
    print(f"  Box set: {box_release.title} ({box_release.total_discs} discs)")

    disc_numbers = sorted(
        {t.disc_number for t in box_release.tracklist if t.disc_number}
    )
    for d in disc_numbers:
        track_count = sum(1 for t in box_release.tracklist if t.disc_number == d)
        print(f"    CD{d}: {headings.get(d, '')} ({track_count} tracks)")

    print("  [s] skip  [q] quit")
    while True:
        ans = input("  Which CD number is this folder?: ").strip().lower()
        if ans == "q":
            sys.exit(0)
        if ans == "s":
            return None
        if ans.isdigit() and int(ans) in disc_numbers:
            return int(ans)
        print("  Invalid disc number.")


def build_disc_release(box_release: DiscogsRelease, disc_number: int) -> DiscogsRelease:
    """Scope a multi-disc release down to one disc's tracks, keeping box-level year/title/total_discs."""
    tracklist = [t for t in box_release.tracklist if t.disc_number == disc_number]
    return dataclasses.replace(box_release, tracklist=tracklist)


def pick_release(
    client: DiscogsClient, folder_name: str, auto_yes: bool
) -> Optional[DiscogsRelease]:
    print(f"\n{'=' * 70}")
    print(f"Folder: {folder_name}")

    suggested_queries = build_search_queries(folder_name)
    candidates = fetch_candidates(client, suggested_queries)

    while not candidates:
        print("  No Discogs results.")
        print(f"  Suggested query: {suggested_queries[0]!r}")
        ans = input("  Enter new query, [u] enter URL, [s] skip, [q] quit: ").strip()
        if ans.lower() == "q":
            sys.exit(0)
        if ans.lower() == "s":
            return None
        if ans.lower() == "u":
            rel = prompt_url_release(client)
            if rel:
                return rel
            continue
        if ans:
            candidates = fetch_candidates(client, [ans])

    for i, rel in enumerate(candidates):
        kind = "master" if rel.is_master else "release"
        print(
            f"  [{i + 1}] [{kind}#{rel.release_id}] {rel.title} ({rel.year})"
            f" — {len(rel.tracklist)} tracks — {', '.join(rel.artists)}"
        )
        print(f"      {rel.discogs_url}")

    if auto_yes:
        print("  → Auto-selecting [1]")
        return candidates[0]

    print(" [s] skip [u] enter url   [q] quit")
    while True:
        ans = input("  Choose release [1]: ").strip().lower() or "1"
        if ans == "q":
            sys.exit(0)
        if ans == "s":
            return None
        if ans == "u":
            rel = prompt_url_release(client)
            if rel:
                return rel
            continue
        try:
            idx = int(ans) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
        except ValueError:
            pass


def generate_track_filename(
    meta: TrackMetadata, heading: Optional[str], extension: str
) -> Optional[str]:
    """Build 'COMPOSER - ALBUM - TRACK_NUM - PIECE_NAME - PART_NAME' filename."""
    if meta.track_number is None:
        return None
    album = sanitize_name(meta.album)
    if meta.disc_number and meta.total_discs and meta.total_discs > 1:
        album_part = f"{album} CD{meta.disc_number}"
    else:
        album_part = album
    track_num = f"{meta.track_number:02d}"

    parts = [COMPOSER, album_part, track_num]
    if heading and heading != meta.title:
        parts.append(sanitize_name(heading))
    parts.append(sanitize_name(meta.title))
    return " - ".join(parts) + extension


def plan_folder(
    folder: Path, release: DiscogsRelease, client: DiscogsClient
) -> List[Tuple[Path, Optional[TrackMetadata], Optional[DiscogsTrack]]]:
    files = get_audio_files(folder)
    total_tracks = len(release.tracklist)
    plans: List[Tuple[Path, Optional[TrackMetadata], Optional[DiscogsTrack]]] = []

    for i, f in enumerate(files):
        stem = f.stem
        track_num = extract_track_num(stem)

        disc_track: Optional[DiscogsTrack] = None

        # 1. Match by extracted track number
        if track_num is not None:
            for t in release.tracklist:
                if t.track_number == track_num:
                    disc_track = t
                    break

        # 2. Fuzzy title match
        if disc_track is None:
            hint = stem
            if " - " in stem:
                hint = stem.split(" - ", 1)[-1]
            disc_track = client.match_track_to_release(release, hint)

        # 3. Positional fallback
        if disc_track is None and i < len(release.tracklist):
            disc_track = release.tracklist[i]

        performer = extract_performer(stem)
        artist = performer or COMPOSER

        if disc_track:
            meta = TrackMetadata(
                title=disc_track.title,
                artist=artist,
                album=release.title,
                album_artist=COMPOSER,
                track_number=disc_track.track_number,
                total_tracks=total_tracks,
                disc_number=disc_track.disc_number if release.total_discs > 1 else None,
                total_discs=release.total_discs if release.total_discs > 1 else None,
                year=release.year or None,
                genre=GENRE,
            )
        else:
            meta = None

        plans.append((f, meta, disc_track))

    return plans


def expected_album_folder_name(
    release: DiscogsRelease, disc_number: Optional[int] = None
) -> str:
    name = generate_folder_name(release.year, release.title)
    if disc_number is not None:
        name = f"{name} {generate_disc_folder_name(disc_number)}"
    return name


def print_plan(
    plans: List[Tuple[Path, Optional[TrackMetadata], Optional[DiscogsTrack]]],
    folder: Path,
    new_folder_name: str,
) -> None:
    for f, meta, disc_track in plans:
        if meta:
            track_info = f"{meta.track_number}/{meta.total_tracks}"
            disc_info = (
                f" disc {meta.disc_number}/{meta.total_discs}"
                if meta.disc_number
                else ""
            )
            print(f"  {f.name}")
            print(
                f"    → [{track_info}{disc_info}] {meta.title!r} | {meta.artist} | {meta.album} ({meta.year})"
            )
            heading = disc_track.heading if disc_track else None
            new_name = generate_track_filename(meta, heading, f.suffix)
            if new_name and new_name != f.name:
                print(f"    → rename to: {new_name}")
        else:
            print(f"  {f.name}  [NO MATCH — will be skipped]")

    if new_folder_name != folder.name:
        print(f"  Folder → rename to: {new_folder_name}")


def apply_plan(
    plans: List[Tuple[Path, Optional[TrackMetadata], Optional[DiscogsTrack]]],
    handler: ID3Handler,
    dry_run: bool,
) -> Tuple[int, int]:
    ok = err = 0
    for f, meta, _disc_track in plans:
        if meta is None:
            continue
        if dry_run:
            ok += 1
            continue
        try:
            if handler.write_tags(str(f), meta, preserve_existing=False):
                ok += 1
            else:
                err += 1
                logger.error(f"  Failed: {f.name}")
        except Exception as e:
            err += 1
            logger.error(f"  Error tagging {f.name}: {e}")
    return ok, err


def rename_files(
    plans: List[Tuple[Path, Optional[TrackMetadata], Optional[DiscogsTrack]]],
    folder_manager: FolderManager,
    dry_run: bool,
) -> Tuple[int, int]:
    ok = err = 0
    for f, meta, disc_track in plans:
        if meta is None:
            continue
        heading = disc_track.heading if disc_track else None
        new_name = generate_track_filename(meta, heading, f.suffix)
        if new_name is None or new_name == f.name:
            continue
        result = folder_manager.rename_audio_file(str(f), new_name, dry_run=dry_run)
        if result.success:
            ok += 1
        else:
            err += 1
            logger.error(f"  Rename failed for {f.name}: {result.message}")
    return ok, err


def rename_album_folder(
    folder: Path,
    release: DiscogsRelease,
    folder_manager: FolderManager,
    dry_run: bool,
    disc_number: Optional[int] = None,
) -> Optional[Path]:
    new_name = expected_album_folder_name(release, disc_number)
    if new_name == folder.name:
        return None
    result = folder_manager.rename_folder(str(folder), new_name, dry_run=dry_run)
    if not result.success:
        logger.error(f"  Folder rename failed: {result.message}")
        return None
    return folder.parent / new_name


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Tag Chopin albums via Discogs")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show plan without writing tags"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-accept first Discogs result and apply without prompting",
    )
    parser.add_argument(
        "--start-at",
        metavar="FOLDER",
        help="Skip folders alphabetically before this substring",
    )
    parser.add_argument(
        "--folder",
        metavar="PATH",
        help="Process a single folder instead of the whole tree",
    )
    parser.add_argument(
        "--music-root",
        metavar="PATH",
        help="Root folder containing Chopin album folders (required unless --folder is given)",
    )
    parser.add_argument(
        "--box-url",
        metavar="URL",
        help="Discogs release/master URL for a multi-disc box set; each folder is "
        "treated as one disc of this release (you pick which disc per folder)",
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

    box_release: Optional[DiscogsRelease] = None
    disc_headings: Dict[int, str] = {}
    if args.box_url:
        box_release = fetch_release_from_url(client, args.box_url)
        if box_release is None:
            logger.error(f"Could not fetch Discogs release from URL: {args.box_url}")
            sys.exit(1)
        disc_headings = fetch_disc_headings(client, box_release.release_id)

    if args.folder:
        folders = [Path(args.folder)]
    else:
        if not args.music_root:
            logger.error("--music-root is required unless --folder is given")
            sys.exit(1)
        folders = sorted(p for p in Path(args.music_root).iterdir() if p.is_dir())

    skip = bool(args.start_at)
    total_ok = total_err = 0

    for folder in folders:
        if skip:
            if args.start_at and args.start_at in folder.name:
                skip = False
            else:
                print(f"Skipping: {folder.name}")
                continue

        if not get_audio_files(folder):
            continue

        disc_number: Optional[int] = None
        if box_release is not None:
            disc_number = pick_box_disc(box_release, disc_headings, folder.name)
            if disc_number is None:
                continue
            release = build_disc_release(box_release, disc_number)
        else:
            release = pick_release(client, folder.name, args.yes)
            if release is None:
                continue

        plans = plan_folder(folder, release, client)
        new_folder_name = expected_album_folder_name(release, disc_number)
        print_plan(plans, folder, new_folder_name)

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

        new_folder = rename_album_folder(
            folder, release, folder_manager, args.dry_run, disc_number
        )
        if new_folder and not args.dry_run:
            folder = new_folder

        suffix = " (dry-run)" if args.dry_run else ""
        print(
            f"  Tagged {ok} files, {err} errors{suffix}. "
            f"Renamed {rename_ok} files, {rename_err} errors{suffix}."
        )

    print(f"\nDone. Total: {total_ok} tagged, {total_err} errors.")


if __name__ == "__main__":
    main()
