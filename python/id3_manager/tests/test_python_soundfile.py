"""Tests for audio_handler/python_soundfile.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from audio_handler.python_soundfile import PythonSoundFileHandler


@pytest.fixture
def handler():
    return PythonSoundFileHandler()


def make_mock_sf(frames=44100, samplerate=44100, channels=2):
    mock_file = MagicMock()
    mock_file.samplerate = samplerate
    mock_file.frames = frames
    mock_file.__enter__ = lambda s: s
    mock_file.__exit__ = MagicMock(return_value=False)
    audio_data = np.zeros((int(frames), channels), dtype=np.float32)
    mock_file.read.return_value = audio_data
    return mock_file


class TestExtractAudioSegment:
    def test_returns_audio_data_and_sample_rate(self, handler):
        mock_file = make_mock_sf(samplerate=44100)
        with patch("soundfile.SoundFile", return_value=mock_file):
            data, sr = handler.extract_audio_segment("song.flac", 0.0, 1.0)
        assert sr == 44100
        assert data is mock_file.read.return_value

    def test_seeks_to_correct_start_frame(self, handler):
        mock_file = make_mock_sf(samplerate=44100)
        with patch("soundfile.SoundFile", return_value=mock_file):
            handler.extract_audio_segment("song.flac", 5.0, 1.0)
        mock_file.seek.assert_called_once_with(5 * 44100)

    def test_reads_correct_number_of_frames(self, handler):
        mock_file = make_mock_sf(samplerate=22050)
        with patch("soundfile.SoundFile", return_value=mock_file):
            handler.extract_audio_segment("song.flac", 0.0, 2.0)
        mock_file.read.assert_called_once_with(2 * 22050)

    def test_fractional_start_truncated_to_int(self, handler):
        mock_file = make_mock_sf(samplerate=44100)
        with patch("soundfile.SoundFile", return_value=mock_file):
            handler.extract_audio_segment("song.flac", 0.1, 1.0)
        mock_file.seek.assert_called_once_with(int(0.1 * 44100))


class TestExportAudioSegment:
    def test_writes_stereo_audio(self, handler):
        mock_file = MagicMock()
        mock_file.__enter__ = lambda s: s
        mock_file.__exit__ = MagicMock(return_value=False)
        audio_data = np.zeros((1024, 2), dtype=np.float32)

        with patch("soundfile.SoundFile", return_value=mock_file) as MockSF:
            handler.export_audio_segment(audio_data, 44100, "out.wav")

        MockSF.assert_called_once_with(
            "out.wav", "w", samplerate=44100, channels=2, subtype="PCM_16"
        )
        mock_file.write.assert_called_once_with(audio_data)

    def test_writes_mono_audio(self, handler):
        mock_file = MagicMock()
        mock_file.__enter__ = lambda s: s
        mock_file.__exit__ = MagicMock(return_value=False)
        audio_data = np.zeros((1024,), dtype=np.float32)

        with patch("soundfile.SoundFile", return_value=mock_file) as MockSF:
            handler.export_audio_segment(audio_data, 22050, "out.wav")

        MockSF.assert_called_once_with(
            "out.wav", "w", samplerate=22050, channels=1, subtype="PCM_16"
        )

    def test_uses_pcm16_subtype(self, handler):
        mock_file = MagicMock()
        mock_file.__enter__ = lambda s: s
        mock_file.__exit__ = MagicMock(return_value=False)
        audio_data = np.zeros((512, 2), dtype=np.float32)

        with patch("soundfile.SoundFile", return_value=mock_file) as MockSF:
            handler.export_audio_segment(audio_data, 44100, "out.wav")

        _, kwargs = MockSF.call_args
        assert kwargs["subtype"] == "PCM_16"


class TestGetAudioDuration:
    def test_returns_correct_duration(self, handler):
        mock_file = make_mock_sf(frames=88200, samplerate=44100)
        with patch("soundfile.SoundFile", return_value=mock_file):
            duration = handler.get_audio_duration("song.flac")
        assert duration == pytest.approx(2.0)

    def test_fractional_duration(self, handler):
        mock_file = make_mock_sf(frames=11025, samplerate=44100)
        with patch("soundfile.SoundFile", return_value=mock_file):
            duration = handler.get_audio_duration("song.flac")
        assert duration == pytest.approx(0.25)

    def test_opens_correct_file(self, handler):
        mock_file = make_mock_sf()
        with patch("soundfile.SoundFile", return_value=mock_file) as MockSF:
            handler.get_audio_duration("/path/to/track.flac")
        MockSF.assert_called_once_with("/path/to/track.flac")
