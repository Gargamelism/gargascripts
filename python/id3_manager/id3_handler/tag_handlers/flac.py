"""FLAC tag handler."""

from mutagen.flac import FLAC

from models import TrackMetadata
from id3_handler.formats import parse_track_disc, parse_year


class FlacTagHandler:
    """Reads and writes tags for FLAC files."""

    def read_tags(self, file_path: str) -> TrackMetadata:
        audio = FLAC(file_path)
        track_num, total_tracks = parse_track_disc(audio.get("tracknumber", [""])[0])
        if total_tracks is None:
            total_str = audio.get("totaltracks", [""])[0]
            if total_str:
                try:
                    total_tracks = int(total_str)
                except ValueError:
                    pass
        disc_num, total_discs = parse_track_disc(audio.get("discnumber", [""])[0])
        if total_discs is None:
            total_str = audio.get("totaldiscs", [""])[0]
            if total_str:
                try:
                    total_discs = int(total_str)
                except ValueError:
                    pass
        return TrackMetadata(
            title=audio.get("title", [None])[0],
            artist=audio.get("artist", [None])[0],
            album=audio.get("album", [None])[0],
            album_artist=audio.get("albumartist", [None])[0],
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_num,
            total_discs=total_discs,
            year=parse_year(audio.get("date", [""])[0]),
            genre=audio.get("genre", [None])[0],
        )

    def write_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        audio = FLAC(file_path)
        if metadata.title:
            audio["title"] = metadata.title
        if metadata.artist:
            audio["artist"] = metadata.artist
        if metadata.album:
            audio["album"] = metadata.album
        if metadata.album_artist:
            audio["albumartist"] = metadata.album_artist
        if metadata.track_number:
            audio["tracknumber"] = str(metadata.track_number)
        if metadata.total_tracks:
            audio["totaltracks"] = str(metadata.total_tracks)
        if metadata.disc_number:
            audio["discnumber"] = str(metadata.disc_number)
        if metadata.total_discs:
            audio["totaldiscs"] = str(metadata.total_discs)
        if metadata.year:
            audio["date"] = str(metadata.year)
        if metadata.genre:
            audio["genre"] = metadata.genre
        audio.save()
        return True
