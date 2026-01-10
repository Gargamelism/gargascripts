"""Tests for utils.py utility functions."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import sanitize_filename, generate_expected_filename, file_needs_rename
from models import TrackMetadata


class TestSanitizeFilename:
    """Tests for sanitize_filename function."""

    def test_replaces_invalid_characters(self):
        """Should replace invalid filename characters with underscore."""
        result = sanitize_filename('Test: File <name> "with" /invalid\\chars?')
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "?" not in result

    def test_strips_leading_trailing_dots_and_spaces(self):
        """Should strip leading/trailing dots and spaces."""
        assert sanitize_filename("  .test. ") == "test"
        assert sanitize_filename("...name...") == "name"

    def test_collapses_multiple_spaces(self):
        """Should collapse multiple spaces to single space."""
        assert sanitize_filename("test    name") == "test name"

    def test_collapses_multiple_underscores(self):
        """Should collapse multiple underscores to single underscore."""
        assert sanitize_filename("test____name") == "test_name"


class TestGenerateExpectedFilename:
    """Tests for generate_expected_filename function."""

    def test_generates_correct_format(self):
        """Should generate filename in correct format."""
        meta = TrackMetadata(
            title="Song Title",
            artist="Artist Name",
            album="Album Name",
            track_number=5
        )
        result = generate_expected_filename(meta, ".mp3")
        assert result == "Artist Name - Album Name - 05 - Song Title.mp3"

    def test_pads_track_number(self):
        """Should zero-pad track number to 2 digits."""
        meta = TrackMetadata(
            title="Song", artist="Artist", album="Album", track_number=1
        )
        result = generate_expected_filename(meta, ".mp3")
        assert "- 01 -" in result

    def test_includes_cd_for_multi_disc(self):
        """Should include CD number for multi-disc albums."""
        meta = TrackMetadata(
            title="Song", artist="Artist", album="Album",
            track_number=1, disc_number=2, total_discs=3
        )
        result = generate_expected_filename(meta, ".mp3")
        assert "Album CD2" in result

    def test_no_cd_for_single_disc(self):
        """Should not include CD number for single disc albums."""
        meta = TrackMetadata(
            title="Song", artist="Artist", album="Album",
            track_number=1, disc_number=1, total_discs=1
        )
        result = generate_expected_filename(meta, ".mp3")
        assert "CD" not in result

    def test_returns_none_when_missing_title(self):
        """Should return None when title is missing."""
        meta = TrackMetadata(artist="Artist", album="Album", track_number=1)
        assert generate_expected_filename(meta, ".mp3") is None

    def test_returns_none_when_missing_artist(self):
        """Should return None when artist is missing."""
        meta = TrackMetadata(title="Song", album="Album", track_number=1)
        assert generate_expected_filename(meta, ".mp3") is None

    def test_returns_none_when_missing_album(self):
        """Should return None when album is missing."""
        meta = TrackMetadata(title="Song", artist="Artist", track_number=1)
        assert generate_expected_filename(meta, ".mp3") is None

    def test_returns_none_when_missing_track_number(self):
        """Should return None when track_number is missing."""
        meta = TrackMetadata(title="Song", artist="Artist", album="Album")
        assert generate_expected_filename(meta, ".mp3") is None

    def test_sanitizes_special_characters(self):
        """Should sanitize special characters in metadata."""
        meta = TrackMetadata(
            title="Song: The Remix?",
            artist="Artist/Band",
            album="Album <Deluxe>",
            track_number=1
        )
        result = generate_expected_filename(meta, ".mp3")
        assert ":" not in result
        assert "/" not in result
        assert "<" not in result
        assert "?" not in result


class TestFileNeedsRename:
    """Tests for file_needs_rename function."""

    def test_returns_true_when_name_differs(self):
        """Should return True when filename doesn't match expected."""
        meta = TrackMetadata(
            title="Song", artist="Artist", album="Album", track_number=1
        )
        assert file_needs_rename("/path/to/wrong_name.mp3", meta) is True

    def test_returns_false_when_name_matches(self):
        """Should return False when filename matches expected."""
        meta = TrackMetadata(
            title="Song", artist="Artist", album="Album", track_number=1
        )
        assert file_needs_rename("/path/to/Artist - Album - 01 - Song.mp3", meta) is False

    def test_returns_false_when_metadata_incomplete(self):
        """Should return False when required metadata is missing."""
        meta = TrackMetadata(title="Song")  # Missing artist, album, track_number
        assert file_needs_rename("/path/to/anything.mp3", meta) is False

    def test_handles_different_extensions(self):
        """Should work with different file extensions."""
        meta = TrackMetadata(
            title="Song", artist="Artist", album="Album", track_number=1
        )
        assert file_needs_rename("/path/Artist - Album - 01 - Song.flac", meta) is False
        assert file_needs_rename("/path/Artist - Album - 01 - Song.m4a", meta) is False
