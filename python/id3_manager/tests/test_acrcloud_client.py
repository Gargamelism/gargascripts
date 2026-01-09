"""Tests for acrcloud_client.py response parsing."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from acrcloud_client import ACRCloudClient


@pytest.fixture
def client():
    """Create an ACRCloudClient instance (credentials not needed for parsing tests)."""
    return ACRCloudClient("fake.host.com", "fake_key", "fake_secret")


class TestParseResponse:
    """Tests for _parse_response method."""

    def test_parses_successful_response(self, client):
        """Should parse a successful ACRCloud response."""
        response = {
            "status": {"code": 0, "msg": "Success"},
            "metadata": {
                "music": [
                    {
                        "title": "Test Song",
                        "artists": [{"name": "Test Artist"}],
                        "album": {"name": "Test Album"},
                        "release_date": "2020-01-15",
                        "label": "Test Label",
                        "score": 95
                    }
                ]
            }
        }
        result = client._parse_response(response)
        assert result is not None
        assert result.title == "Test Song"
        assert result.artists == ["Test Artist"]
        assert result.album == "Test Album"
        assert result.release_date == "2020-01-15"
        assert result.label == "Test Label"
        assert result.confidence == 0.95

    def test_parses_multiple_artists(self, client):
        """Should parse response with multiple artists."""
        response = {
            "status": {"code": 0, "msg": "Success"},
            "metadata": {
                "music": [
                    {
                        "title": "Collaboration Song",
                        "artists": [
                            {"name": "Artist One"},
                            {"name": "Artist Two"},
                            {"name": "Artist Three"}
                        ],
                        "album": {"name": "Collab Album"},
                        "score": 80
                    }
                ]
            }
        }
        result = client._parse_response(response)
        assert result is not None
        assert result.artists == ["Artist One", "Artist Two", "Artist Three"]

    def test_returns_none_for_no_match(self, client):
        """Should return None when status code indicates no match."""
        response = {
            "status": {"code": 1001, "msg": "No result"},
            "metadata": {}
        }
        result = client._parse_response(response)
        assert result is None

    def test_returns_none_for_empty_music_list(self, client):
        """Should return None when music list is empty."""
        response = {
            "status": {"code": 0, "msg": "Success"},
            "metadata": {"music": []}
        }
        result = client._parse_response(response)
        assert result is None

    def test_returns_none_for_missing_metadata(self, client):
        """Should return None when metadata is missing."""
        response = {
            "status": {"code": 0, "msg": "Success"}
        }
        result = client._parse_response(response)
        assert result is None

    def test_handles_missing_optional_fields(self, client):
        """Should handle missing optional fields gracefully."""
        response = {
            "status": {"code": 0, "msg": "Success"},
            "metadata": {
                "music": [
                    {
                        "title": "Simple Song",
                        "artists": [],
                        "score": 70
                    }
                ]
            }
        }
        result = client._parse_response(response)
        assert result is not None
        assert result.title == "Simple Song"
        assert result.artists == []
        assert result.album is None
        assert result.release_date is None
        assert result.label is None
        assert result.confidence == 0.70

    def test_uses_first_match_only(self, client):
        """Should use only the first match from multiple results."""
        response = {
            "status": {"code": 0, "msg": "Success"},
            "metadata": {
                "music": [
                    {
                        "title": "First Match",
                        "artists": [{"name": "First Artist"}],
                        "score": 90
                    },
                    {
                        "title": "Second Match",
                        "artists": [{"name": "Second Artist"}],
                        "score": 85
                    }
                ]
            }
        }
        result = client._parse_response(response)
        assert result is not None
        assert result.title == "First Match"
        assert result.artists == ["First Artist"]

    def test_handles_zero_score(self, client):
        """Should handle zero score correctly."""
        response = {
            "status": {"code": 0, "msg": "Success"},
            "metadata": {
                "music": [
                    {
                        "title": "Low Confidence Match",
                        "artists": [{"name": "Unknown"}],
                        "score": 0
                    }
                ]
            }
        }
        result = client._parse_response(response)
        assert result is not None
        assert result.confidence == 0.0

    def test_handles_missing_score(self, client):
        """Should default to 0 confidence when score is missing."""
        response = {
            "status": {"code": 0, "msg": "Success"},
            "metadata": {
                "music": [
                    {
                        "title": "No Score Song",
                        "artists": [{"name": "Artist"}]
                    }
                ]
            }
        }
        result = client._parse_response(response)
        assert result is not None
        assert result.confidence == 0.0

    def test_handles_error_status(self, client):
        """Should return None for error status codes."""
        error_codes = [2000, 2001, 3000, 3001, 3003, 3014, 3015]
        for code in error_codes:
            response = {
                "status": {"code": code, "msg": "Error"},
                "metadata": {}
            }
            result = client._parse_response(response)
            assert result is None, f"Expected None for error code {code}"


class TestClientInitialization:
    """Tests for ACRCloudClient initialization."""

    def test_stores_credentials(self):
        """Should store provided credentials."""
        client = ACRCloudClient("test.host", "test_key", "test_secret")
        assert client.host == "test.host"
        assert client.access_key == "test_key"
        assert client.access_secret == "test_secret"

    def test_default_timeout(self):
        """Should have default timeout of 15 seconds."""
        client = ACRCloudClient("test.host", "test_key", "test_secret")
        assert client.timeout == 15
