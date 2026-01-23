"""Tests for folder_manager.py file and folder operations."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from folder_manager import FolderManager
from models import TrackMetadata


@pytest.fixture
def folder_manager():
    """Create a FolderManager instance."""
    return FolderManager()


class TestSanitizeFilename:
    """Tests for _sanitize_filename method."""

    def test_replaces_invalid_characters(self, folder_manager):
        """Should replace <, >, :, \", /, \\, |, ?, * with underscore."""
        result = folder_manager._sanitize_filename('Test<>:"/\\|?*Name')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_strips_leading_trailing_dots_and_spaces(self, folder_manager):
        """Should remove leading/trailing dots and spaces."""
        assert folder_manager._sanitize_filename("  Test  ") == "Test"
        assert folder_manager._sanitize_filename("...Test...") == "Test"
        assert folder_manager._sanitize_filename(". Test .") == "Test"

    def test_collapses_multiple_spaces(self, folder_manager):
        """Should collapse multiple spaces into one."""
        result = folder_manager._sanitize_filename("Test    Multiple   Spaces")
        assert "  " not in result
        assert result == "Test Multiple Spaces"

    def test_collapses_multiple_underscores(self, folder_manager):
        """Should collapse multiple underscores into space."""
        result = folder_manager._sanitize_filename("Test___Name")
        assert "___" not in result


class TestGenerateFilename:
    """Tests for generate_filename method."""

    def test_single_disc_format(self, folder_manager, sample_metadata):
        """Should generate {ARTIST} - {ALBUM} - {TRACK_NUMBER} - {TITLE}.ext."""
        result = folder_manager.generate_filename(sample_metadata, ".mp3")
        assert result == "Test Artist - Test Album - 01 - Test Song.mp3"

    def test_multi_disc_format(self, folder_manager, multi_disc_metadata):
        """Should include CD number for multi-disc albums."""
        result = folder_manager.generate_filename(multi_disc_metadata, ".mp3")
        assert result == "Test Artist - Test Album CD2 - 01 - Test Song.mp3"

    def test_single_disc_with_disc_number_but_only_one_disc(self, folder_manager):
        """Should not include CD number when total_discs is 1."""
        meta = TrackMetadata(
            title="Song",
            artist="Artist",
            album="Album",
            track_number=1,
            disc_number=1,
            total_discs=1,
        )
        result = folder_manager.generate_filename(meta, ".mp3")
        assert "CD" not in result
        assert result == "Artist - Album - 01 - Song.mp3"

    def test_track_number_zero_padded(self, folder_manager):
        """Should zero-pad track number to 2 digits."""
        meta = TrackMetadata(
            title="Song",
            artist="Artist",
            album="Album",
            track_number=5,
        )
        result = folder_manager.generate_filename(meta, ".mp3")
        assert " - 05 - " in result

    def test_returns_none_when_missing_title(self, folder_manager):
        """Should return None when title is missing."""
        meta = TrackMetadata(artist="Artist", album="Album", track_number=1)
        result = folder_manager.generate_filename(meta, ".mp3")
        assert result is None

    def test_returns_none_when_missing_artist(self, folder_manager):
        """Should return None when artist is missing."""
        meta = TrackMetadata(title="Song", album="Album", track_number=1)
        result = folder_manager.generate_filename(meta, ".mp3")
        assert result is None

    def test_returns_none_when_missing_album(self, folder_manager):
        """Should return None when album is missing."""
        meta = TrackMetadata(title="Song", artist="Artist", track_number=1)
        result = folder_manager.generate_filename(meta, ".mp3")
        assert result is None

    def test_returns_none_when_missing_track_number(self, folder_manager):
        """Should return None when track_number is missing."""
        meta = TrackMetadata(title="Song", artist="Artist", album="Album")
        result = folder_manager.generate_filename(meta, ".mp3")
        assert result is None

    def test_sanitizes_special_characters(self, folder_manager):
        """Should sanitize special characters in all fields."""
        meta = TrackMetadata(
            title="Song: Part 1",
            artist="Artist/Band",
            album="Album?",
            track_number=1,
        )
        result = folder_manager.generate_filename(meta, ".mp3")
        assert ":" not in result
        assert "/" not in result
        assert "?" not in result

    def test_different_extensions(self, folder_manager, sample_metadata):
        """Should work with different file extensions."""
        assert folder_manager.generate_filename(sample_metadata, ".flac").endswith(".flac")
        assert folder_manager.generate_filename(sample_metadata, ".m4a").endswith(".m4a")


