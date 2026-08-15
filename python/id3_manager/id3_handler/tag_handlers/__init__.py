"""Per-format tag handlers implementing the TagHandler protocol."""

from id3_handler.tag_handlers.protocol import TagHandler
from id3_handler.tag_handlers.mp3 import Mp3TagHandler
from id3_handler.tag_handlers.flac import FlacTagHandler
from id3_handler.tag_handlers.m4a import M4aTagHandler
from id3_handler.tag_handlers.wma import WmaTagHandler

__all__ = [
    "TagHandler",
    "Mp3TagHandler",
    "FlacTagHandler",
    "M4aTagHandler",
    "WmaTagHandler",
]
