"""Extra coverage tests for discogs_client.py."""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from discogs_client import DiscogsClient
from discogs_client.parsing import parse_position, parse_release
from models import DiscogsRelease, DiscogsTrack


@pytest.fixture
def client():
    with patch("discogs_client.requests.Session") as MockSession:
        MockSession.return_value = MagicMock()
        c = DiscogsClient("fake_token")
    return c


def _make_resp(json_data, status=200, headers=None):
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status
    resp.headers = headers or {"X-Discogs-Ratelimit-Remaining": "55"}
    resp.raise_for_status = MagicMock()
    return resp


def _release_data(tracks=None):
    return {
        "id": 123,
        "title": "Test Album",
        "artists": [{"name": "Test Artist"}],
        "year": 2020,
        "tracklist": tracks or [
            {"type_": "track", "position": "1", "title": "Track One"},
            {"type_": "track", "position": "2", "title": "Track Two"},
        ],
        "genres": ["Rock"],
        "labels": [{"name": "Test Label"}],
    }


# ---------------------------------------------------------------------------
# _respect_rate_limit
# ---------------------------------------------------------------------------

class TestRespectRateLimit:
    def test_sleeps_when_too_soon(self, client):
        client._last_request_time = time.time()  # just now
        with patch("discogs_client.time.sleep") as mock_sleep, \
             patch("discogs_client.time.time", return_value=client._last_request_time + 0.3):
            client._respect_rate_limit()
        mock_sleep.assert_called_once()
        args = mock_sleep.call_args[0][0]
        assert abs(args - 0.7) < 0.1

    def test_no_sleep_when_enough_time_elapsed(self, client):
        client._last_request_time = time.time() - 2.0
        with patch("discogs_client.time.sleep") as mock_sleep:
            client._respect_rate_limit()
        mock_sleep.assert_not_called()

    def test_sleeps_60s_near_rate_limit(self, client):
        client.rate_limit_remaining = 3
        client._last_request_time = 0  # long ago
        with patch("discogs_client.time.sleep") as mock_sleep:
            client._respect_rate_limit()
        mock_sleep.assert_called_with(60)
        assert client.rate_limit_remaining == 60


# ---------------------------------------------------------------------------
# _update_rate_limit
# ---------------------------------------------------------------------------

class TestUpdateRateLimit:
    def test_updates_remaining(self, client):
        resp = _make_resp({}, headers={"X-Discogs-Ratelimit-Remaining": "42"})
        client._update_rate_limit(resp)
        assert client.rate_limit_remaining == 42

    def test_no_header_does_not_crash(self, client):
        resp = _make_resp({}, headers={})
        client._update_rate_limit(resp)  # should not raise

    def test_updates_last_request_time(self, client):
        client._last_request_time = 0
        resp = _make_resp({}, headers={})
        with patch("discogs_client.time.time", return_value=999.0):
            client._update_rate_limit(resp)
        assert client._last_request_time == 999.0


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_returns_results(self, client):
        resp = _make_resp({"results": [{"id": 1}, {"id": 2}]})
        client.session.get.return_value = resp
        with patch.object(client, "_respect_rate_limit"), \
             patch.object(client, "_update_rate_limit"):
            results = client.search("Artist", album="Album")
        assert len(results) == 2

    def test_includes_track_param(self, client):
        resp = _make_resp({"results": []})
        client.session.get.return_value = resp
        with patch.object(client, "_respect_rate_limit"), \
             patch.object(client, "_update_rate_limit"):
            client.search("Artist", track="Song")
        params = client.session.get.call_args[1]["params"]
        assert "track" in params

    def test_returns_empty_on_exception(self, client):
        client.session.get.side_effect = requests.exceptions.RequestException("err")
        with patch.object(client, "_respect_rate_limit"):
            results = client.search("Artist")
        assert results == []


# ---------------------------------------------------------------------------
# get_release
# ---------------------------------------------------------------------------