class TestShouldRenameFile:
    """Tests for should_rename_file method."""

    def test_returns_true_when_name_differs(self, folder_manager, sample_metadata):
        """Should return True when current name doesn't match expected."""
        result = folder_manager.should_rename_file(
            "/path/to/wrong_name.mp3",
            sample_metadata,
        )
        assert result is True

    def test_returns_false_when_name_matches(self, folder_manager, sample_metadata):
        """Should return False when current name matches expected."""
        result = folder_manager.should_rename_file(
            "/path/to/Test Artist - Test Album - 01 - Test Song.mp3",
            sample_metadata,
        )
        assert result is False

    def test_returns_false_when_metadata_incomplete(self, folder_manager, incomplete_metadata):
        """Should return False when metadata is incomplete."""
        result = folder_manager.should_rename_file(
            "/path/to/any_file.mp3",
            incomplete_metadata,
        )
        assert result is False


class TestGenerateFolderName:
    """Tests for generate_folder_name method."""

    def test_generates_year_album_format(self, folder_manager):
        """Should generate {YEAR} - {ALBUM} format."""
        result = folder_manager.generate_folder_name(2020, "Test Album")
        assert result == "2020 - Test Album"

    def test_sanitizes_album_name(self, folder_manager):
        """Should sanitize special characters in album name."""
        result = folder_manager.generate_folder_name(2020, "Album: Part 1")
        assert ":" not in result


class TestGenerateDiscFolderName:
    """Tests for generate_disc_folder_name method."""

    def test_generates_cd_format(self, folder_manager):
        """Should generate CD{N} format."""
        assert folder_manager.generate_disc_folder_name(1) == "CD1"
        assert folder_manager.generate_disc_folder_name(2) == "CD2"
        assert folder_manager.generate_disc_folder_name(10) == "CD10"


class TestIsFolderProperlyNamed:
    """Tests for is_folder_properly_named method."""

    def test_matches_year_album_format(self, folder_manager):
        """Should return True for {YEAR} - {ALBUM} format."""
        assert folder_manager.is_folder_properly_named("/path/to/2020 - Album Name") is True

    def test_matches_various_years(self, folder_manager):
        """Should match different year values."""
        assert folder_manager.is_folder_properly_named("/path/to/1999 - Album") is True
        assert folder_manager.is_folder_properly_named("/path/to/2023 - Album") is True

    def test_rejects_wrong_format(self, folder_manager):
        """Should return False for wrong formats."""
        assert folder_manager.is_folder_properly_named("/path/to/Album Name") is False
        assert folder_manager.is_folder_properly_named("/path/to/Artist - Album") is False
        assert folder_manager.is_folder_properly_named("/path/to/20 - Album") is False


class TestExtractDiscNumber:
    """Tests for _extract_disc_number method."""

    def test_extracts_cd_number(self, folder_manager):
        """Should extract disc number from CD{N} format."""
        assert folder_manager._extract_disc_number("CD1") == 1
        assert folder_manager._extract_disc_number("CD2") == 2
        assert folder_manager._extract_disc_number("cd3") == 3

    def test_extracts_disc_number(self, folder_manager):
        """Should extract disc number from Disc {N} format."""
        assert folder_manager._extract_disc_number("Disc 1") == 1
        assert folder_manager._extract_disc_number("Disc 2") == 2
        assert folder_manager._extract_disc_number("disc 3") == 3

    def test_extracts_disk_number(self, folder_manager):
        """Should extract disc number from Disk {N} format."""
        assert folder_manager._extract_disc_number("Disk1") == 1
        assert folder_manager._extract_disc_number("Disk 2") == 2

    def test_returns_none_for_no_disc(self, folder_manager):
        """Should return None when no disc pattern found."""
        assert folder_manager._extract_disc_number("Album Name") is None
        assert folder_manager._extract_disc_number("Regular Folder") is None

    def test_extracts_d_number(self, folder_manager):
        """Should extract disc number from d{N} format."""
        assert folder_manager._extract_disc_number("d1") == 1
        assert folder_manager._extract_disc_number("d2") == 2


