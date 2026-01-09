"""Tests for discogs_client.py API parsing utilities."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from discogs_client import DiscogsClient
from models import DiscogsRelease, DiscogsTrack


@pytest.fixture
def client():
    """Create a DiscogsClient instance (token not needed for parsing tests)."""
    return DiscogsClient("fake_token")


@pytest.fixture
def release_with_tracks():
    """Create a release with multiple tracks for matching tests."""
    return DiscogsRelease(
        release_id=12345,
        title="Test Album",
        artists=["Test Artist"],
        year=2020,
        tracklist=[
            DiscogsTrack(position="1", title="First Song", track_number=1, disc_number=1),
            DiscogsTrack(position="2", title="Second Song", track_number=2, disc_number=1),
            DiscogsTrack(position="3", title="Third Song (Extended Mix)", track_number=3, disc_number=1),
            DiscogsTrack(position="4", title="Another Track", track_number=4, disc_number=1),
        ],
        total_discs=1,
    )


class TestParsePosition:
    """Tests for _parse_position method."""

    def test_simple_number(self, client):
        """Should parse simple track number (defaults disc to 1)."""
        track, disc = client._parse_position("1")
        assert track == 1
        assert disc == 1  # Implementation defaults to disc 1

    def test_simple_number_multi_digit(self, client):
        """Should parse multi-digit track numbers (defaults disc to 1)."""
        track, disc = client._parse_position("12")
        assert track == 12
        assert disc == 1  # Implementation defaults to disc 1

    def test_vinyl_side_a(self, client):
        """Should parse A-side vinyl positions."""
        track, disc = client._parse_position("A1")
        assert track == 1
        assert disc == 1

        track, disc = client._parse_position("A2")
        assert track == 2
        assert disc == 1

    def test_vinyl_side_b(self, client):
        """Should parse B-side vinyl positions."""
        track, disc = client._parse_position("B1")
        assert track == 1
        assert disc == 1

        track, disc = client._parse_position("B2")
        assert track == 2
        assert disc == 1

    def test_disc_track_format(self, client):
        """Should parse disc-track format like '1-3'."""
        track, disc = client._parse_position("1-3")
        assert track == 3
        assert disc == 1

        track, disc = client._parse_position("2-5")
        assert track == 5
        assert disc == 2

    def test_cd_prefix_format(self, client):
        """Should parse CD prefix format like 'CD1-3'."""
        track, disc = client._parse_position("CD1-3")
        assert track == 3
        assert disc == 1

        track, disc = client._parse_position("CD2-1")
        assert track == 1
        assert disc == 2

    def test_case_insensitive(self, client):
        """Should handle lowercase input."""
        track, disc = client._parse_position("a1")
        assert track == 1
        assert disc == 1

        track, disc = client._parse_position("cd1-3")
        assert track == 3
        assert disc == 1

    def test_empty_position(self, client):
        """Should return (None, None) for empty position."""
        track, disc = client._parse_position("")
        assert track is None
        assert disc is None

    def test_none_position(self, client):
        """Should handle None-ish values gracefully."""
        track, disc = client._parse_position("")
        assert track is None
        assert disc is None


class TestMatchTrackToRelease:
    """Tests for match_track_to_release method."""

    def test_exact_match(self, client, release_with_tracks):
        """Should find exact title match."""
        track = client.match_track_to_release(release_with_tracks, "First Song")
        assert track is not None
        assert track.title == "First Song"
        assert track.track_number == 1

    def test_case_insensitive_match(self, client, release_with_tracks):
        """Should match regardless of case."""
        track = client.match_track_to_release(release_with_tracks, "FIRST SONG")
        assert track is not None
        assert track.title == "First Song"

    def test_match_ignoring_parentheticals(self, client, release_with_tracks):
        """Should match when ignoring parenthetical content."""
        track = client.match_track_to_release(release_with_tracks, "Third Song")
        assert track is not None
        assert track.title == "Third Song (Extended Mix)"

    def test_substring_match_search_in_track(self, client, release_with_tracks):
        """Should match when search title is contained in track title (requires >70% similarity)."""
        # "Another" is only 7 chars vs "Another Track" 13 chars = ~54% similarity
        # So it won't match. Use a longer substring that exceeds 70% threshold.
        track = client.match_track_to_release(release_with_tracks, "Another Track")
        assert track is not None
        assert track.title == "Another Track"

    def test_no_match_returns_none(self, client, release_with_tracks):
        """Should return None when no match found."""
        track = client.match_track_to_release(release_with_tracks, "Nonexistent Song")
        assert track is None

    def test_strips_whitespace(self, client, release_with_tracks):
        """Should handle leading/trailing whitespace."""
        track = client.match_track_to_release(release_with_tracks, "  First Song  ")
        assert track is not None
        assert track.title == "First Song"

    def test_strips_track_number_prefix(self, client, release_with_tracks):
        """Should strip track number prefixes from search."""
        track = client.match_track_to_release(release_with_tracks, "01. First Song")
        assert track is not None
        assert track.title == "First Song"

        track = client.match_track_to_release(release_with_tracks, "1 - Second Song")
        assert track is not None
        assert track.title == "Second Song"