class TestGetRelease:
    def test_returns_release_on_success(self, client):
        resp = _make_resp(_release_data())
        client.session.get.return_value = resp
        with patch.object(client, "_respect_rate_limit"), \
             patch.object(client, "_update_rate_limit"):
            release = client.get_release(123)
        assert release is not None
        assert release.title == "Test Album"

    def test_returns_none_on_404(self, client):
        resp = _make_resp({}, status=404)
        http_err = requests.exceptions.HTTPError(response=resp)
        resp.raise_for_status.side_effect = http_err
        client.session.get.return_value = resp
        with patch.object(client, "_respect_rate_limit"), \
             patch.object(client, "_update_rate_limit"):
            result = client.get_release(999)
        assert result is None

    def test_returns_none_on_http_error(self, client):
        resp = _make_resp({}, status=500)
        http_err = requests.exceptions.HTTPError(response=MagicMock(status_code=500))
        resp.raise_for_status.side_effect = http_err
        client.session.get.return_value = resp
        with patch.object(client, "_respect_rate_limit"), \
             patch.object(client, "_update_rate_limit"):
            result = client.get_release(1)
        assert result is None

    def test_returns_none_on_request_exception(self, client):
        client.session.get.side_effect = requests.exceptions.RequestException("net")
        with patch.object(client, "_respect_rate_limit"):
            result = client.get_release(1)
        assert result is None


# ---------------------------------------------------------------------------
# _parse_release — vinyl and multi-disc
# ---------------------------------------------------------------------------

class TestParseRelease:
    def test_parses_non_vinyl_simple(self, client):
        data = _release_data([
            {"type_": "track", "position": "1", "title": "One"},
            {"type_": "track", "position": "2", "title": "Two"},
        ])
        release = parse_release(data)
        assert len(release.tracklist) == 2
        assert release.tracklist[0].track_number == 1
        assert release.tracklist[1].track_number == 2

    def test_parses_vinyl_positions(self, client):
        data = _release_data([
            {"type_": "track", "position": "A1", "title": "Side A Track 1"},
            {"type_": "track", "position": "A2", "title": "Side A Track 2"},
            {"type_": "track", "position": "B1", "title": "Side B Track 1"},
        ])
        release = parse_release(data)
        assert len(release.tracklist) == 3
        # All on disc 1 (sides A and B)
        assert all(t.disc_number == 1 for t in release.tracklist)
        # Sequential numbering: 1, 2, 1 (B resets)
        track_nums = [t.track_number for t in release.tracklist]
        assert track_nums == [1, 2, 3]

    def test_parses_vinyl_multi_disc(self, client):
        data = _release_data([
            {"type_": "track", "position": "A1", "title": "A1"},
            {"type_": "track", "position": "B1", "title": "B1"},
            {"type_": "track", "position": "C1", "title": "C1"},  # disc 2
            {"type_": "track", "position": "D1", "title": "D1"},  # disc 2
        ])
        release = parse_release(data)
        discs = {t.disc_number for t in release.tracklist}
        assert 1 in discs
        assert 2 in discs

    def test_skips_non_track_types(self, client):
        data = _release_data([
            {"type_": "heading", "position": "", "title": "Side A"},
            {"type_": "track", "position": "1", "title": "Real Track"},
        ])
        release = parse_release(data)
        assert len(release.tracklist) == 1

    def test_handles_no_labels(self, client):
        data = _release_data()
        data["labels"] = []
        release = parse_release(data)
        assert release.label is None

    def test_strips_artist_numbering(self, client):
        data = _release_data()
        data["artists"] = [{"name": "Artist (2)"}]
        release = parse_release(data)
        assert release.artists == ["Artist"]

    def test_mixed_vinyl_and_non_vinyl(self, client):
        data = _release_data([
            {"type_": "track", "position": "A1", "title": "Vinyl"},
            {"type_": "track", "position": "5", "title": "NonVinyl"},
        ])
        release = parse_release(data)
        assert len(release.tracklist) == 2

    def test_disc_track_format(self, client):
        data = _release_data([
            {"type_": "track", "position": "1-1", "title": "D1T1"},
            {"type_": "track", "position": "1-2", "title": "D1T2"},
            {"type_": "track", "position": "2-1", "title": "D2T1"},
        ])
        release = parse_release(data)
        assert release.total_discs == 2
        assert release.tracklist[2].disc_number == 2


# ---------------------------------------------------------------------------
# _parse_position
# ---------------------------------------------------------------------------

class TestParsePosition:
    def test_simple_number(self):
        assert parse_position("3") == (3, 1)

    def test_disc_track_format(self):
        assert parse_position("2-5") == (5, 2)

    def test_cd_format(self):
        assert parse_position("CD2-3") == (3, 2)

    def test_vinyl_format(self):
        track, disc = parse_position("B2")
        assert track == 2
        assert disc == 1

    def test_empty_returns_none_none(self):
        assert parse_position("") == (None, None)

    def test_unrecognized_returns_none_none(self):
        assert parse_position("???") == (None, None)


