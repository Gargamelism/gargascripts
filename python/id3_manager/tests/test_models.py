"""Tests for models.py data classes."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import TrackMetadata, TagStatus, DiscogsRelease, DiscogsTrack, AudioFile


class TestTrackMetadata:
    """Tests for TrackMetadata dataclass."""

    def test_is_complete_with_all_required_fields(self, sample_metadata):
        """Should return True when title, artist, and track_number are present."""
        assert sample_metadata.is_complete() is True

    def test_is_complete_missing_title(self):
        """Should return False when title is missing."""
        meta = TrackMetadata(artist="Artist", track_number=1)
        assert meta.is_complete() is False

    def test_is_complete_missing_artist(self):
        """Should return False when artist is missing."""
        meta = TrackMetadata(title="Song", track_number=1)
        assert meta.is_complete() is False

    def test_is_complete_missing_track_number(self):
        """Should return False when track_number is missing."""
        meta = TrackMetadata(title="Song", artist="Artist")
        assert meta.is_complete() is False

    def test_is_complete_multi_disc_requires_disc_number(self):
        """Should return False for multi-disc when disc_number is missing."""
        meta = TrackMetadata(title="Song", artist="Artist", track_number=1)
        assert meta.is_complete(is_multi_disc=True) is False

    def test_is_complete_multi_disc_with_disc_number(self):
        """Should return True for multi-disc when disc_number is present."""
        meta = TrackMetadata(title="Song", artist="Artist", track_number=1, disc_number=2)
        assert meta.is_complete(is_multi_disc=True) is True

    def test_get_status_complete(self, sample_metadata):
        """Should return COMPLETE when all required fields present."""
        assert sample_metadata.get_status() == TagStatus.COMPLETE

    def test_get_status_partial_with_some_fields(self):
        """Should return PARTIAL when some but not all required fields present."""
        meta = TrackMetadata(title="Song", artist="Artist")
        assert meta.get_status() == TagStatus.PARTIAL

    def test_get_status_missing_with_no_fields(self):
        """Should return MISSING when no title, artist, or album."""
        meta = TrackMetadata()
        assert meta.get_status() == TagStatus.MISSING

    def test_get_status_partial_with_only_album(self):
        """Should return PARTIAL when only album is present."""
        meta = TrackMetadata(album="Album")
        assert meta.get_status() == TagStatus.PARTIAL

    def test_merge_with_fills_missing_fields(self):
        """Should fill missing fields from other metadata."""
        meta1 = TrackMetadata(title="Song", artist="Artist")
        meta2 = TrackMetadata(album="Album", year=2020, track_number=5)

        merged = meta1.merge_with(meta2)

        assert merged.title == "Song"
        assert merged.artist == "Artist"
        assert merged.album == "Album"
        assert merged.year == 2020
        assert merged.track_number == 5

    def test_merge_with_preserves_existing_fields(self):
        """Should not overwrite existing fields."""
        meta1 = TrackMetadata(title="Original", year=2019)
        meta2 = TrackMetadata(title="Other", year=2020, album="Album")

        merged = meta1.merge_with(meta2)

        assert merged.title == "Original"
        assert merged.year == 2019
        assert merged.album == "Album"

    def test_get_missing_required_fields_returns_empty_when_complete(self):
        """Should return empty list when all required fields present."""
        meta = TrackMetadata(title="Song", artist="Artist", album="Album", track_number=1)
        assert meta.get_missing_required_fields() == []

    def test_get_missing_required_fields_returns_missing_title(self):
        """Should include 'title' when title is missing."""
        meta = TrackMetadata(artist="Artist", album="Album", track_number=1)
        missing = meta.get_missing_required_fields()
        assert "title" in missing
        assert "artist" not in missing

    def test_get_missing_required_fields_returns_missing_artist(self):
        """Should include 'artist' when artist is missing."""
        meta = TrackMetadata(title="Song", album="Album", track_number=1)
        missing = meta.get_missing_required_fields()
        assert "artist" in missing
        assert "title" not in missing

    def test_get_missing_required_fields_returns_missing_album(self):
        """Should include 'album' when album is missing."""
        meta = TrackMetadata(title="Song", artist="Artist", track_number=1)
        missing = meta.get_missing_required_fields()
        assert "album" in missing

    def test_get_missing_required_fields_returns_missing_track_number(self):
        """Should include 'track_number' when track_number is missing."""
        meta = TrackMetadata(title="Song", artist="Artist", album="Album")
        missing = meta.get_missing_required_fields()
        assert "track_number" in missing

    def test_get_missing_required_fields_returns_multiple_missing(self):
        """Should return all missing required fields."""
        meta = TrackMetadata(title="Song")  # Missing artist, album, track_number
        missing = meta.get_missing_required_fields()
        assert len(missing) == 3
        assert "artist" in missing
        assert "album" in missing
        assert "track_number" in missing


class TestDiscogsRelease:
    """Tests for DiscogsRelease dataclass."""

    def test_find_track_exact_match(self, sample_discogs_release):
        """Should find track with exact title match."""
        track = sample_discogs_release.find_track("Test Song")
        assert track is not None
        assert track.title == "Test Song"

    def test_find_track_partial_match_title_contains(self, sample_discogs_release):
        """Should find track when search title is contained in track title."""
        track = sample_discogs_release.find_track("Another")
        assert track is not None
        assert track.title == "Another Song"

    def test_find_track_partial_match_track_contains(self, sample_discogs_release):
        """Should find track when track title is contained in search."""
        track = sample_discogs_release.find_track("Third Song (Extended Mix)")
        assert track is not None
        assert track.title == "Third Song"

    def test_find_track_case_insensitive(self, sample_discogs_release):
        """Should find track regardless of case."""
        track = sample_discogs_release.find_track("TEST SONG")
        assert track is not None
        assert track.title == "Test Song"

    def test_find_track_no_match(self, sample_discogs_release):
        """Should return None when no match found."""
        track = sample_discogs_release.find_track("Nonexistent Song")
        assert track is None


class TestAudioFile:
    """Tests for AudioFile dataclass."""

    def test_tag_status_returns_current_tags_status(self, sample_audio_file):
        """Should return status based on current_tags."""
        assert sample_audio_file.tag_status == TagStatus.COMPLETE

    def test_needs_processing_false_when_complete(self, sample_audio_file):
        """Should not need processing when tags are complete."""
        assert sample_audio_file.needs_processing is False

    def test_needs_processing_true_when_partial(self, incomplete_metadata):
        """Should need processing when tags are incomplete."""
        af = AudioFile(
            file_path="/fake/path/song.mp3",
            format="mp3",
            current_tags=incomplete_metadata,
        )
        assert af.needs_processing is True

    def test_needs_processing_true_when_missing(self):
        """Should need processing when tags are missing."""
        af = AudioFile(
            file_path="/fake/path/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        assert af.needs_processing is True

    def test_needs_rename_true_when_filename_differs(self):
        """Should need rename when filename doesn't match expected format."""
        af = AudioFile(
            file_path="/fake/path/wrong_name.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song", artist="Artist", album="Album", track_number=1
            ),
        )
        # Expected: "Artist - Album - 01 - Song.mp3"
        assert af.needs_rename is True

    def test_needs_rename_false_when_filename_matches(self):
        """Should not need rename when filename matches expected format."""
        af = AudioFile(
            file_path="/fake/path/Artist - Album - 01 - Song.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song", artist="Artist", album="Album", track_number=1
            ),
        )
        assert af.needs_rename is False

    def test_needs_rename_false_when_metadata_incomplete(self):
        """Should not need rename when required metadata is missing."""
        af = AudioFile(
            file_path="/fake/path/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(title="Song"),  # Missing artist, album, track
        )
        assert af.needs_rename is False


