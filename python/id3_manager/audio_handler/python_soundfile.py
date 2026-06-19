import soundfile


class PythonSoundFileHandler:
    def extract_audio_segment(self, audio_path: str, start_sec: float, duration_sec: float):
        with soundfile.SoundFile(audio_path) as f:
            sample_rate = f.samplerate
            start_frame = int(start_sec * sample_rate)
            num_frames = int(duration_sec * sample_rate)

            # Seek to start position
            f.seek(start_frame)

            # Read the segment
            audio_data = f.read(num_frames)

        return audio_data, sample_rate

    def export_audio_segment(self, audio_data, sample_rate: int, output_path: str):
        """Export an audio segment to a file."""
        num_channels = audio_data.shape[1] if len(audio_data.shape) > 1 else 1
        with soundfile.SoundFile(
            output_path, "w", samplerate=sample_rate, channels=num_channels, subtype="PCM_16"
        ) as f:
            f.write(audio_data)

    def get_audio_duration(self, audio_path: str) -> float:
        with soundfile.SoundFile(audio_path) as f:
            return f.frames / f.samplerate