# ---------------------------------------------------------------------------
# find_best_release
# ---------------------------------------------------------------------------

class TestFindBestRelease:
    def _mock_release(self, n_tracks=3):
        tracks = [DiscogsTrack(position=str(i), title=f"T{i}", track_number=i, disc_number=1)
                  for i in range(1, n_tracks + 1)]
        return DiscogsRelease(
            release_id=1, title="Album", artists=["Artist"],
            year=2020, tracklist=tracks, total_discs=1,
        )

    def test_searches_with_album(self, client):
        release = self._mock_release()
        with patch.object(client, "search", return_value=[{"id": 1}]) as mock_search, \
             patch.object(client, "get_release", return_value=release):
            client.find_best_release("Artist", album="Album")
        mock_search.assert_called_with("Artist", album="Album")

    def test_falls_back_to_track_search(self, client):
        release = self._mock_release()
        call_count = [0]

        def fake_search(artist, album=None, track=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return []  # album search → empty
            return [{"id": 1}]

        with patch.object(client, "search", side_effect=fake_search), \
             patch.object(client, "get_release", return_value=release):
            results = client.find_best_release("Artist", album="Album", track="Song")
        assert len(results) > 0

    def test_falls_back_to_artist_only(self, client):
        release = self._mock_release()

        def fake_search(artist, album=None, track=None):
            if album is None and track is None:
                return [{"id": 1}]
            return []

        with patch.object(client, "search", side_effect=fake_search), \
             patch.object(client, "get_release", return_value=release):
            results = client.find_best_release("Artist")
        assert len(results) > 0

    def test_returns_empty_when_no_results(self, client):
        with patch.object(client, "search", return_value=[]):
            results = client.find_best_release("Artist")
        assert results == []

    def test_skips_releases_without_tracklist(self, client):
        empty_release = DiscogsRelease(
            release_id=1, title="Album", artists=["Artist"],
            year=2020, tracklist=[], total_discs=1,
        )
        with patch.object(client, "search", return_value=[{"id": 1}]), \
             patch.object(client, "get_release", return_value=empty_release):
            results = client.find_best_release("Artist")
        assert results == []

    def test_sorts_by_track_count(self, client):
        r_short = self._mock_release(n_tracks=2)
        r_long = self._mock_release(n_tracks=10)
        results_list = [r_short, r_long]
        with patch.object(client, "search", return_value=[{"id": 1}, {"id": 2}]), \
             patch.object(client, "get_release", side_effect=results_list):
            results = client.find_best_release("Artist")
        assert results[0].tracklist == r_long.tracklist


# ---------------------------------------------------------------------------
# match_track_to_release — exact / substring / threshold / none
# ---------------------------------------------------------------------------

class TestMatchTrackToRelease:
    def _release_with(self, *titles):
        tracks = [DiscogsTrack(position=str(i+1), title=t, track_number=i+1, disc_number=1)
                  for i, t in enumerate(titles)]
        return DiscogsRelease(
            release_id=1, title="A", artists=["A"],
            year=2020, tracklist=tracks, total_discs=1,
        )

    def test_exact_match(self, client):
        release = self._release_with("Hello World", "Other Track")
        result = client.match_track_to_release(release, "Hello World")
        assert result is not None
        assert result.title == "Hello World"

    def test_substring_match(self, client):
        release = self._release_with("Hello World (Live)", "Other")
        result = client.match_track_to_release(release, "Hello World")
        assert result is not None

    def test_below_threshold_returns_none(self, client):
        release = self._release_with("Completely Different Song Title")
        result = client.match_track_to_release(release, "ABCDEF")
        assert result is None

    def test_strips_track_number_prefix(self, client):
        release = self._release_with("Hello World")
        result = client.match_track_to_release(release, "01. Hello World")
        assert result is not None

    def test_returns_none_on_empty_tracklist(self, client):
        release = DiscogsRelease(
            release_id=1, title="A", artists=["A"],
            year=2020, tracklist=[], total_discs=1,
        )
        result = client.match_track_to_release(release, "Any Song")
        assert result is None
