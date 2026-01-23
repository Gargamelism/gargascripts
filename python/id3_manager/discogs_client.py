"""Discogs API client for fetching album metadata."""

import re
import time
from typing import List, Optional

import requests

from config import eprint
from models import DiscogsRelease, DiscogsTrack


class DiscogsClient:
    """Client for Discogs API."""

    BASE_URL = "https://api.discogs.com"
    USER_AGENT = "ID3Manager/1.0 +https://github.com/gargascripts"

    def __init__(self, user_token: str):
        """
        Initialize Discogs client.

        Args:
            user_token: Discogs personal access token
        """
        self.user_token = user_token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Discogs token={user_token}",
            "User-Agent": self.USER_AGENT,
        })
        self.rate_limit_remaining = 60
        self._last_request_time = 0

    def _respect_rate_limit(self):
        """Ensure we don't exceed rate limits (60 requests/minute)."""
        # Discogs requires at least 1 second between requests
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        if self.rate_limit_remaining <= 5:
            eprint("Approaching rate limit, waiting 60 seconds...")
            time.sleep(60)
            self.rate_limit_remaining = 60

    def _update_rate_limit(self, response: requests.Response):
        """Update rate limit info from response headers."""
        remaining = response.headers.get("X-Discogs-Ratelimit-Remaining")
        if remaining:
            self.rate_limit_remaining = int(remaining)
        self._last_request_time = time.time()

    def search(self, artist: str, album: Optional[str] = None,
               track: Optional[str] = None) -> List[dict]:
        """
        Search Discogs for releases.

        Args:
            artist: Artist name
            album: Album title (optional)
            track: Track title (optional)

        Returns:
            List of search results
        """
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
        """
        Get full release details including tracklist.

        Args:
            release_id: Discogs release ID

        Returns:
            DiscogsRelease if found, None otherwise
        """
        self._respect_rate_limit()

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/releases/{release_id}",
                timeout=15
            )
            resp.raise_for_status()
            self._update_rate_limit(resp)
            return self._parse_release(resp.json())
        except requests.exceptions.RequestException as e:
            eprint(f"Discogs release fetch error: {e}")
            return None

    def _parse_release(self, data: dict) -> DiscogsRelease:
        """Parse Discogs API response into DiscogsRelease."""
        # First pass: collect track data and check for vinyl-style positions
        raw_tracks = []
        has_vinyl_positions = False

        for track_data in data.get("tracklist", []):
            track_type = track_data.get("type_", "track")
            if track_type != "track":
                continue

            position = track_data.get("position", "")
            if self._is_vinyl_position(position):
                has_vinyl_positions = True

            raw_tracks.append({
                "position": position,
                "title": track_data.get("title", ""),
                "duration": track_data.get("duration"),
            })

        # Process tracks based on format type
        tracklist = []

        if has_vinyl_positions:
            # Vinyl-style: assign sequential track numbers across sides
            # Sort by position to ensure A1, A2, B1, B2 ordering
            vinyl_tracks = []
            non_vinyl_tracks = []

            for track_data in raw_tracks:
                position = track_data["position"]
                if self._is_vinyl_position(position):
                    side, track_on_side = self._parse_vinyl_position(position)
                    vinyl_tracks.append((side, track_on_side, track_data))
                else:
                    non_vinyl_tracks.append(track_data)

            # Sort vinyl tracks by side letter, then by track number on that side
            vinyl_tracks.sort(key=lambda x: (x[0], x[1]))

            # Assign sequential track numbers
            # Group by disc (A/B = disc 1, C/D = disc 2, etc.)
            track_number = 1
            current_disc = 1

            for side, track_on_side, track_data in vinyl_tracks:
                disc = (ord(side) - ord('A')) // 2 + 1
                if disc != current_disc:
                    # Starting a new disc, reset track numbering
                    track_number = 1
                    current_disc = disc

                tracklist.append(DiscogsTrack(
                    position=track_data["position"],
                    title=track_data["title"],
                    duration=track_data["duration"],
                    track_number=track_number,
                    disc_number=disc,
                ))
                track_number += 1

            # Add any non-vinyl tracks at the end (rare edge case)
            for track_data in non_vinyl_tracks:
                track_num, disc_num = self._parse_position(track_data["position"])
                tracklist.append(DiscogsTrack(
                    position=track_data["position"],
                    title=track_data["title"],
                    duration=track_data["duration"],
                    track_number=track_num,
                    disc_number=disc_num,
                ))
        else:
            # Non-vinyl: use standard position parsing
            for track_data in raw_tracks:
                position = track_data["position"]
                track_num, disc_num = self._parse_position(position)

                tracklist.append(DiscogsTrack(
                    position=position,
                    title=track_data["title"],
                    duration=track_data["duration"],
                    track_number=track_num,
                    disc_number=disc_num,
                ))

        # Determine total discs
        disc_numbers = {t.disc_number for t in tracklist if t.disc_number}
        total_discs = max(disc_numbers) if disc_numbers else 1

        # Get artists
        artists = [a.get("name", "") for a in data.get("artists", [])]
        # Clean up artist names (remove numbering like "(2)")
        artists = [re.sub(r"\s*\(\d+\)$", "", a) for a in artists]

        # Get label
        labels = data.get("labels", [])
        label = labels[0].get("name") if labels else None

        return DiscogsRelease(
            release_id=data.get("id", 0),
            title=data.get("title", ""),
            artists=artists,
            year=data.get("year", 0),
            tracklist=tracklist,
            total_discs=total_discs,
            genres=data.get("genres", []),
            label=label,
        )

    def _is_vinyl_position(self, position: str) -> bool:
        """Check if position uses vinyl-style format (e.g., A1, B2)."""
        return bool(re.match(r"^[A-Za-z]\d+$", position))

    def _parse_vinyl_position(self, position: str) -> tuple:
        """
        Parse vinyl position into (side_letter, track_on_side).

        Returns:
            (side, track_on_side) tuple, e.g., ('A', 1) for 'A1'
        """
        match = re.match(r"^([A-Za-z])(\d+)$", position)
        if match:
            return match.group(1).upper(), int(match.group(2))
        return None, None

    def _parse_position(self, position: str) -> tuple:
        """
        Parse track position into track number and disc number.

        Handles formats like:
        - "1", "2", "3" (simple numbering)
        - "1-1", "1-2", "2-1" (disc-track)
        - "CD1-1", "CD2-1" (explicit CD notation)

        Note: Vinyl positions (A1, B1) are handled separately in _parse_release()
        to enable sequential numbering across sides.

        Returns:
            (track_number, disc_number) tuple
        """
        if not position:
            return None, None

        # Pattern: disc-track (e.g., "1-5", "2-3")
        disc_track_match = re.match(r"^(\d+)-(\d+)$", position)
        if disc_track_match:
            return int(disc_track_match.group(2)), int(disc_track_match.group(1))

        # Pattern: CD prefix (e.g., "CD1-5", "CD2-3")
        cd_match = re.match(r"^CD(\d+)-(\d+)$", position, re.IGNORECASE)
        if cd_match:
            return int(cd_match.group(2)), int(cd_match.group(1))

        # Pattern: vinyl sides (A1, A2, B1, etc.) - return side-relative track
        # Actual sequential numbering is done in _parse_release()
        vinyl_match = re.match(r"^([A-Za-z])(\d+)$", position)
        if vinyl_match:
            side = vinyl_match.group(1).upper()
            track = int(vinyl_match.group(2))
            # Map A/B to disc 1, C/D to disc 2, etc.
            disc = (ord(side) - ord('A')) // 2 + 1
            return track, disc

        # Simple number
        simple_match = re.match(r"^(\d+)$", position)
        if simple_match:
            return int(simple_match.group(1)), 1

        return None, None

    def find_best_release(self, artist: str, album: Optional[str] = None,
                          track: Optional[str] = None,
                          max_results: int = 5) -> List[DiscogsRelease]:
        """
        Find matching releases from Discogs.

        Args:
            artist: Artist name from ACRCloud
            album: Album name (optional)
            track: Track title (optional)
            max_results: Maximum releases to return

        Returns:
            List of DiscogsRelease candidates
        """
        # Try with album if available
        results = []
        if album:
            results = self.search(artist, album=album)

        # If no results, try with track title
        if not results and track:
            results = self.search(artist, track=track)

        # If still no results, try artist only
        if not results:
            results = self.search(artist)

        if not results:
            return []

        # Fetch full details for top candidates
        candidates = []
        for result in results[:max_results]:
            release = self.get_release(result["id"])
            if release and release.tracklist:
                candidates.append(release)

        # Sort by completeness (more tracks = likely more complete release)
        candidates.sort(key=lambda r: len(r.tracklist), reverse=True)

        return candidates

    def match_track_to_release(self, release: DiscogsRelease,
                               track_title: str) -> Optional[DiscogsTrack]:
        """
        Match a track title to a track in the release.

        Uses fuzzy matching to handle slight title variations.

        Args:
            release: Discogs release
            track_title: Track title to match

        Returns:
            Matching DiscogsTrack if found, None otherwise
        """
        title_lower = track_title.lower().strip()

        # Remove common prefixes/suffixes
        clean_title = re.sub(r"^\d+[\.\-\s]+", "", title_lower)  # Track numbers
        clean_title = re.sub(r"\s*\([^)]*\)\s*$", "", clean_title)  # Parentheticals

        best_match = None
        best_score = 0

        for track in release.tracklist:
            track_lower = track.title.lower().strip()
            clean_track = re.sub(r"\s*\([^)]*\)\s*$", "", track_lower)

            # Exact match
            if clean_title == clean_track:
                return track

            # Substring match (one contains the other)
            if clean_title in clean_track or clean_track in clean_title:
                score = min(len(clean_title), len(clean_track)) / max(len(clean_title), len(clean_track))
                if score > best_score:
                    best_score = score
                    best_match = track

        # Return best match if similarity is high enough
        if best_score > 0.7:
            return best_match

        return None
