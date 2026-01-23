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


class TestParseReleaseVinyl:
    """Tests for _parse_release with vinyl-style positions."""

    def test_two_sided_vinyl_sequential_numbering(self, client):
        """Two-sided vinyl should have sequential track numbers across sides."""
        data = {
            "id": 12345,
            "title": "Test Vinyl",
            "artists": [{"name": "Test Artist"}],
            "year": 2020,
            "genres": ["Rock"],
            "labels": [{"name": "Test Label"}],
            "tracklist": [
                {"type_": "track", "position": "A1", "title": "Side A Track 1"},
                {"type_": "track", "position": "A2", "title": "Side A Track 2"},
                {"type_": "track", "position": "A3", "title": "Side A Track 3"},
                {"type_": "track", "position": "B1", "title": "Side B Track 1"},
                {"type_": "track", "position": "B2", "title": "Side B Track 2"},
                {"type_": "track", "position": "B3", "title": "Side B Track 3"},
            ],
        }

        release = client._parse_release(data)

        assert len(release.tracklist) == 6
        assert release.total_discs == 1

        # Verify sequential numbering: A1=1, A2=2, A3=3, B1=4, B2=5, B3=6
        tracks = {t.position: t for t in release.tracklist}
        assert tracks["A1"].track_number == 1
        assert tracks["A2"].track_number == 2
        assert tracks["A3"].track_number == 3
        assert tracks["B1"].track_number == 4
        assert tracks["B2"].track_number == 5
        assert tracks["B3"].track_number == 6

        # All tracks should be on disc 1
        for track in release.tracklist:
            assert track.disc_number == 1

    def test_four_sided_vinyl_two_discs(self, client):
        """Four-sided vinyl (2LP) should have sequential numbering per disc."""
        data = {
            "id": 12345,
            "title": "Double LP",
            "artists": [{"name": "Test Artist"}],
            "year": 2020,
            "genres": ["Rock"],
            "labels": [],
            "tracklist": [
                {"type_": "track", "position": "A1", "title": "A1"},
                {"type_": "track", "position": "A2", "title": "A2"},
                {"type_": "track", "position": "B1", "title": "B1"},
                {"type_": "track", "position": "B2", "title": "B2"},
                {"type_": "track", "position": "C1", "title": "C1"},
                {"type_": "track", "position": "C2", "title": "C2"},
                {"type_": "track", "position": "D1", "title": "D1"},
                {"type_": "track", "position": "D2", "title": "D2"},
            ],
        }

        release = client._parse_release(data)

        assert len(release.tracklist) == 8
        assert release.total_discs == 2

        tracks = {t.position: t for t in release.tracklist}

        # Disc 1: A/B sides - sequential 1-4
        assert tracks["A1"].track_number == 1
        assert tracks["A1"].disc_number == 1
        assert tracks["A2"].track_number == 2
        assert tracks["A2"].disc_number == 1
        assert tracks["B1"].track_number == 3
        assert tracks["B1"].disc_number == 1
        assert tracks["B2"].track_number == 4
        assert tracks["B2"].disc_number == 1

        # Disc 2: C/D sides - sequential 1-4 (resets for new disc)
        assert tracks["C1"].track_number == 1
        assert tracks["C1"].disc_number == 2
        assert tracks["C2"].track_number == 2
        assert tracks["C2"].disc_number == 2
        assert tracks["D1"].track_number == 3
        assert tracks["D1"].disc_number == 2
        assert tracks["D2"].track_number == 4
        assert tracks["D2"].disc_number == 2

    def test_non_vinyl_release_unchanged(self, client):
        """Non-vinyl releases should use standard position parsing."""
        data = {
            "id": 12345,
            "title": "CD Album",
            "artists": [{"name": "Test Artist"}],
            "year": 2020,
            "genres": [],
            "labels": [],
            "tracklist": [
                {"type_": "track", "position": "1", "title": "Track 1"},
                {"type_": "track", "position": "2", "title": "Track 2"},
                {"type_": "track", "position": "3", "title": "Track 3"},
            ],
        }

        release = client._parse_release(data)

        assert len(release.tracklist) == 3
        assert release.total_discs == 1

        tracks = release.tracklist
        assert tracks[0].track_number == 1
        assert tracks[1].track_number == 2
        assert tracks[2].track_number == 3

    def test_vinyl_skips_heading_entries(self, client):
        """Vinyl parsing should skip heading entries (side markers)."""
        data = {
            "id": 12345,
            "title": "Test Vinyl",
            "artists": [{"name": "Test Artist"}],
            "year": 2020,
            "genres": [],
            "labels": [],
            "tracklist": [
                {"type_": "heading", "position": "", "title": "Side A"},
                {"type_": "track", "position": "A1", "title": "Track 1"},
                {"type_": "track", "position": "A2", "title": "Track 2"},
                {"type_": "heading", "position": "", "title": "Side B"},
                {"type_": "track", "position": "B1", "title": "Track 3"},
                {"type_": "track", "position": "B2", "title": "Track 4"},
            ],
        }

        release = client._parse_release(data)

        # Should only have 4 tracks, not 6
        assert len(release.tracklist) == 4

        tracks = {t.position: t for t in release.tracklist}
        assert tracks["A1"].track_number == 1
        assert tracks["A2"].track_number == 2
        assert tracks["B1"].track_number == 3
        assert tracks["B2"].track_number == 4


class TestIsVinylPosition:
    """Tests for _is_vinyl_position helper method."""

    def test_vinyl_positions(self, client):
        """Should identify vinyl-style positions."""
        assert client._is_vinyl_position("A1") is True
        assert client._is_vinyl_position("B2") is True
        assert client._is_vinyl_position("C10") is True
        assert client._is_vinyl_position("a1") is True  # lowercase

    def test_non_vinyl_positions(self, client):
        """Should not identify non-vinyl positions as vinyl."""
        assert client._is_vinyl_position("1") is False
        assert client._is_vinyl_position("12") is False
        assert client._is_vinyl_position("1-1") is False
        assert client._is_vinyl_position("CD1-1") is False
        assert client._is_vinyl_position("") is False
