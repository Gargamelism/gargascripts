"""Stateless parsing helpers for Discogs API responses."""

import re
from typing import Optional

from models import DiscogsRelease, DiscogsTrack


def is_vinyl_position(position: str) -> bool:
    return bool(re.match(r"^[A-Za-z]\d+$", position))


def parse_vinyl_position(position: str) -> tuple:
    match = re.match(r"^([A-Za-z])(\d+)$", position)
    if match:
        return match.group(1).upper(), int(match.group(2))
    return None, None


def parse_position(position: str) -> tuple:
    """Parse track position string into (track_number, disc_number)."""
    if not position:
        return None, None

    disc_track_match = re.match(r"^(\d+)-(\d+)$", position)
    if disc_track_match:
        return int(disc_track_match.group(2)), int(disc_track_match.group(1))

    cd_match = re.match(r"^CD(\d+)-(\d+)$", position, re.IGNORECASE)
    if cd_match:
        return int(cd_match.group(2)), int(cd_match.group(1))

    vinyl_match = re.match(r"^([A-Za-z])(\d+)$", position)
    if vinyl_match:
        side = vinyl_match.group(1).upper()
        track = int(vinyl_match.group(2))
        disc = (ord(side) - ord('A')) // 2 + 1
        return track, disc

    simple_match = re.match(r"^(\d+)$", position)
    if simple_match:
        return int(simple_match.group(1)), 1

    return None, None


def parse_release(data: dict) -> DiscogsRelease:
    """Parse Discogs API response dict into a DiscogsRelease."""
    raw_tracks = []
    has_vinyl_positions = False

    for track_data in data.get("tracklist", []):
        if track_data.get("type_", "track") != "track":
            continue
        position = track_data.get("position", "")
        if is_vinyl_position(position):
            has_vinyl_positions = True
        raw_tracks.append({
            "position": position,
            "title": track_data.get("title", ""),
            "duration": track_data.get("duration"),
        })

    tracklist = []

    if has_vinyl_positions:
        vinyl_tracks = []
        non_vinyl_tracks = []

        for track_data in raw_tracks:
            position = track_data["position"]
            if is_vinyl_position(position):
                side, track_on_side = parse_vinyl_position(position)
                vinyl_tracks.append((side, track_on_side, track_data))
            else:
                non_vinyl_tracks.append(track_data)

        vinyl_tracks.sort(key=lambda x: (x[0], x[1]))

        track_number = 1
        current_disc = 1

        for side, track_on_side, track_data in vinyl_tracks:
            disc = (ord(side) - ord('A')) // 2 + 1
            if disc != current_disc:
                track_number = 1
                current_disc = disc

            tracklist.append(DiscogsTrack(
                position=track_data["position"],
                title=track_data["title"],
                duration=track_data["duration"],
                track_number=track_number,
                disc_number=disc,
            ))
            track_number += 1

        for track_data in non_vinyl_tracks:
            track_num, disc_num = parse_position(track_data["position"])
            tracklist.append(DiscogsTrack(
                position=track_data["position"],
                title=track_data["title"],
                duration=track_data["duration"],
                track_number=track_num,
                disc_number=disc_num,
            ))
    else:
        for track_data in raw_tracks:
            position = track_data["position"]
            track_num, disc_num = parse_position(position)
            tracklist.append(DiscogsTrack(
                position=position,
                title=track_data["title"],
                duration=track_data["duration"],
                track_number=track_num,
                disc_number=disc_num,
            ))

    disc_numbers = {t.disc_number for t in tracklist if t.disc_number}
    total_discs = max(disc_numbers) if disc_numbers else 1

    artists = [a.get("name", "") for a in data.get("artists", [])]
    artists = [re.sub(r"\s*\(\d+\)$", "", a) for a in artists]

    labels = data.get("labels", [])
    label = labels[0].get("name") if labels else None

    return DiscogsRelease(
        release_id=data.get("id", 0),
        title=data.get("title", ""),
        artists=artists,
        year=data.get("year", 0),
        tracklist=tracklist,
        total_discs=total_discs,
        genres=data.get("genres", []),
        label=label,
    )
