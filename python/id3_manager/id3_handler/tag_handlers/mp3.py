"""MP3 tag handler."""

from mutagen.mp3 import MP3
from mutagen.id3 import TIT2, TPE1, TALB, TPE2, TRCK, TPOS, TDRC, TCON

from models import TrackMetadata
from id3_handler.formats import parse_track_disc, parse_year, get_tag_str

ID3_ENCODING_UTF8 = 3


class Mp3TagHandler:
    """Reads and writes tags for MP3 files."""

    def read_tags(self, file_path: str) -> TrackMetadata:
        audio = MP3(file_path)
        tags = audio.tags or {}
        track_num, total_tracks = parse_track_disc(get_tag_str(tags, "TRCK") or "")
        disc_num, total_discs = parse_track_disc(get_tag_str(tags, "TPOS") or "")
        return TrackMetadata(
            title=get_tag_str(tags, "TIT2"),
            artist=get_tag_str(tags, "TPE1"),
            album=get_tag_str(tags, "TALB"),
            album_artist=get_tag_str(tags, "TPE2"),
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_num,
            total_discs=total_discs,
            year=parse_year(get_tag_str(tags, "TDRC")),
            genre=get_tag_str(tags, "TCON"),
        )

    def write_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        audio = MP3(file_path)
        if audio.tags is None:
            audio.add_tags()
        if metadata.title:
            audio.tags.add(TIT2(encoding=ID3_ENCODING_UTF8, text=metadata.title))
        if metadata.artist:
            audio.tags.add(TPE1(encoding=ID3_ENCODING_UTF8, text=metadata.artist))
        if metadata.album:
            audio.tags.add(TALB(encoding=ID3_ENCODING_UTF8, text=metadata.album))
        if metadata.album_artist:
            audio.tags.add(TPE2(encoding=ID3_ENCODING_UTF8, text=metadata.album_artist))
        if metadata.track_number:
            track_str = str(metadata.track_number)
            if metadata.total_tracks:
                track_str += f"/{metadata.total_tracks}"
            audio.tags.add(TRCK(encoding=ID3_ENCODING_UTF8, text=track_str))
        if metadata.disc_number:
            disc_str = str(metadata.disc_number)
            if metadata.total_discs:
                disc_str += f"/{metadata.total_discs}"
            audio.tags.add(TPOS(encoding=ID3_ENCODING_UTF8, text=disc_str))
        if metadata.year:
            audio.tags.add(TDRC(encoding=ID3_ENCODING_UTF8, text=str(metadata.year)))
        if metadata.genre:
            audio.tags.add(TCON(encoding=ID3_ENCODING_UTF8, text=metadata.genre))
        audio.save()
        return True
