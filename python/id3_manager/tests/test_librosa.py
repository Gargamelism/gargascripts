"""Tests for audio_handler/librosa.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_handler.librosa import LibrosaHandler


@pytest.fixture
def handler():
    return LibrosaHandler()


class TestExtractAudioSegment:
    def test_returns_audio_data_and_sample_rate(self, handler):
        audio_data = np.zeros((44100, 2), dtype=np.float32)
        with patch("librosa.load", return_value=(audio_data, 44100)):
            data, sr = handler.extract_audio_segment("song.m4a", 0.0, 1.0)
        assert sr == 44100
        assert data is audio_data

    def test_passes_offset_and_duration(self, handler):
        audio_data = np.zeros((22050,), dtype=np.float32)
        with patch("librosa.load", return_value=(audio_data, 22050)) as mock_load:
            handler.extract_audio_segment("song.m4a", 5.0, 2.0)
        mock_load.assert_called_once_with("song.m4a", sr=None, offset=5.0, duration=2.0)

    def test_preserves_native_sample_rate(self, handler):
        audio_data = np.zeros((48000,), dtype=np.float32)
        with patch("librosa.load", return_value=(audio_data, 48000)) as mock_load:
            _, sr = handler.extract_audio_segment("song.m4a", 0.0, 1.0)
        assert mock_load.call_args[1]["sr"] is None
        assert sr == 48000


class TestExportAudioSegment:
    def _make_mock_sf(self):
        mock_file = MagicMock()
        mock_file.__enter__ = lambda s: s
        mock_file.__exit__ = MagicMock(return_value=False)
        return mock_file

    def test_writes_stereo_audio(self, handler):
        mock_file = self._make_mock_sf()
        audio_data = np.zeros((1024, 2), dtype=np.float32)

        with patch("soundfile.SoundFile", return_value=mock_file) as MockSF:
            handler.export_audio_segment(audio_data, 44100, "out.wav")

        MockSF.assert_called_once_with(
            "out.wav", "w", samplerate=44100, channels=2, subtype="PCM_16"
        )
        mock_file.write.assert_called_once_with(audio_data)

    def test_writes_mono_audio(self, handler):
        mock_file = self._make_mock_sf()
        audio_data = np.zeros((1024,), dtype=np.float32)

        with patch("soundfile.SoundFile", return_value=mock_file) as MockSF:
            handler.export_audio_segment(audio_data, 22050, "out.wav")

        MockSF.assert_called_once_with(
            "out.wav", "w", samplerate=22050, channels=1, subtype="PCM_16"
        )

    def test_uses_pcm16_subtype(self, handler):
        mock_file = self._make_mock_sf()
        audio_data = np.zeros((512, 2), dtype=np.float32)

        with patch("soundfile.SoundFile", return_value=mock_file) as MockSF:
            handler.export_audio_segment(audio_data, 44100, "out.wav")

        _, kwargs = MockSF.call_args
        assert kwargs["subtype"] == "PCM_16"


class TestGetAudioDuration:
    def test_returns_duration(self, handler):
        with patch("librosa.get_duration", return_value=3.5):
            duration = handler.get_audio_duration("song.m4a")
        assert duration == pytest.approx(3.5)

    def test_passes_path_kwarg(self, handler):
        with patch("librosa.get_duration", return_value=1.0) as mock_dur:
            handler.get_audio_duration("/path/to/track.m4a")
        mock_dur.assert_called_once_with(path="/path/to/track.m4a")
