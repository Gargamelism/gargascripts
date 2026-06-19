"""Additional coverage tests for acrcloud_client.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from acrcloud_client import ACRCloudClient


@pytest.fixture
def client():
    mock_handler = MagicMock()
    mock_handler.get_audio_duration.return_value = 120.0
    mock_handler.extract_audio_segment.return_value = (np.zeros((2, 1000)), 44100)
    return ACRCloudClient("fake.host.com", "fake_key", "fake_secret", mock_handler)


class TestRecognize:
    def test_returns_result_on_success(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch.object(
            client,
            "_call_api",
            return_value={
                "status": {"code": 0},
                "metadata": {"music": [{"title": "T", "artists": [], "score": 80}]},
            },
        ):
            result = client.recognize(str(f))
        assert result is not None
        assert result.title == "T"

    def test_cleans_up_snippet_file(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        created_paths = []

        def fake_export(audio_data, sr, path):
            Path(path).touch()
            created_paths.append(Path(path))

        client._audio_handler.export_audio_segment.side_effect = fake_export
        with patch.object(
            client, "_call_api", return_value={"status": {"code": 1001}, "metadata": {}}
        ):
            client.recognize(str(f))

        assert created_paths
        assert not created_paths[0].exists()

    def test_returns_none_on_audio_load_error(self, client, tmp_path, capsys):
        f = tmp_path / "song.mp3"
        f.touch()
        client._audio_handler.get_audio_duration.side_effect = Exception("bad file")
        result = client.recognize(str(f))
        assert result is None

    def test_returns_none_on_api_exception(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch.object(client, "_call_api", side_effect=Exception("network error")):
            result = client.recognize(str(f))
        assert result is None

    def test_uses_start_from_beginning_for_short_audio(self, client, tmp_path):
        f = tmp_path / "short.mp3"
        f.touch()
        client._audio_handler.get_audio_duration.return_value = 3.0  # < 5s
        with patch.object(
            client, "_call_api", return_value={"status": {"code": 1001}, "metadata": {}}
        ):
            client.recognize(str(f))
        start_arg = client._audio_handler.extract_audio_segment.call_args[0][1]
        assert start_arg == 0


class TestCallApi:
    def test_posts_to_correct_url(self, client, tmp_path):
        f = tmp_path / "clip.mp3"
        f.write_bytes(b"fake mp3")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": {"code": 0}, "metadata": {}}

        with (
            patch("acrcloud_client.requests.post", return_value=mock_resp) as mock_post,
            patch("acrcloud_client.time.time", return_value=1234567890),
        ):
            client._call_api(str(f))

        (url,) = mock_post.call_args[0]
        assert "fake.host.com" in url
        assert "/v1/identify" in url

    def test_raises_for_http_error(self, client, tmp_path):
        f = tmp_path / "clip.mp3"
        f.write_bytes(b"data")

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("403")

        with (
            patch("acrcloud_client.requests.post", return_value=mock_resp),
            patch("acrcloud_client.time.time", return_value=1000),
        ):
            with pytest.raises(requests.HTTPError):
                client._call_api(str(f))


class TestRecognizeWithRetry:
    def test_returns_result_on_first_attempt(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        mock_result = MagicMock()
        with patch.object(client, "recognize", return_value=mock_result):
            result = client.recognize_with_retry(str(f))
        assert result is mock_result

    def test_tries_alternate_on_no_match(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        alt_result = MagicMock()
        with (
            patch.object(client, "recognize", return_value=None),
            patch.object(
                client, "_recognize_alternate_segment", return_value=alt_result
            ),
        ):
            result = client.recognize_with_retry(str(f), max_retries=1)
        assert result is alt_result

    def test_retries_on_timeout(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        good_result = MagicMock()
        call_count = [0]

        def flaky_recognize(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise requests.exceptions.Timeout()
            return good_result

        with (
            patch.object(client, "recognize", side_effect=flaky_recognize),
            patch("acrcloud_client.time.sleep"),
        ):
            result = client.recognize_with_retry(str(f), max_retries=2)
        assert result is good_result

    def test_sleeps_60s_on_rate_limit(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        good_result = MagicMock()
        call_count = [0]

        def rate_limited(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise requests.exceptions.RequestException("429 Too Many Requests")
            return good_result

        with (
            patch.object(client, "recognize", side_effect=rate_limited),
            patch("acrcloud_client.time.sleep") as mock_sleep,
        ):
            client.recognize_with_retry(str(f), max_retries=2)
        mock_sleep.assert_called_with(60)

    def test_returns_none_after_all_retries_exhausted(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with (
            patch.object(client, "recognize", return_value=None),
            patch.object(client, "_recognize_alternate_segment", return_value=None),
        ):
            result = client.recognize_with_retry(str(f), max_retries=1)
        assert result is None

    def test_raises_on_final_request_exception(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with (
            patch.object(
                client,
                "recognize",
                side_effect=requests.exceptions.RequestException("network down"),
            ),
            patch("acrcloud_client.time.sleep"),
        ):
            with pytest.raises(requests.exceptions.RequestException):
                client.recognize_with_retry(str(f), max_retries=0)


class TestRecognizeAlternateSegment:
    def test_returns_result_for_valid_attempt(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch.object(
            client,
            "_call_api",
            return_value={
                "status": {"code": 0},
                "metadata": {"music": [{"title": "T", "artists": [], "score": 90}]},
            },
        ):
            result = client._recognize_alternate_segment(str(f), attempt=0)
        assert result is not None

    def test_returns_none_beyond_positions(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        result = client._recognize_alternate_segment(str(f), attempt=99)
        assert result is None

    def test_returns_none_on_audio_load_error(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        client._audio_handler.get_audio_duration.side_effect = Exception("bad")
        result = client._recognize_alternate_segment(str(f), attempt=0)
        assert result is None

    def test_cleans_up_alt_snippet(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        created_paths = []

        def fake_export(audio_data, sr, path):
            Path(path).touch()
            created_paths.append(Path(path))

        client._audio_handler.export_audio_segment.side_effect = fake_export
        with patch.object(
            client, "_call_api", return_value={"status": {"code": 1001}, "metadata": {}}
        ):
            client._recognize_alternate_segment(str(f), attempt=0)

        assert created_paths
        assert not created_paths[0].exists()
