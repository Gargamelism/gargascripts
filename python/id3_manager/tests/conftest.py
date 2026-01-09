"""Shared test fixtures for id3_manager tests."""

import sys
from pathlib import Path

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import TrackMetadata, DiscogsRelease, DiscogsTrack, AudioFile


@pytest.fixture
def sample_metadata():
    """Basic complete metadata for a single-disc album."""
    return TrackMetadata(
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        track_number=1,
        total_tracks=10,
        year=2020,
    )


@pytest.fixture
def multi_disc_metadata():
    """Metadata for a track on a multi-disc album."""
    return TrackMetadata(
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        track_number=1,
        total_tracks=5,
        disc_number=2,
        total_discs=3,
        year=2020,
    )


@pytest.fixture
def incomplete_metadata():
    """Metadata missing required fields."""
    return TrackMetadata(
        title="Test Song",
        artist=None,
        album="Test Album",
    )


@pytest.fixture
def sample_discogs_track():
    """A single Discogs track."""
    return DiscogsTrack(
        position="A1",
        title="Test Song",
        duration="3:45",
        track_number=1,
        disc_number=1,
    )


@pytest.fixture
def sample_discogs_release(sample_discogs_track):
    """A Discogs release with tracks."""
    return DiscogsRelease(
        release_id=12345,
        title="Test Album",
        artists=["Test Artist"],
        year=2020,
        tracklist=[
            sample_discogs_track,
            DiscogsTrack(position="A2", title="Another Song", track_number=2, disc_number=1),
            DiscogsTrack(position="B1", title="Third Song", track_number=3, disc_number=1),
        ],
        total_discs=1,
        genres=["Rock", "Alternative"],
        label="Test Label",
    )


@pytest.fixture
def sample_audio_file(sample_metadata):
    """An AudioFile object with complete tags."""
    return AudioFile(
        file_path="/fake/path/song.mp3",
        format="mp3",
        current_tags=sample_metadata,
    )
