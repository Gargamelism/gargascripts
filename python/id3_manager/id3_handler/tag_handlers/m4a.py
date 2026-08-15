"""M4A/MP4 tag handler."""

from mutagen.mp4 import MP4

from models import TrackMetadata
from id3_handler.formats import MP4_TAGS, parse_year, get_mp4_tag


class M4aTagHandler:
    """Reads and writes tags for M4A (MP4) files."""

    def read_tags(self, file_path: str) -> TrackMetadata:
        audio = MP4(file_path)
        tags = audio.tags or {}
        track_info = tags.get(MP4_TAGS["track"], [(None, None)])[0]
        disc_info = tags.get(MP4_TAGS["disc"], [(None, None)])[0]
        track_num = track_info[0] if track_info and track_info[0] else None
        total_tracks = (
            track_info[1]
            if track_info and len(track_info) > 1 and track_info[1]
            else None
        )
        disc_num = disc_info[0] if disc_info and disc_info[0] else None
        total_discs = (
            disc_info[1] if disc_info and len(disc_info) > 1 and disc_info[1] else None
        )
        return TrackMetadata(
            title=get_mp4_tag(tags, "title", MP4_TAGS),
            artist=get_mp4_tag(tags, "artist", MP4_TAGS),
            album=get_mp4_tag(tags, "album", MP4_TAGS),
            album_artist=get_mp4_tag(tags, "album_artist", MP4_TAGS),
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_num,
            total_discs=total_discs,
            year=parse_year(get_mp4_tag(tags, "year", MP4_TAGS) or ""),
            genre=get_mp4_tag(tags, "genre", MP4_TAGS),
        )

    def write_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        audio = MP4(file_path)
        if audio.tags is None:
            audio.add_tags()
        if metadata.title:
            audio.tags[MP4_TAGS["title"]] = [metadata.title]
        if metadata.artist:
            audio.tags[MP4_TAGS["artist"]] = [metadata.artist]
        if metadata.album:
            audio.tags[MP4_TAGS["album"]] = [metadata.album]
        if metadata.album_artist:
            audio.tags[MP4_TAGS["album_artist"]] = [metadata.album_artist]
        if metadata.track_number:
            audio.tags[MP4_TAGS["track"]] = [
                (metadata.track_number, metadata.total_tracks or 0)
            ]
        if metadata.disc_number:
            audio.tags[MP4_TAGS["disc"]] = [
                (metadata.disc_number, metadata.total_discs or 0)
            ]
        if metadata.year:
            audio.tags[MP4_TAGS["year"]] = [str(metadata.year)]
        if metadata.genre:
            audio.tags[MP4_TAGS["genre"]] = [metadata.genre]
        audio.save()
        return True
