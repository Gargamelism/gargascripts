"""Discogs API client for fetching album metadata."""

import re
import time
from typing import List, Optional

import requests
from rapidfuzz import fuzz

from config import eprint
from models import DiscogsRelease, DiscogsTrack
from . import parsing as _parsing

# Title normalization patterns for track matching
_RE_LEADING_TRACKNUM = re.compile(r"^\d+[\.\-\s]+")
_RE_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")



class DiscogsClient:
    """Client for Discogs API."""

    BASE_URL = "https://api.discogs.com"
    USER_AGENT = "ID3Manager/1.0 +https://github.com/gargascripts"

    def __init__(self, user_token: str):
        self.user_token = user_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Discogs token={user_token}",
            "User-Agent": self.USER_AGENT,
        })
        self.rate_limit_remaining = 60
        self._last_request_time = 0

    def _respect_rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        if self.rate_limit_remaining <= 5:
            eprint("Approaching rate limit, waiting 60 seconds...")
            time.sleep(60)
            self.rate_limit_remaining = 60

    def _update_rate_limit(self, response: requests.Response):
        remaining = response.headers.get("X-Discogs-Ratelimit-Remaining")
        if remaining:
            self.rate_limit_remaining = int(remaining)
        self._last_request_time = time.time()

    def search(self, artist: str, album: Optional[str] = None,
               track: Optional[str] = None) -> List[dict]:
        self._respect_rate_limit()

        params = {
            "type": "release",
            "artist": artist,
        }
        if album:
            params["release_title"] = album
        if track:
            params["track"] = track

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/database/search",
                params=params,
                timeout=15
            )
            resp.raise_for_status()
            self._update_rate_limit(resp)
            return resp.json().get("results", [])
        except requests.exceptions.RequestException as e:
            eprint(f"Discogs search error: {e}")
            return []

    def get_release(self, release_id: int) -> Optional[DiscogsRelease]:
        self._respect_rate_limit()

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/releases/{release_id}",
                timeout=15
            )
            resp.raise_for_status()
            self._update_rate_limit(resp)
            return _parsing.parse_release(resp.json())
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                eprint(
                    f"Discogs release {release_id} not fetchable (404) — "
                    f"likely deleted/withdrawn, private, or still in moderation "
                    f"while search index is stale. Skipping."
                )
                return None
            eprint(f"Discogs release fetch error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            eprint(f"Discogs release fetch error: {e}")
            return None

    def find_best_release(self, artist: str, album: Optional[str] = None,
                          track: Optional[str] = None,
                          max_results: int = 5) -> List[DiscogsRelease]:
        results = []
        if album:
            results = self.search(artist, album=album)

        if not results and track:
            results = self.search(artist, track=track)

        if not results:
            results = self.search(artist)

        if not results:
            return []

        candidates = []
        for result in results[:max_results]:
            release = self.get_release(result["id"])
            if release and release.tracklist:
                candidates.append(release)

        candidates.sort(key=lambda r: len(r.tracklist), reverse=True)
        return candidates

    def match_track_to_release(self, release: DiscogsRelease,
                               track_title: str) -> Optional[DiscogsTrack]:
        title_lower = track_title.lower().strip()
        clean_title = _RE_LEADING_TRACKNUM.sub("", title_lower)
        clean_title = _RE_TRAILING_PAREN.sub("", clean_title)

        best_match = None
        best_score = 0

        for track in release.tracklist:
            track_lower = track.title.lower().strip()
            clean_track = _RE_TRAILING_PAREN.sub("", track_lower)

            if clean_title == clean_track:
                return track

            score = fuzz.token_sort_ratio(clean_title, clean_track) / 100
            if score > best_score:
                best_score = score
                best_match = track

        if best_score > 0.7:
            return best_match

        return None

