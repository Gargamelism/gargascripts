"""ID3 tag handler using mutagen for cross-format support."""

from pathlib import Path
from typing import Optional

from mutagen import File
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TPOS, TDRC, TCON

from config import eprint
from models import TrackMetadata
from id3_handler.formats import (
    MP4_TAGS as _MP4_TAGS,
    parse_track_disc as _parse_track_disc,
    parse_year as _parse_year,
    get_tag_str as _get_tag_str,
    get_mp4_tag as _get_mp4_tag,
)
from id3_handler.backup import SafeWriter


class ID3Handler:
    """Handles reading and writing ID3 tags using mutagen."""

    SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a"}

    MP4_TAGS = _MP4_TAGS

    def __init__(self, writer=None):
        self._writer = writer or SafeWriter()

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def get_format(cls, file_path: str) -> Optional[str]:
        ext = Path(file_path).suffix.lower()
        if ext in cls.SUPPORTED_EXTENSIONS:
            return ext[1:]
        return None

    def read_tags(self, file_path: str) -> TrackMetadata:
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext == ".mp3":
            return self._read_mp3_tags(file_path)
        elif ext == ".flac":
            return self._read_flac_tags(file_path)
        elif ext == ".m4a":
            return self._read_m4a_tags(file_path)
        else:
            eprint(f"Unsupported format: {ext}")
            return TrackMetadata()

    def _read_mp3_tags(self, file_path: str) -> TrackMetadata:
        audio = MP3(file_path)
        tags = audio.tags or {}
        track_num, total_tracks = _parse_track_disc(
            str(tags.get("TRCK", [""])[0]) if tags.get("TRCK") else ""
        )
        disc_num, total_discs = _parse_track_disc(
            str(tags.get("TPOS", [""])[0]) if tags.get("TPOS") else ""
        )
        return TrackMetadata(
            title=_get_tag_str(tags, "TIT2"),
            artist=_get_tag_str(tags, "TPE1"),
            album=_get_tag_str(tags, "TALB"),
            album_artist=_get_tag_str(tags, "TPE2"),
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_num,
            total_discs=total_discs,
            year=_parse_year(_get_tag_str(tags, "TDRC")),
            genre=_get_tag_str(tags, "TCON"),
        )

    def _read_flac_tags(self, file_path: str) -> TrackMetadata:
        audio = FLAC(file_path)
        track_num, total_tracks = _parse_track_disc(
            audio.get("tracknumber", [""])[0]
        )
        if total_tracks is None:
            total_str = audio.get("totaltracks", [""])[0]
            if total_str:
                try:
                    total_tracks = int(total_str)
                except ValueError:
                    pass
        disc_num, total_discs = _parse_track_disc(
            audio.get("discnumber", [""])[0]
        )
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
            year=_parse_year(audio.get("date", [""])[0]),
            genre=audio.get("genre", [None])[0],
        )

    def _read_m4a_tags(self, file_path: str) -> TrackMetadata:
        audio = MP4(file_path)
        tags = audio.tags or {}
        track_info = tags.get(self.MP4_TAGS["track"], [(None, None)])[0]
        disc_info = tags.get(self.MP4_TAGS["disc"], [(None, None)])[0]
        track_num = track_info[0] if track_info and track_info[0] else None
        total_tracks = track_info[1] if track_info and len(track_info) > 1 and track_info[1] else None
        disc_num = disc_info[0] if disc_info and disc_info[0] else None
        total_discs = disc_info[1] if disc_info and len(disc_info) > 1 and disc_info[1] else None
        return TrackMetadata(
            title=_get_mp4_tag(tags, "title", _MP4_TAGS),
            artist=_get_mp4_tag(tags, "artist", _MP4_TAGS),
            album=_get_mp4_tag(tags, "album", _MP4_TAGS),
            album_artist=_get_mp4_tag(tags, "album_artist", _MP4_TAGS),
            track_number=track_num,
            total_tracks=total_tracks,
            disc_number=disc_num,
            total_discs=total_discs,
            year=_parse_year(_get_mp4_tag(tags, "year", _MP4_TAGS) or ""),
            genre=_get_mp4_tag(tags, "genre", _MP4_TAGS),
        )

    def write_tags(self, file_path: str, metadata: TrackMetadata,
                   preserve_existing: bool = True) -> bool:
        return self._writer.write(self, file_path, metadata, preserve_existing)

    def _write_mp3_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        audio = MP3(file_path)
        if audio.tags is None:
            audio.add_tags()
        if metadata.title:
            audio.tags.add(TIT2(encoding=3, text=metadata.title))
        if metadata.artist:
            audio.tags.add(TPE1(encoding=3, text=metadata.artist))
        if metadata.album:
            audio.tags.add(TALB(encoding=3, text=metadata.album))
        if metadata.album_artist:
            audio.tags.add(TPE2(encoding=3, text=metadata.album_artist))
        if metadata.track_number:
            track_str = str(metadata.track_number)
            if metadata.total_tracks:
                track_str += f"/{metadata.total_tracks}"
            audio.tags.add(TRCK(encoding=3, text=track_str))
        if metadata.disc_number:
            disc_str = str(metadata.disc_number)
            if metadata.total_discs:
                disc_str += f"/{metadata.total_discs}"
            audio.tags.add(TPOS(encoding=3, text=disc_str))
        if metadata.year:
            audio.tags.add(TDRC(encoding=3, text=str(metadata.year)))
        if metadata.genre:
            audio.tags.add(TCON(encoding=3, text=metadata.genre))
        audio.save()
        return True

    def _write_flac_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
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

    def _write_m4a_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        audio = MP4(file_path)
        if audio.tags is None:
            audio.add_tags()
        if metadata.title:
            audio.tags[self.MP4_TAGS["title"]] = [metadata.title]
        if metadata.artist:
            audio.tags[self.MP4_TAGS["artist"]] = [metadata.artist]
        if metadata.album:
            audio.tags[self.MP4_TAGS["album"]] = [metadata.album]
        if metadata.album_artist:
            audio.tags[self.MP4_TAGS["album_artist"]] = [metadata.album_artist]
        if metadata.track_number:
            audio.tags[self.MP4_TAGS["track"]] = [
                (metadata.track_number, metadata.total_tracks or 0)
            ]
        if metadata.disc_number:
            audio.tags[self.MP4_TAGS["disc"]] = [
                (metadata.disc_number, metadata.total_discs or 0)
            ]
        if metadata.year:
            audio.tags[self.MP4_TAGS["year"]] = [str(metadata.year)]
        if metadata.genre:
            audio.tags[self.MP4_TAGS["genre"]] = [metadata.genre]
        audio.save()
        return True