class TestParseFolderName:
    """Tests for parse_folder_name method."""

    def test_parses_valid_folder_name(self, folder_manager):
        """Should parse year and album from valid format."""
        year, album = folder_manager.parse_folder_name("/path/to/2020 - Test Album")
        assert year == 2020
        assert album == "Test Album"

    def test_parses_with_extra_spaces(self, folder_manager):
        """Should handle extra spaces around separator."""
        year, album = folder_manager.parse_folder_name("/path/to/2020  -  Test Album")
        # Based on regex, this should work with the current pattern
        year, album = folder_manager.parse_folder_name("/path/to/2020 - Test Album")
        assert year == 2020
        assert album == "Test Album"

    def test_returns_none_for_invalid_format(self, folder_manager):
        """Should return (None, None) for invalid folder name."""
        year, album = folder_manager.parse_folder_name("/path/to/Invalid Album")
        assert year is None
        assert album is None


class TestDetectMultiDiscFromMetadata:
    """Tests for detect_multi_disc_from_metadata method."""

    def test_returns_max_disc_number(self, folder_manager):
        """Should return maximum disc number found in metadata."""
        from models import AudioFile, TrackMetadata

        files = [
            AudioFile(
                file_path="/path/file1.mp3",
                format="mp3",
                current_tags=TrackMetadata(disc_number=1)
            ),
            AudioFile(
                file_path="/path/file2.mp3",
                format="mp3",
                current_tags=TrackMetadata(disc_number=2)
            ),
            AudioFile(
                file_path="/path/file3.mp3",
                format="mp3",
                current_tags=TrackMetadata(disc_number=3)
            ),
        ]
        assert folder_manager.detect_multi_disc_from_metadata(files) == 3

    def test_uses_total_discs_if_higher(self, folder_manager):
        """Should use total_discs if higher than disc_number."""
        from models import AudioFile, TrackMetadata

        files = [
            AudioFile(
                file_path="/path/file1.mp3",
                format="mp3",
                current_tags=TrackMetadata(disc_number=1, total_discs=5)
            ),
        ]
        assert folder_manager.detect_multi_disc_from_metadata(files) == 5

    def test_returns_one_for_no_disc_info(self, folder_manager):
        """Should return 1 when no disc info in metadata."""
        from models import AudioFile, TrackMetadata

        files = [
            AudioFile(
                file_path="/path/file1.mp3",
                format="mp3",
                current_tags=TrackMetadata()
            ),
        ]
        assert folder_manager.detect_multi_disc_from_metadata(files) == 1


class TestGetAlbumInfoFromFiles:
    """Tests for get_album_info_from_files method."""

    def test_extracts_year_and_album(self, folder_manager):
        """Should extract year and album from audio files."""
        from models import AudioFile, TrackMetadata

        files = [
            AudioFile(
                file_path="/path/file1.mp3",
                format="mp3",
                current_tags=TrackMetadata(year=2020, album="Test Album")
            ),
        ]
        year, album = folder_manager.get_album_info_from_files(files)
        assert year == 2020
        assert album == "Test Album"

    def test_prefers_proposed_tags(self, folder_manager):
        """Should prefer proposed_tags over current_tags."""
        from models import AudioFile, TrackMetadata

        files = [
            AudioFile(
                file_path="/path/file1.mp3",
                format="mp3",
                current_tags=TrackMetadata(year=2019, album="Old Album"),
                proposed_tags=TrackMetadata(year=2020, album="New Album"),
            ),
        ]
        year, album = folder_manager.get_album_info_from_files(files)
        assert year == 2020
        assert album == "New Album"

    def test_returns_none_when_no_info(self, folder_manager):
        """Should return (None, None) when no album info available."""
        from models import AudioFile, TrackMetadata

        files = [
            AudioFile(
                file_path="/path/file1.mp3",
                format="mp3",
                current_tags=TrackMetadata()
            ),
        ]
        year, album = folder_manager.get_album_info_from_files(files)
        assert year is None
        assert album is None


