"""Stateless tag helpers shared across formats."""

from typing import Literal, Optional, TypedDict, get_args

TagField = Literal[
    "title", "artist", "album", "album_artist", "track", "disc", "year", "genre"
]

TagKeyMap = TypedDict("TagKeyMap", {field: str for field in get_args(TagField)})


MP4_TAGS: TagKeyMap = {
    "title": "\xa9nam",
    "artist": "\xa9ART",
    "album": "\xa9alb",
    "album_artist": "aART",
    "track": "trkn",
    "disc": "disk",
    "year": "\xa9day",
    "genre": "\xa9gen",
}

WMA_TAGS: TagKeyMap = {
    "title": "Title",
    "artist": "Author",
    "album": "WM/AlbumTitle",
    "album_artist": "WM/AlbumArtist",
    "track": "WM/TrackNumber",
    "disc": "WM/PartOfSet",
    "year": "WM/Year",
    "genre": "WM/Genre",
}


def parse_track_disc(value: str) -> tuple:
    """Parse track/disc string like '3/12' or '3'. Returns (number, total)."""
    if not value:
        return None, None
    parts = value.split("/")
    try:
        num = int(parts[0]) if parts[0].strip() else None
        total = int(parts[1]) if len(parts) > 1 and parts[1].strip() else None
        return num, total
    except ValueError:
        return None, None


def parse_year(value: str) -> Optional[int]:
    """Parse year from various date formats."""
    if not value:
        return None
    try:
        return int(str(value)[:4])
    except (ValueError, IndexError):
        return None


def get_tag_str(tags: dict, key: str) -> Optional[str]:
    """Get string value from ID3 tag dict."""
    tag = tags.get(key)
    if tag:
        try:
            value = str(tag[0]) if hasattr(tag, "__getitem__") else str(tag)
        except IndexError:
            return None
        return value if value else None
    return None


def get_mp4_tag(tags: dict, key: TagField, mp4_tags: TagKeyMap) -> Optional[str]:
    """Get string value from MP4 tag dict."""
    mp4_key = mp4_tags.get(key)
    if mp4_key and mp4_key in tags:
        value = tags[mp4_key]
        if isinstance(value, list) and value:
            return str(value[0]) if value[0] else None
        return str(value) if value else None
    return None
