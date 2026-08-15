"""ID3 tag handler using mutagen for cross-format support."""

import logging
from pathlib import Path
from typing import Optional

from models import AudioFormat, TrackMetadata
from id3_handler.tag_handlers import (
    Mp3TagHandler,
    FlacTagHandler,
    M4aTagHandler,
    WmaTagHandler,
)
from id3_handler.tag_handlers.mp3 import ID3_ENCODING_UTF8  # noqa: F401 (re-exported)
from id3_handler.backup import SafeWriter

logger = logging.getLogger(__name__)


class ID3Handler:
    """Handles reading and writing ID3 tags using mutagen."""

    SUPPORTED_EXTENSIONS = {
        f".{fmt.value}" for fmt in AudioFormat if fmt is not AudioFormat.UNKNOWN
    }

    def __init__(self, writer=None):
        self._writer = writer or SafeWriter()

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def get_format(cls, file_path: str) -> Optional[AudioFormat]:
        ext = Path(file_path).suffix.lower()
        if ext in cls.SUPPORTED_EXTENSIONS:
            return AudioFormat(ext[1:])
        return None

    def read_tags(self, file_path: str) -> TrackMetadata:
        ext = Path(file_path).suffix.lower()
        match ext:
            case ".mp3":
                return self._read_mp3_tags(file_path)
            case ".flac":
                return self._read_flac_tags(file_path)
            case ".m4a":
                return self._read_m4a_tags(file_path)
            case ".wma":
                return self._read_wma_tags(file_path)
            case _:
                logger.warning(f"Unsupported format: {ext}")
                return TrackMetadata()

    def _read_mp3_tags(self, file_path: str) -> TrackMetadata:
        return Mp3TagHandler().read_tags(file_path)

    def _read_flac_tags(self, file_path: str) -> TrackMetadata:
        return FlacTagHandler().read_tags(file_path)

    def _read_m4a_tags(self, file_path: str) -> TrackMetadata:
        return M4aTagHandler().read_tags(file_path)

    def _read_wma_tags(self, file_path: str) -> TrackMetadata:
        return WmaTagHandler().read_tags(file_path)

    def write_tags(
        self, file_path: str, metadata: TrackMetadata, preserve_existing: bool = True
    ) -> bool:
        return self._writer.write(self, file_path, metadata, preserve_existing)

    def _write_mp3_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        return Mp3TagHandler().write_tags(file_path, metadata)

    def _write_flac_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        return FlacTagHandler().write_tags(file_path, metadata)

    def _write_m4a_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        return M4aTagHandler().write_tags(file_path, metadata)

    def _write_wma_tags(self, file_path: str, metadata: TrackMetadata) -> bool:
        return WmaTagHandler().write_tags(file_path, metadata)