class TestAudioFileHashability:
    """Tests for AudioFile __hash__ method and set usage."""

    def test_hash_based_on_file_path(self):
        """Should hash based on file_path."""
        af1 = AudioFile(
            file_path="/path/to/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        af2 = AudioFile(
            file_path="/path/to/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(title="Different"),
        )
        assert hash(af1) == hash(af2)

    def test_different_paths_have_different_hashes(self):
        """Should have different hashes for different file paths."""
        af1 = AudioFile(
            file_path="/path/to/song1.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        af2 = AudioFile(
            file_path="/path/to/song2.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        assert hash(af1) != hash(af2)

    def test_can_be_added_to_set(self):
        """Should be usable in a set."""
        af = AudioFile(
            file_path="/path/to/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        audio_set = {af}
        assert len(audio_set) == 1
        assert af in audio_set

    def test_set_deduplicates_same_path(self):
        """Set should deduplicate AudioFiles with same file_path."""
        af1 = AudioFile(
            file_path="/path/to/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        af2 = AudioFile(
            file_path="/path/to/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(title="Different"),
        )
        audio_set = {af1, af2}
        assert len(audio_set) == 1

    def test_set_keeps_different_paths(self):
        """Set should keep AudioFiles with different file_paths."""
        af1 = AudioFile(
            file_path="/path/to/song1.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        af2 = AudioFile(
            file_path="/path/to/song2.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )
        audio_set = {af1, af2}
        assert len(audio_set) == 2

    def test_set_comprehension_deduplicates(self):
        """Set comprehension should properly deduplicate AudioFiles."""
        audio_files = [
            AudioFile("/path/song1.mp3", "mp3", TrackMetadata(title="A")),
            AudioFile("/path/song2.mp3", "mp3", TrackMetadata(title="B")),
            AudioFile("/path/song1.mp3", "mp3", TrackMetadata(title="C")),  # Duplicate path
        ]
        # Simulates the pattern used in main.py _process_folder
        unique_files = {af for af in audio_files}
        assert len(unique_files) == 2

    def test_set_union_with_overlapping_files(self):
        """Set union should correctly handle overlapping AudioFiles."""
        af1 = AudioFile("/path/song1.mp3", "mp3", TrackMetadata())
        af2 = AudioFile("/path/song2.mp3", "mp3", TrackMetadata())
        af3 = AudioFile("/path/song1.mp3", "mp3", TrackMetadata())  # Same as af1

        needs_processing = {af1}
        needs_rename = {af2, af3}

        # Union should have 2 unique files
        combined = needs_processing | needs_rename
        assert len(combined) == 2

    def test_files_needing_work_pattern(self):
        """Test the exact pattern used in _process_folder for files needing work."""
        # File needs both processing and rename
        af_both = AudioFile(
            file_path="/path/wrong_name.mp3",
            format="mp3",
            current_tags=TrackMetadata(title="Song"),  # Incomplete - needs processing
        )
        # File needs only processing (correct name but incomplete tags)
        af_processing = AudioFile(
            file_path="/path/Artist - Album - 01 - Song.mp3",
            format="mp3",
            current_tags=TrackMetadata(title="Song"),  # Incomplete
        )
        # File needs only rename (complete tags but wrong name)
        af_rename = AudioFile(
            file_path="/path/wrong_name2.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song", artist="Artist", album="Album", track_number=1
            ),
        )

        audio_files = [af_both, af_processing, af_rename]

        # Pattern from main.py
        files_needing_work = {
            af for af in audio_files if af.needs_processing or af.needs_rename
        }

        assert len(files_needing_work) == 3
        assert af_both in files_needing_work
        assert af_processing in files_needing_work
        assert af_rename in files_needing_work
