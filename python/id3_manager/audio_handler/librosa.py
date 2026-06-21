from audio_handler.audio_handler_protocol import AudioHandler
import librosa
import soundfile

from typing import TYPE_CHECKING


class LibrosaHandler:
    def extract_audio_segment(self, audio_path: str, start_sec: float, duration_sec: float):
        audio_data, sample_rate = librosa.load(audio_path, sr=None, offset=start_sec, duration=duration_sec)

        return audio_data, sample_rate

    def export_audio_segment(self, audio_data, sample_rate: int, output_path: str):
        """Export an audio segment to a file."""
        num_channels = audio_data.shape[1] if len(audio_data.shape) > 1 else 1
        with soundfile.SoundFile(
            output_path, "w", samplerate=sample_rate, channels=num_channels, subtype="PCM_16"
        ) as f:
            f.write(audio_data)
        

    def get_audio_duration(self, audio_path: str) -> float:
        return librosa.get_duration(path=audio_path)


if TYPE_CHECKING:
    _: AudioHandler = LibrosaHandler()
