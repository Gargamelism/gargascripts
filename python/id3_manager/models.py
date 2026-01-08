"""Data models for ID3 Manager."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List


class TagStatus(Enum):
    """Status of ID3 tags for an audio file."""
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


@dataclass
class TrackMetadata:
    """Represents metadata for a single track."""
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    album_artist: Optional[str] = None
    track_number: Optional[int] = None
    total_tracks: Optional[int] = None
    disc_number: Optional[int] = None
    total_discs: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None

    def is_complete(self, is_multi_disc: bool = False) -> bool:
        """Check if required tags are present."""
        required = [self.title, self.artist, self.track_number]
        if is_multi_disc:
            required.append(self.disc_number)
        return all(r is not None for r in required)

    def get_status(self, is_multi_disc: bool = False) -> TagStatus:
        """Get the overall tag status."""
        if self.is_complete(is_multi_disc):
            return TagStatus.COMPLETE
        if any([self.title, self.artist, self.album]):
            return TagStatus.PARTIAL
        return TagStatus.MISSING

    def merge_with(self, other: "TrackMetadata") -> "TrackMetadata":
        """Create new metadata by filling missing fields from other."""
        return TrackMetadata(
            title=self.title or other.title,
            artist=self.artist or other.artist,
            album=self.album or other.album,
            album_artist=self.album_artist or other.album_artist,
            track_number=self.track_number or other.track_number,
            total_tracks=self.total_tracks or other.total_tracks,
            disc_number=self.disc_number or other.disc_number,
            total_discs=self.total_discs or other.total_discs,
            year=self.year or other.year,
            genre=self.genre or other.genre,
        )


@dataclass
class ACRCloudResult:
    """Result from ACRCloud fingerprint recognition."""
    title: str
    artists: List[str]
    album: Optional[str] = None
    release_date: Optional[str] = None
    label: Optional[str] = None
    confidence: float = 0.0


@dataclass
class DiscogsTrack:
    """A single track from a Discogs release."""
    position: str
    title: str
    duration: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None


@dataclass
class DiscogsRelease:
    """Discogs release information."""
    release_id: int
    title: str
    artists: List[str]
    year: int
    tracklist: List[DiscogsTrack] = field(default_factory=list)
    total_discs: int = 1
    genres: List[str] = field(default_factory=list)
    label: Optional[str] = None

    def find_track(self, title: str, artist: str = None) -> Optional[DiscogsTrack]:
        """Find a track in the tracklist by title (fuzzy match)."""
        title_lower = title.lower()
        for track in self.tracklist:
            if title_lower in track.title.lower() or track.title.lower() in title_lower:
                return track
        return None


@dataclass
class AudioFile:
    """Represents an audio file with its current and proposed metadata."""
    file_path: str
    format: str  # 'mp3', 'flac', 'm4a'
    current_tags: TrackMetadata = field(default_factory=TrackMetadata)
    proposed_tags: Optional[TrackMetadata] = None
    acr_result: Optional[ACRCloudResult] = None
    discogs_release: Optional[DiscogsRelease] = None
    discogs_track: Optional[DiscogsTrack] = None

    @property
    def tag_status(self) -> TagStatus:
        """Get current tag status."""
        return self.current_tags.get_status()

    @property
    def needs_processing(self) -> bool:
        """Check if file needs tag processing."""
        return self.tag_status != TagStatus.COMPLETE


@dataclass
class AlbumFolder:
    """Represents a folder containing audio files (potentially one disc of an album)."""
    folder_path: str
    audio_files: List[AudioFile] = field(default_factory=list)
    detected_disc_number: Optional[int] = None
    parent_folder: Optional[str] = None
    proposed_name: Optional[str] = None
    album_info: Optional[TrackMetadata] = None

    @property
    def is_multi_disc_part(self) -> bool:
        """Check if this folder is part of a multi-disc album."""
        return self.parent_folder is not None or self.detected_disc_number is not None


@dataclass
class ProcessingStats:
    """Statistics for a processing run."""
    total_files: int = 0
    files_processed: int = 0
    tags_updated: int = 0
    files_skipped: int = 0
    acr_lookups: int = 0
    discogs_lookups: int = 0
    folders_renamed: int = 0
    errors: List[str] = field(default_factory=list)
    malformed_files: List[str] = field(default_factory=list)
