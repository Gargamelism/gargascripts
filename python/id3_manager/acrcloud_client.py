"""ACRCloud audio fingerprinting client."""

import base64
import hashlib
import hmac
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import requests
from pedalboard.io import AudioFile

from config import eprint
from models import ACRCloudResult


class ACRCloudClient:
    """Client for ACRCloud audio fingerprinting service."""

    def __init__(self, host: str, access_key: str, access_secret: str):
        """
        Initialize ACRCloud client.

        Args:
            host: ACRCloud API host
            access_key: ACRCloud access key
            access_secret: ACRCloud access secret
        """
        self.host = host
        self.access_key = access_key
        self.access_secret = access_secret
        self.timeout = 15

    def _extract_audio_segment(self, audio_path: str, start_sec: float,
                               duration_sec: float) -> Tuple[np.ndarray, int]:
        """
        Extract a segment from an audio file.

        Args:
            audio_path: Path to audio file
            start_sec: Start position in seconds
            duration_sec: Duration to extract in seconds

        Returns:
            (audio_data, sample_rate) tuple
        """
        with AudioFile(audio_path) as f:
            sample_rate = f.samplerate
            start_frame = int(start_sec * sample_rate)
            num_frames = int(duration_sec * sample_rate)

            # Seek to start position
            f.seek(start_frame)

            # Read the segment
            audio_data = f.read(num_frames)

        return audio_data, sample_rate

    def _export_to_mp3(self, audio_data: np.ndarray, sample_rate: int,
                       output_path: str) -> None:
        """
        Export audio data to MP3 file.

        Args:
            audio_data: NumPy array of audio samples
            sample_rate: Sample rate in Hz
            output_path: Output file path
        """
        num_channels = audio_data.shape[0] if audio_data.ndim > 1 else 1
        with AudioFile(output_path, "w", samplerate=sample_rate,
                       num_channels=num_channels, quality=128) as f:
            f.write(audio_data)

    def recognize(self, audio_path: str,
                  duration_seconds: int = 15) -> Optional[ACRCloudResult]:
        """
        Recognize audio file using ACRCloud.

        Extracts a segment from the middle of the audio for better accuracy.

        Args:
            audio_path: Path to audio file
            duration_seconds: Duration of segment to analyze

        Returns:
            ACRCloudResult if match found, None otherwise
        """
        try:
            with AudioFile(audio_path) as f:
                duration_sec = f.duration
        except Exception as e:
            eprint(f"Error loading audio file {audio_path}: {e}")
            return None

        # Calculate middle segment position
        middle_start_sec = max(0, (duration_sec / 2) - (duration_seconds / 2))

        # Ensure we have at least 5 seconds
        if duration_sec < 5:
            middle_start_sec = 0

        # Extract segment
        audio_data, sr = self._extract_audio_segment(
            audio_path, middle_start_sec, duration_seconds
        )

        # Create temporary file for API
        snippet_path = Path(audio_path).with_suffix(".acr_snippet.mp3")
        try:
            self._export_to_mp3(audio_data, sr, str(snippet_path))
            result = self._call_api(str(snippet_path))
            return self._parse_response(result)
        except Exception as e:
            eprint(f"ACRCloud recognition error: {e}")
            return None
        finally:
            if snippet_path.exists():
                snippet_path.unlink()

    def _call_api(self, file_path: str) -> dict:
        """
        Call ACRCloud API with audio file.

        Args:
            file_path: Path to audio file to identify

        Returns:
            API response as dictionary
        """
        http_method = "POST"
        http_uri = "/v1/identify"
        data_type = "audio"
        signature_version = "1"
        timestamp = str(int(time.time()))

        string_to_sign = "\n".join([
            http_method, http_uri, self.access_key,
            data_type, signature_version, timestamp
        ])

        sign = base64.b64encode(
            hmac.new(
                self.access_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha1
            ).digest()
        ).decode("utf-8")

        with open(file_path, "rb") as f:
            files = {
                "sample": f,
                "access_key": (None, self.access_key),
                "data_type": (None, data_type),
                "signature_version": (None, signature_version),
                "signature": (None, sign),
                "timestamp": (None, timestamp),
            }
            resp = requests.post(
                f"https://{self.host}/v1/identify",
                files=files,
                timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()

    def _parse_response(self, data: dict) -> Optional[ACRCloudResult]:
        """
        Parse ACRCloud response into structured result.

        Args:
            data: API response dictionary

        Returns:
            ACRCloudResult if match found, None otherwise
        """
        status = data.get("status", {})
        if status.get("code") != 0:
            # No match or error
            return None

        music = data.get("metadata", {}).get("music", [])
        if not music:
            return None

        best_match = music[0]

        return ACRCloudResult(
            title=best_match.get("title", ""),
            artists=[a["name"] for a in best_match.get("artists", [])],
            album=best_match.get("album", {}).get("name"),
            release_date=best_match.get("release_date"),
            label=best_match.get("label"),
            confidence=best_match.get("score", 0) / 100
        )

    def recognize_with_retry(self, audio_path: str,
                             max_retries: int = 2) -> Optional[ACRCloudResult]:
        """
        Recognize audio with retry logic for transient failures.

        Args:
            audio_path: Path to audio file
            max_retries: Maximum number of retries

        Returns:
            ACRCloudResult if match found, None otherwise
        """
        for attempt in range(max_retries + 1):
            try:
                result = self.recognize(audio_path)
                if result:
                    return result

                # If no match, try different segment positions
                if attempt < max_retries:
                    eprint(f"No match, trying different segment (attempt {attempt + 2})...")
                    result = self._recognize_alternate_segment(
                        audio_path, attempt + 1
                    )
                    if result:
                        return result

            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    eprint(f"Request timeout, retrying ({attempt + 2}/{max_retries + 1})...")
                    time.sleep(2)
                else:
                    eprint("ACRCloud request timed out after retries")

            except requests.exceptions.RequestException as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    eprint("Rate limit hit, waiting 60 seconds...")
                    time.sleep(60)
                elif attempt < max_retries:
                    eprint(f"Request error, retrying: {e}")
                    time.sleep(2)
                else:
                    raise

        return None

    def _recognize_alternate_segment(self, audio_path: str,
                                     attempt: int) -> Optional[ACRCloudResult]:
        """
        Try recognizing with a different segment of the audio.

        Args:
            audio_path: Path to audio file
            attempt: Attempt number (affects segment position)

        Returns:
            ACRCloudResult if match found, None otherwise
        """
        try:
            with AudioFile(audio_path) as f:
                duration_sec = f.duration
        except Exception:
            return None

        duration_extract = 15  # seconds

        # Try different positions based on attempt
        positions_sec = [
            0,                      # Start
            duration_sec / 4,       # 25%
            duration_sec * 3 / 4,   # 75%
        ]

        if attempt < len(positions_sec):
            start_sec = positions_sec[attempt]

            audio_data, sr = self._extract_audio_segment(
                audio_path, start_sec, duration_extract
            )

            snippet_path = Path(audio_path).with_suffix(f".acr_alt_{attempt}.mp3")

            try:
                self._export_to_mp3(audio_data, sr, str(snippet_path))
                result = self._call_api(str(snippet_path))
                return self._parse_response(result)
            except Exception:
                return None
            finally:
                if snippet_path.exists():
                    snippet_path.unlink()

        return None
