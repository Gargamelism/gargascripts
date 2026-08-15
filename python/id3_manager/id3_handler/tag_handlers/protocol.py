"""Protocol for per-format tag handlers."""

from typing import Protocol

from models import TrackMetadata


class TagHandler(Protocol):
    """Reads and writes tags for a single audio format."""

    def read_tags(self, file_path: str) -> TrackMetadata: ...

    def write_tags(self, file_path: str, metadata: TrackMetadata) -> bool: ...