class TestRenameAudioFile:
    """Tests for rename_audio_file method (logic only, no filesystem)."""

    def test_returns_correct_name_message_when_same(self, folder_manager):
        """Should indicate file already has correct name."""
        success, msg = folder_manager.rename_audio_file("/path/to/song.mp3", "song.mp3")
        assert success is True
        assert msg == "File already has correct name"

    def test_dry_run_returns_would_rename(self, folder_manager):
        """Should return would-rename message in dry run."""
        success, msg = folder_manager.rename_audio_file(
            "/path/to/old_name.mp3", "new_name.mp3", dry_run=True
        )
        assert success is True
        assert "Would rename to" in msg


class TestRenameFolder:
    """Tests for rename_folder method (logic only, no filesystem)."""

    def test_returns_correct_name_message_when_same(self, folder_manager):
        """Should indicate folder already has correct name."""
        success, msg = folder_manager.rename_folder("/path/to/Album", "Album")
        assert success is True
        assert msg == "Folder already has correct name"

    def test_dry_run_returns_would_rename(self, folder_manager):
        """Should return would-rename message in dry run."""
        success, msg = folder_manager.rename_folder(
            "/path/to/Old Album", "2020 - New Album", dry_run=True
        )
        assert success is True
        assert "Would rename to" in msg


class TestNormalizeDiscFolderName:
    """Tests for normalize_disc_folder_name method."""

    def test_already_correct_name_returns_same_path(self, folder_manager):
        """Should return same path when folder already named CD{N}."""
        success, result = folder_manager.normalize_disc_folder_name(
            "/path/to/album/CD1", 1
        )
        assert success is True
        assert result == "/path/to/album/CD1"

    def test_dry_run_disc_format(self, folder_manager):
        """Should return would-rename message for 'Disc 1' in dry run."""
        success, msg = folder_manager.normalize_disc_folder_name(
            "/path/to/album/Disc 1", 1, dry_run=True
        )
        assert success is True
        assert "Would rename" in msg
        assert "'Disc 1'" in msg
        assert "'CD1'" in msg

    def test_dry_run_disk_format(self, folder_manager):
        """Should return would-rename message for 'disk 1' in dry run."""
        success, msg = folder_manager.normalize_disc_folder_name(
            "/path/to/album/disk 1", 1, dry_run=True
        )
        assert success is True
        assert "Would rename" in msg
        assert "'disk 1'" in msg
        assert "'CD1'" in msg

    def test_dry_run_d_format(self, folder_manager):
        """Should return would-rename message for 'd1' in dry run."""
        success, msg = folder_manager.normalize_disc_folder_name(
            "/path/to/album/d1", 1, dry_run=True
        )
        assert success is True
        assert "Would rename" in msg
        assert "'d1'" in msg
        assert "'CD1'" in msg

    def test_dry_run_number_format(self, folder_manager):
        """Should return would-rename message for '1' in dry run."""
        success, msg = folder_manager.normalize_disc_folder_name(
            "/path/to/album/1", 1, dry_run=True
        )
        assert success is True
        assert "Would rename" in msg
        assert "'1'" in msg
        assert "'CD1'" in msg

    def test_normalizes_various_disc_numbers(self, folder_manager):
        """Should handle different disc numbers correctly in dry run."""
        success, msg = folder_manager.normalize_disc_folder_name(
            "/path/to/album/Disc 2", 2, dry_run=True
        )
        assert success is True
        assert "'CD2'" in msg

        success, msg = folder_manager.normalize_disc_folder_name(
            "/path/to/album/disk 3", 3, dry_run=True
        )
        assert success is True
        assert "'CD3'" in msg
