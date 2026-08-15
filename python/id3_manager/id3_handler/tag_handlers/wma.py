"""WMA tag handler."""

from mutagen.asf import ASF

from models import TrackMetadata
from id3_handler.formats import WMA_TAGS, parse_track_disc, parse_year, get_tag_str


class WmaTagHandler:
    """Reads and writes tags for WMA files."""

    def read_tags(self, file_path: str) -> TrackMetadata:
        audio = ASF(file_path)
        tags = audio.tags or {}
        track_num, total_tracks = parse_track_disc(
            get_tag_str(tags, WMA_TAGS["track"]) or ""
        )
        disc_num, total_discs = parse_track_disc(
            get_tag_str(tags, WMA_TAGS["disc"]) or ""
        )
        return TrackMetadata(
            title=get_tag_str(tags, WMA_TAGS["title"]),
            artist=get_tag_str(tags, WMA_TAGS["artist"]),
            album=get_tag_str(tags, WMA_TAGS["album"]),
            album_artist=get_tag_str(tags, WMA_TAGS["album_artist"]),
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_num,
            total_discs=total_discs,
            year=parse_year(get_tag_str(tags, WMA_TAGS["year"])),
            genre=get_tag_str(tags, WMA_TAGS["genre"]),
        )

    def write_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        audio = ASF(file_path)
        if metadata.title:
            audio[WMA_TAGS["title"]] = metadata.title
        if metadata.artist:
            audio[WMA_TAGS["artist"]] = metadata.artist
        if metadata.album:
            audio[WMA_TAGS["album"]] = metadata.album
        if metadata.album_artist:
            audio[WMA_TAGS["album_artist"]] = metadata.album_artist
        if metadata.track_number:
            track_str = str(metadata.track_number)
            if metadata.total_tracks:
                track_str += f"/{metadata.total_tracks}"
            audio[WMA_TAGS["track"]] = track_str
        if metadata.disc_number:
            disc_str = str(metadata.disc_number)
            if metadata.total_discs:
                disc_str += f"/{metadata.total_discs}"
            audio[WMA_TAGS["disc"]] = disc_str
        if metadata.year:
            audio[WMA_TAGS["year"]] = str(metadata.year)
        if metadata.genre:
            audio[WMA_TAGS["genre"]] = metadata.genre
        audio.save()
        return True
