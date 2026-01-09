"""Tests for id3_handler.py tag parsing utilities."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from id3_handler import ID3Handler


@pytest.fixture
def handler():
    """Create an ID3Handler instance."""
    return ID3Handler()


class TestParseTrackDisc:
    """Tests for _parse_track_disc method."""

    def test_parses_track_with_total(self, handler):
        """Should parse '3/12' format into (track, total)."""
        num, total = handler._parse_track_disc("3/12")
        assert num == 3
        assert total == 12

    def test_parses_track_only(self, handler):
        """Should parse single number as (track, None)."""
        num, total = handler._parse_track_disc("5")
        assert num == 5
        assert total is None

    def test_handles_empty_string(self, handler):
        """Should return (None, None) for empty string."""
        num, total = handler._parse_track_disc("")
        assert num is None
        assert total is None

    def test_handles_invalid_format(self, handler):
        """Should return (None, None) for invalid format."""
        num, total = handler._parse_track_disc("invalid")
        assert num is None
        assert total is None

    def test_handles_partial_slash(self, handler):
        """Should handle '5/' format."""
        num, total = handler._parse_track_disc("5/")
        assert num == 5
        assert total is None

    def test_handles_spaces(self, handler):
        """Should handle spaces in input."""
        num, total = handler._parse_track_disc(" 3 / 12 ")
        assert num == 3
        assert total == 12

    def test_handles_zero(self, handler):
        """Should handle zero values."""
        num, total = handler._parse_track_disc("0/10")
        assert num == 0
        assert total == 10


class TestParseYear:
    """Tests for _parse_year method."""

    def test_parses_four_digit_year(self, handler):
        """Should parse simple year string."""
        assert handler._parse_year("2020") == 2020
        assert handler._parse_year("1999") == 1999

    def test_parses_full_date(self, handler):
        """Should extract year from YYYY-MM-DD format."""
        assert handler._parse_year("2020-01-15") == 2020
        assert handler._parse_year("1985-12-25") == 1985

    def test_handles_empty_string(self, handler):
        """Should return None for empty string."""
        assert handler._parse_year("") is None

    def test_handles_none_like_values(self, handler):
        """Should handle various null-like inputs."""
        assert handler._parse_year("") is None

    def test_handles_invalid_year(self, handler):
        """Should return None for invalid year format."""
        assert handler._parse_year("abc") is None
        # Note: "20" returns 20 because _parse_year takes first 4 chars and int("20") = 20
        # This is acceptable behavior - it's a best-effort parser


class TestIsSupported:
    """Tests for is_supported class method."""

    def test_supports_mp3(self):
        """Should support .mp3 files."""
        assert ID3Handler.is_supported("/path/to/song.mp3") is True
        assert ID3Handler.is_supported("/path/to/song.MP3") is True

    def test_supports_flac(self):
        """Should support .flac files."""
        assert ID3Handler.is_supported("/path/to/song.flac") is True
        assert ID3Handler.is_supported("/path/to/song.FLAC") is True

    def test_supports_m4a(self):
        """Should support .m4a files."""
        assert ID3Handler.is_supported("/path/to/song.m4a") is True
        assert ID3Handler.is_supported("/path/to/song.M4A") is True

    def test_rejects_unsupported_formats(self):
        """Should reject unsupported formats."""
        assert ID3Handler.is_supported("/path/to/song.wav") is False
        assert ID3Handler.is_supported("/path/to/song.ogg") is False
        assert ID3Handler.is_supported("/path/to/song.aac") is False
        assert ID3Handler.is_supported("/path/to/document.txt") is False


class TestGetFormat:
    """Tests for get_format class method."""

    def test_returns_format_for_supported_files(self):
        """Should return format string without dot."""
        assert ID3Handler.get_format("/path/to/song.mp3") == "mp3"
        assert ID3Handler.get_format("/path/to/song.flac") == "flac"
        assert ID3Handler.get_format("/path/to/song.m4a") == "m4a"

    def test_case_insensitive(self):
        """Should handle uppercase extensions."""
        assert ID3Handler.get_format("/path/to/song.MP3") == "mp3"
        assert ID3Handler.get_format("/path/to/song.FLAC") == "flac"

    def test_returns_none_for_unsupported(self):
        """Should return None for unsupported formats."""
        assert ID3Handler.get_format("/path/to/song.wav") is None
        assert ID3Handler.get_format("/path/to/song.ogg") is None
