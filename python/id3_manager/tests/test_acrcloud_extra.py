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
    return ACRCloudClient("fake.host.com", "fake_key", "fake_secret")


def _mock_audio_file_ctx(duration=120.0, samplerate=44100):
    """Return a context manager mock that simulates pedalboard AudioFile."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.duration = duration
    cm.samplerate = samplerate
    cm.read = MagicMock(return_value=np.zeros((2, samplerate * 15)))
    cm.seek = MagicMock()
    return cm


class TestExtractAudioSegment:
    def test_calls_seek_and_read(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        mock_af = _mock_audio_file_ctx(duration=60.0, samplerate=44100)
        with patch("acrcloud_client.AudioFile", return_value=mock_af):
            audio_data, sr = client._extract_audio_segment(str(f), 10.0, 15.0)
        mock_af.seek.assert_called_once_with(int(10.0 * 44100))
        mock_af.read.assert_called_once_with(int(15.0 * 44100))
        assert sr == 44100

    def test_returns_correct_samplerate(self, client, tmp_path):
        f = tmp_path / "song.flac"
        f.touch()
        mock_af = _mock_audio_file_ctx(samplerate=48000)
        with patch("acrcloud_client.AudioFile", return_value=mock_af):
            _, sr = client._extract_audio_segment(str(f), 0.0, 5.0)
        assert sr == 48000


class TestExportToMp3:
    def test_writes_mono_audio(self, client, tmp_path):
        out = tmp_path / "out.mp3"
        audio = np.zeros(44100)  # 1D = mono
        write_cm = MagicMock()
        write_cm.__enter__ = MagicMock(return_value=write_cm)
        write_cm.__exit__ = MagicMock(return_value=False)
        with patch("acrcloud_client.AudioFile", return_value=write_cm):
            client._export_to_mp3(audio, 44100, str(out))
        write_cm.write.assert_called_once_with(audio)

    def test_writes_stereo_audio(self, client, tmp_path):
        out = tmp_path / "out.mp3"
        audio = np.zeros((2, 44100))  # 2D = stereo
        write_cm = MagicMock()
        write_cm.__enter__ = MagicMock(return_value=write_cm)
        write_cm.__exit__ = MagicMock(return_value=False)
        with patch("acrcloud_client.AudioFile", return_value=write_cm) as af_cls:
            client._export_to_mp3(audio, 44100, str(out))
        # num_channels should be 2 (shape[0])
        _, kwargs = af_cls.call_args
        assert kwargs.get("num_channels") == 2 or af_cls.call_args[0][3] == 2


class TestRecognize:
    def _mock_setup(self, client, tmp_path, duration=120.0):
        """Wire up all three AudioFile calls (duration probe + extract + export)."""
        probe_cm = _mock_audio_file_ctx(duration=duration)
        extract_cm = _mock_audio_file_ctx(duration=duration)
        write_cm = MagicMock()
        write_cm.__enter__ = MagicMock(return_value=write_cm)
        write_cm.__exit__ = MagicMock(return_value=False)
        return probe_cm, extract_cm, write_cm

    def test_returns_result_on_success(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()

        mock_result = MagicMock()
        with patch.object(client, "_extract_audio_segment",
                          return_value=(np.zeros((2, 1000)), 44100)), \
             patch.object(client, "_export_to_mp3"), \
             patch.object(client, "_call_api", return_value={"status": {"code": 0},
                                                              "metadata": {"music": [{"title": "T", "artists": [], "score": 80}]}}), \
             patch("acrcloud_client.AudioFile") as af_cls:
            af_inst = _mock_audio_file_ctx(duration=120.0)
            af_cls.return_value = af_inst
            result = client.recognize(str(f))
        assert result is not None
        assert result.title == "T"

    def test_cleans_up_snippet_file(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()

        snippet = f.with_suffix(".acr_snippet.mp3")

        def fake_export(audio_data, sr, path):
            Path(path).touch()  # create the snippet

        with patch.object(client, "_extract_audio_segment",
                          return_value=(np.zeros((2, 1000)), 44100)), \
             patch.object(client, "_export_to_mp3", side_effect=fake_export), \
             patch.object(client, "_call_api", return_value={"status": {"code": 1001}, "metadata": {}}), \
             patch("acrcloud_client.AudioFile") as af_cls:
            af_cls.return_value = _mock_audio_file_ctx(duration=60.0)
            client.recognize(str(f))

        assert not snippet.exists()

    def test_returns_none_on_audio_load_error(self, client, tmp_path, capsys):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("acrcloud_client.AudioFile", side_effect=Exception("bad file")):
            result = client.recognize(str(f))
        assert result is None

    def test_returns_none_on_api_exception(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch.object(client, "_extract_audio_segment",
                          return_value=(np.zeros((2, 1000)), 44100)), \
             patch.object(client, "_export_to_mp3"), \
             patch.object(client, "_call_api", side_effect=Exception("network error")), \
             patch("acrcloud_client.AudioFile") as af_cls:
            af_cls.return_value = _mock_audio_file_ctx(duration=120.0)
            result = client.recognize(str(f))
        assert result is None

    def test_uses_start_from_beginning_for_short_audio(self, client, tmp_path):
        f = tmp_path / "short.mp3"
        f.touch()
        calls = []

        def fake_extract(path, start, duration):
            calls.append(start)
            return np.zeros((2, 1000)), 44100

        with patch.object(client, "_extract_audio_segment", side_effect=fake_extract), \
             patch.object(client, "_export_to_mp3"), \
             patch.object(client, "_call_api", return_value={"status": {"code": 1001}, "metadata": {}}), \
             patch("acrcloud_client.AudioFile") as af_cls:
            af_cls.return_value = _mock_audio_file_ctx(duration=3.0)  # < 5s
            client.recognize(str(f))
        assert calls[0] == 0


class TestCallApi:
    def test_posts_to_correct_url(self, client, tmp_path):
        f = tmp_path / "clip.mp3"
        f.write_bytes(b"fake mp3")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": {"code": 0}, "metadata": {}}

        with patch("acrcloud_client.requests.post", return_value=mock_resp) as mock_post, \
             patch("acrcloud_client.time.time", return_value=1234567890):
            client._call_api(str(f))

        url, = mock_post.call_args[0]
        assert "fake.host.com" in url
        assert "/v1/identify" in url

    def test_raises_for_http_error(self, client, tmp_path):
        f = tmp_path / "clip.mp3"
        f.write_bytes(b"data")

        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("403")

        with patch("acrcloud_client.requests.post", return_value=mock_resp), \
             patch("acrcloud_client.time.time", return_value=1000):
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
        with patch.object(client, "recognize", return_value=None), \
             patch.object(client, "_recognize_alternate_segment", return_value=alt_result):
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

        with patch.object(client, "recognize", side_effect=flaky_recognize), \
             patch("acrcloud_client.time.sleep"):
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

        with patch.object(client, "recognize", side_effect=rate_limited), \
             patch("acrcloud_client.time.sleep") as mock_sleep:
            client.recognize_with_retry(str(f), max_retries=2)
        mock_sleep.assert_called_with(60)

    def test_returns_none_after_all_retries_exhausted(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch.object(client, "recognize", return_value=None), \
             patch.object(client, "_recognize_alternate_segment", return_value=None):
            result = client.recognize_with_retry(str(f), max_retries=1)
        assert result is None

    def test_raises_on_final_request_exception(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch.object(client, "recognize",
                          side_effect=requests.exceptions.RequestException("network down")), \
             patch("acrcloud_client.time.sleep"):
            with pytest.raises(requests.exceptions.RequestException):
                client.recognize_with_retry(str(f), max_retries=0)


class TestRecognizeAlternateSegment:
    def test_returns_result_for_valid_attempt(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        mock_result = MagicMock()
        with patch.object(client, "_extract_audio_segment",
                          return_value=(np.zeros((2, 1000)), 44100)), \
             patch.object(client, "_export_to_mp3"), \
             patch.object(client, "_call_api", return_value={"status": {"code": 0},
                                                              "metadata": {"music": [{"title": "T", "artists": [], "score": 90}]}}), \
             patch("acrcloud_client.AudioFile") as af_cls:
            af_cls.return_value = _mock_audio_file_ctx(duration=120.0)
            result = client._recognize_alternate_segment(str(f), attempt=0)
        assert result is not None

    def test_returns_none_beyond_positions(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("acrcloud_client.AudioFile") as af_cls:
            af_cls.return_value = _mock_audio_file_ctx(duration=120.0)
            result = client._recognize_alternate_segment(str(f), attempt=99)
        assert result is None

    def test_returns_none_on_audio_load_error(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("acrcloud_client.AudioFile", side_effect=Exception("bad")):
            result = client._recognize_alternate_segment(str(f), attempt=0)
        assert result is None

    def test_cleans_up_alt_snippet(self, client, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        alt_snippet = f.with_suffix(".acr_alt_0.mp3")

        def fake_export(audio_data, sr, path):
            Path(path).touch()

        with patch.object(client, "_extract_audio_segment",
                          return_value=(np.zeros((2, 1000)), 44100)), \
             patch.object(client, "_export_to_mp3", side_effect=fake_export), \
             patch.object(client, "_call_api", return_value={"status": {"code": 1001}, "metadata": {}}), \
             patch("acrcloud_client.AudioFile") as af_cls:
            af_cls.return_value = _mock_audio_file_ctx(duration=120.0)
            client._recognize_alternate_segment(str(f), attempt=0)

        assert not alt_snippet.exists()
