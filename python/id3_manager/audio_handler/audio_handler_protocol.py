from typing import Protocol

class AudioHandler(Protocol):
    def extract_audio_segment(self, audio_path: str, start_sec: float, duration_sec: float):
        """Extract a segment from an audio file."""
        ...

    def export_audio_segment(self, audio_data, sample_rate: int, output_path: str):
        """Export an audio segment to a file."""
        ...

    def get_audio_duration(self, audio_path: str) -> float:
        """Get the duration of an audio file in seconds."""
        ...