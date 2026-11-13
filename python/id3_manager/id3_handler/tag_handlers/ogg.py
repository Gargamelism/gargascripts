"""OGG tag handler (Vorbis comments — same layout as FLAC)."""

from mutagen import File

from id3_handler.tag_handlers.flac import FlacTagHandler


class OggTagHandler(FlacTagHandler):
    """Reads and writes tags for OGG files (Vorbis, Opus, OGG FLAC)."""

    def _open(self, file_path: str):
        audio = File(file_path)
        if audio is None:
            raise ValueError(f"Not a recognized OGG file: {file_path}")
        return audio
