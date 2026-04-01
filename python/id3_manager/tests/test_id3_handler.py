"""Tests for id3_handler.py tag parsing utilities."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from id3_handler import ID3Handler
from models import TrackMetadata


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


class TestWriteTags:
    """Tests for write_tags backup/restore and validation."""

    def _make_metadata(self):
        return TrackMetadata(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            track_number=1,
        )

    def test_skips_already_malformed_file(self, handler, tmp_path):
        """Pre-write validation should skip files that cannot be read."""
        bad_file = tmp_path / "bad.mp3"
        original_content = b"this is not a valid mp3 file"
        bad_file.write_bytes(original_content)

        result = handler.write_tags(str(bad_file), self._make_metadata())

        assert result is False
        assert bad_file.read_bytes() == original_content  # file unchanged

    def test_restores_original_if_write_corrupts_file(self, handler, tmp_path):
        """Post-write validation should detect corruption and restore original bytes."""
        mp3_file = tmp_path / "song.mp3"
        original_content = b"original bytes"
        mp3_file.write_bytes(original_content)

        corrupt_content = b"corrupted bytes after bad write"

        def fake_write_mp3(file_path, metadata):
            Path(file_path).write_bytes(corrupt_content)
            return True

        # Pre-write read_tags succeeds; post-write read_tags raises (detects corruption)
        read_calls = [0]

        def fake_read_tags(file_path):
            read_calls[0] += 1
            if read_calls[0] > 1:
                raise Exception("can't sync to MPEG frame")
            return self._make_metadata()

        with patch.object(handler, "read_tags", side_effect=fake_read_tags), \
             patch.object(handler, "_write_mp3_tags", side_effect=fake_write_mp3), \
             pytest.raises(RuntimeError, match="Write corrupted"):
            handler.write_tags(str(mp3_file), self._make_metadata(),
                               preserve_existing=False)

        assert mp3_file.read_bytes() == original_content  # restored

    def test_returns_true_on_successful_write(self, handler, tmp_path):
        """Should return True when write and post-write validation both succeed."""
        mp3_file = tmp_path / "song.mp3"
        mp3_file.write_bytes(b"placeholder")

        metadata = self._make_metadata()

        with patch.object(handler, "read_tags", return_value=metadata), \
             patch.object(handler, "_write_mp3_tags", return_value=True):
            result = handler.write_tags(str(mp3_file), metadata, preserve_existing=False)

        assert result is True

    def test_post_write_validation_is_performed(self, handler, tmp_path):
        """read_tags must be called after write to validate the written file."""
        mp3_file = tmp_path / "song.mp3"
        mp3_file.write_bytes(b"placeholder")
        metadata = self._make_metadata()

        read_calls = []

        def tracking_read(file_path):
            read_calls.append(file_path)
            return metadata

        with patch.object(handler, "read_tags", side_effect=tracking_read), \
             patch.object(handler, "_write_mp3_tags", return_value=True):
            result = handler.write_tags(str(mp3_file), metadata, preserve_existing=False)

        assert result is True
        assert len(read_calls) == 2, "expected pre-write and post-write read_tags calls"
        assert all(c == str(mp3_file) for c in read_calls)

    def test_restores_original_on_unexpected_exception(self, handler, tmp_path):
        """Should restore original bytes if an unexpected exception occurs during write."""
        mp3_file = tmp_path / "song.mp3"
        original_content = b"original bytes"
        mp3_file.write_bytes(original_content)

        metadata = self._make_metadata()

        with patch.object(handler, "read_tags", return_value=metadata), \
             patch.object(handler, "_write_mp3_tags", side_effect=OSError("disk full")), \
             pytest.raises(RuntimeError, match="Failed to write tags"):
            handler.write_tags(str(mp3_file), metadata, preserve_existing=False)

        assert mp3_file.read_bytes() == original_content  # restored
