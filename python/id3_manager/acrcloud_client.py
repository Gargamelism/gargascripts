"""ACRCloud audio fingerprinting client."""

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional

import requests
from pydub import AudioSegment

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
            audio = AudioSegment.from_file(audio_path)
        except Exception as e:
            eprint(f"Error loading audio file {audio_path}: {e}")
            return None

        audio_len_ms = len(audio)

        # Use middle section for better recognition
        middle_start = max(0, (audio_len_ms // 2) - (duration_seconds * 500))
        end_pos = min(audio_len_ms, middle_start + (duration_seconds * 1000))

        # Ensure we have at least 5 seconds
        if end_pos - middle_start < 5000:
            middle_start = 0
            end_pos = min(audio_len_ms, duration_seconds * 1000)

        snippet = audio[middle_start:end_pos]

        # Create temporary file for API
        snippet_path = Path(audio_path).with_suffix(".acr_snippet.mp3")
        try:
            snippet.export(str(snippet_path), format="mp3")
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
            audio = AudioSegment.from_file(audio_path)
        except Exception:
            return None

        audio_len_ms = len(audio)
        duration_ms = 15000  # 15 seconds

        # Try different positions based on attempt
        positions = [
            0,  # Start
            audio_len_ms // 4,  # 25%
            audio_len_ms * 3 // 4,  # 75%
        ]

        if attempt < len(positions):
            start_pos = positions[attempt]
            end_pos = min(audio_len_ms, start_pos + duration_ms)

            snippet = audio[start_pos:end_pos]
            snippet_path = Path(audio_path).with_suffix(f".acr_alt_{attempt}.mp3")

            try:
                snippet.export(str(snippet_path), format="mp3")
                result = self._call_api(str(snippet_path))
                return self._parse_response(result)
            except Exception:
                return None
            finally:
                if snippet_path.exists():
                    snippet_path.unlink()

        return None
