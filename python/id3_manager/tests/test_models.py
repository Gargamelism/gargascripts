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
