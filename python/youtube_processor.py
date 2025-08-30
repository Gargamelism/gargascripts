"""
YouTube Channel Video Manager
A modular script to mark all videos in a YouTube channel as unwatched.
"""

import os
import logging
import argparse
from typing import List, Dict, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod
from time import time

try:
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Required Google API libraries not found. Install with:")
    print("pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    exit(1)

try:
    import pandas as pd
    import requests
    import openpyxl
    from PIL import Image
    from io import BytesIO
except ImportError:
    print("Excel export requires: pip install pandas openpyxl requests pillow")


@dataclass
class VideoInfo:
    """Data class to store video information."""

    video_id: str
    title: str
    channel_id: str
    published_at: str
    duration: Optional[str] = None
    view_count: Optional[int] = None


class YouTubeAuthenticator:
    """Handles YouTube API authentication."""

    SCOPES = [
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/youtubepartner",
    ]

    def __init__(self, credentials_file: str = "credentials.json", token_file: str = "token.json"):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None

    def authenticate(self) -> bool:
        """Authenticate with YouTube API."""
        creds = None

        # Load existing token
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    logging.error(f"Credentials file {self.credentials_file} not found")
                    return False

                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())

        self.service = build("youtube", "v3", credentials=creds)
        return True

    def get_service(self):
        """Get the YouTube service object."""
        return self.service


class YouTubeDataFetcher:
    """Handles fetching data from YouTube API."""

    def __init__(self, service):
        self.service = service

    def get_channel_id_by_username(self, username: str) -> Optional[str]:
        """Get channel ID from username."""
        try:
            request = self.service.channels().list(part="id", forUsername=username)
            response = request.execute()

            if response["items"]:
                return response["items"][0]["id"]
            return None
        except Exception as e:
            logging.error(f"Error fetching channel ID: {e}")
            return None

    def get_channel_id_by_handle(self, handle: str) -> Optional[str]:
        """Get channel ID from handle (e.g., @channelname)."""
        try:
            # Remove @ if present
            handle = handle.lstrip("@")
            request = self.service.search().list(part="snippet", q=handle, type="channel", maxResults=1)
            response = request.execute()

            if response["items"]:
                return response["items"][0]["snippet"]["channelId"]
            return None
        except Exception as e:
            logging.error(f"Error fetching channel ID by handle: {e}")
            return None

    def get_channel_videos(self, channel_id: str, batch_size: int = 50) -> List[VideoInfo]:
        """Get all videos from a channel."""
        videos = []
        next_page_token = None

        try:
            # Get channel's uploads playlist ID first
            channel_request = self.service.channels().list(part="contentDetails", id=channel_id)
            channel_response = channel_request.execute()

            if not channel_response["items"]:
                logging.error(f"Channel {channel_id} not found")
                return videos

            uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            logging.info(f"Fetching all videos from channel (batch size: {batch_size})")

            while True:
                # Get videos from uploads playlist
                playlist_request = self.service.playlistItems().list(
                    part="snippet",
                    playlistId=uploads_playlist_id,
                    maxResults=min(batch_size, 50),  # API limit is 50
                    pageToken=next_page_token,
                )
                playlist_response = playlist_request.execute()

                batch_count = 0
                for item in playlist_response["items"]:
                    video_info = VideoInfo(
                        video_id=item["snippet"]["resourceId"]["videoId"],
                        title=item["snippet"]["title"],
                        channel_id=channel_id,
                        published_at=item["snippet"]["publishedAt"],
                    )
                    videos.append(video_info)
                    batch_count += 1

                logging.info(f"Fetched {batch_count} videos (total: {len(videos)})")

                next_page_token = playlist_response.get("nextPageToken")

                if not next_page_token:
                    break

        except Exception as e:
            logging.error(f"Error fetching channel videos: {e}")

        logging.info(f"Total videos found: {len(videos)}")
        return videos


class VideoProcessor(ABC):
    """Abstract base class for video processing operations."""

    @abstractmethod
    def process_video(self, video: VideoInfo) -> bool:
        """Process a single video. Return True if successful."""
        pass

    @abstractmethod
    def get_operation_name(self) -> str:
        """Get the name of the operation for logging."""
        pass


class VideoManager:
    """Main class to manage video operations."""

    def __init__(self, authenticator: YouTubeAuthenticator):
        self.authenticator = authenticator
        self.data_fetcher = None
        self.processors: List[VideoProcessor] = []

    def initialize(self) -> bool:
        """Initialize the video manager."""
        if not self.authenticator.authenticate():
            logging.error("Failed to authenticate with YouTube API")
            return False

        service = self.authenticator.get_service()
        self.data_fetcher = YouTubeDataFetcher(service)
        return True

    def add_processor(self, processor: VideoProcessor):
        """Add a video processor."""
        self.processors.append(processor)

    def process_channel(
        self, channel_identifier: str, batch_size: int = 50, confirm: bool = True, fail_on_error: bool = False
    ) -> Dict[str, int]:
        """Process all videos in a channel.

        Args:
            channel_identifier: Channel username, handle (@channel), or ID
            batch_size: Batch size for API requests
            confirm: Whether to show confirmation prompt
            fail_on_error: Whether to stop processing on first error
        """
        results = {"processed": 0, "successful": 0, "failed": 0}

        # Get channel ID
        channel_id = self._resolve_channel_id(channel_identifier)
        if not channel_id:
            logging.error(f"Could not resolve channel: {channel_identifier}")
            return results

        # Get all videos
        logging.info(f"Fetching all videos from channel {channel_id}")
        videos = self.data_fetcher.get_channel_videos(channel_id, batch_size)

        if not videos:
            logging.warning("No videos found in channel")
            return results

        logging.info(f"Found {len(videos)} videos")

        # Show confirmation with video list
        if confirm and not self._confirm_processing(videos):
            logging.info("Operation cancelled by user")
            return results

        # Process videos
        for video in videos:
            results["processed"] += 1
            success = True

            for processor in self.processors:
                try:
                    success = True
                    if processor.process_video(video):
                        if hasattr(processor, "final_process") and not processor.final_process():
                            success = False
                            error_msg = f"Failed to finalize {processor.get_operation_name()} for: {video.title}"
                            logging.error(error_msg)
                        logging.info(f"Successfully {processor.get_operation_name()}: {video.title}")
                    else:
                        success = False
                        error_msg = f"Failed to {processor.get_operation_name()}: {video.title}"
                        logging.warning(error_msg)
                except Exception as e:
                    success = False
                    error_msg = f"Error processing {video.title}: {e}"
                    logging.error(error_msg)
                finally:
                    if fail_on_error and not success:
                        raise RuntimeError(error_msg)

            if success:
                results["successful"] += 1
            else:
                results["failed"] += 1

        return results

    def _confirm_processing(self, videos: List[VideoInfo]) -> bool:
        """Show video list and ask for confirmation."""
        print(f"\n{'='*80}")
        print(f"FOUND {len(videos)} VIDEOS TO PROCESS")
        print(f"{'='*80}")

        # Show first 20 videos, then ask if user wants to see more
        display_count = min(20, len(videos))

        for i, video in enumerate(videos[:display_count], 1):
            # Truncate long titles
            title = video.title[:75] + "..." if len(video.title) > 75 else video.title
            print(f"{i:3d}. {title}")

        if len(videos) > display_count:
            print(f"\n... and {len(videos) - display_count} more videos")

            while True:
                show_more = input(f"\nShow all {len(videos)} video titles? (y/n): ").lower().strip()
                if show_more in ["y", "yes"]:
                    print()
                    for i, video in enumerate(videos[display_count:], display_count + 1):
                        title = video.title[:75] + "..." if len(video.title) > 75 else video.title
                        print(f"{i:3d}. {title}")
                    break
                elif show_more in ["n", "no"]:
                    break
                else:
                    print("Please enter 'y' or 'n'")

        print(f"\n{'='*80}")

        while True:
            operations = [p.get_operation_name() for p in self.processors]
            operation_text = ", ".join(operations) if operations else "process"

            confirm = input(f"Do you want to {operation_text} all {len(videos)} videos? (y/n): ").lower().strip()
            if confirm in ["y", "yes"]:
                return True
            elif confirm in ["n", "no"]:
                return False
            else:
                print("Please enter 'y' or 'n'")

    def _resolve_channel_id(self, identifier: str) -> Optional[str]:
        """Resolve channel identifier to channel ID."""
        # If it looks like a channel ID already
        if identifier.startswith("UC") and len(identifier) == 24:
            return identifier

        # If it starts with @, treat as handle
        if identifier.startswith("@"):
            return self.data_fetcher.get_channel_id_by_handle(identifier)

        # Try as username first, then as handle
        channel_id = self.data_fetcher.get_channel_id_by_username(identifier)
        if not channel_id:
            channel_id = self.data_fetcher.get_channel_id_by_handle(identifier)

        return channel_id


# ------------- start of operations -------------


class LikeVideoProcessor(VideoProcessor):
    """Processor to like videos."""

    def __init__(self, service):
        self.service = service

    def process_video(self, video: VideoInfo) -> bool:
        """Like a video."""
        try:
            request = self.service.videos().rate(id=video.video_id, rating="like")
            request.execute()
            return True
        except Exception as e:
            logging.warning(f"Could not like video {video.title}: {e}")
            return False

    def get_operation_name(self) -> str:
        return "like"


class DislikeVideoProcessor(VideoProcessor):
    """Processor to dislike videos."""

    def __init__(self, service):
        self.service = service

    def process_video(self, video: VideoInfo) -> bool:
        """Dislike a video."""
        try:
            request = self.service.videos().rate(id=video.video_id, rating="dislike")
            request.execute()
            return True
        except Exception as e:
            logging.warning(f"Could not dislike video {video.title}: {e}")
            return False

    def get_operation_name(self) -> str:
        return "dislike"


class RemoveRatingProcessor(VideoProcessor):
    """Processor to remove rating from videos."""

    def __init__(self, service):
        self.service = service

    def process_video(self, video: VideoInfo) -> bool:
        """Remove rating from a video."""
        try:
            request = self.service.videos().rate(id=video.video_id, rating="none")
            request.execute()
            return True
        except Exception as e:
            logging.warning(f"Could not remove rating from video {video.title}: {e}")
            return False

    def get_operation_name(self) -> str:
        return "remove rating"


class AddToPlaylistProcessor(VideoProcessor):
    """Processor to add videos to a playlist."""

    def __init__(self, service, playlist_id: str):
        self.service = service
        self.playlist_id = playlist_id

    def process_video(self, video: VideoInfo) -> bool:
        """Add video to playlist."""
        try:
            request = self.service.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": self.playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video.video_id},
                    }
                },
            )
            request.execute()
            return True
        except Exception as e:
            logging.warning(f"Could not add video {video.title} to playlist: {e}")
            return False

    def get_operation_name(self) -> str:
        return f"add to playlist"


class SubscribeToChannelProcessor(VideoProcessor):
    """Processor to subscribe to the channel (runs once)."""

    def __init__(self, service):
        self.service = service
        self.subscribed = False

    def process_video(self, video: VideoInfo) -> bool:
        """Subscribe to channel (only on first video)."""
        if self.subscribed:
            return True

        try:
            request = self.service.subscriptions().insert(
                part="snippet",
                body={"snippet": {"resourceId": {"kind": "youtube#channel", "channelId": video.channel_id}}},
            )
            request.execute()
            self.subscribed = True
            return True
        except Exception as e:
            logging.warning(f"Could not subscribe to channel: {e}")
            return False

    def get_operation_name(self) -> str:
        return "subscribe to channel"


class DiagnosticProcessor(VideoProcessor):
    """Processor to run diagnostics on API permissions."""

    def __init__(self, service):
        self.service = service
        self.test_count = 0

    def process_video(self, video: VideoInfo) -> bool:
        """Run diagnostic tests on the first few videos only."""
        self.test_count += 1
        if self.test_count > 3:  # Only test first 3 videos
            return True

        logging.info(f"Testing video {self.test_count}: {video.title[:50]}...")

        tests_passed = 0
        total_tests = 0

        # Test 1: Can we get video details?
        total_tests += 1
        try:
            request = self.service.videos().list(part="snippet,statistics", id=video.video_id)
            response = request.execute()
            if response["items"]:
                logging.info(f"Can access video details")
                tests_passed += 1
            else:
                logging.warning(f"Video not found: {video.video_id}")
        except Exception as e:
            logging.error(f"Video details failed: {e}")

        # Test 2: Can we check rating status?
        total_tests += 1
        try:
            request = self.service.videos().getRating(id=video.video_id)
            response = request.execute()
            rating = response["items"][0]["rating"] if response["items"] else "none"
            logging.info(f"Current rating: {rating}")
            tests_passed += 1
        except Exception as e:
            logging.error(f"Rating check failed: {e}")

        # Test 3: Can we attempt to rate (without actually rating)?
        total_tests += 1
        try:
            # This will likely fail but tells us about permissions
            request = self.service.videos().rate(id=video.video_id, rating="none")
            request.execute()
            logging.info(f"Can modify ratings")
            tests_passed += 1
        except Exception as e:
            if "forbidden" in str(e).lower():
                logging.error(f"Rating modification forbidden: {e}")
            elif "not rated" in str(e).lower():
                logging.info(f"Rating API accessible (video not previously rated)")
                tests_passed += 1
            else:
                logging.error(f"Rating test failed: {e}")

        # Test 4: Can we change watch position?
        total_tests += 1
        try:
            request = self.service.videos().update(
                part="id",
                body={
                    "id": video.video_id,
                    "watchInfo": {"videoId": video.video_id, "watchTimeSeconds": 0, "watchedToEndTime": False},
                },
            )
            response = request.execute()
            logging.info(f"Can modify watch position", response)
            tests_passed += 1
        except Exception as e:
            logging.error(f"Watch position modification failed: {e}")

        success_rate = tests_passed / total_tests
        logging.info(
            f"Video {self.test_count} diagnostic: {tests_passed}/{total_tests} tests passed ({success_rate:.1%})"
        )

        return success_rate > 0.5

    def get_operation_name(self) -> str:
        return "run diagnostics"


class ExcelExportProcessor(VideoProcessor):
    """Processor to export video information to Excel with thumbnails."""

    def __init__(self, service, output_file: str = None):
        self.service = service
        self.video_data = []
        self.output_file = output_file or f"youtube_videos_{int(time())}.xlsx"
        self.thumbnail_folder = f"thumbnails_{int(time())}"
        os.makedirs(self.thumbnail_folder, exist_ok=True)

    def process_video(self, video: VideoInfo) -> bool:
        """Collect video data for Excel export."""
        try:
            # Get detailed video information
            request = self.service.videos().list(part="snippet,statistics,contentDetails,status", id=video.video_id)
            response = request.execute()

            if not response["items"]:
                logging.warning(f"Video details not found: {video.video_id}")
                return False

            video_details = response["items"][0]
            snippet = video_details["snippet"]
            statistics = video_details.get("statistics", {})
            content_details = video_details.get("contentDetails", {})
            status = video_details.get("status", {})

            # Download thumbnail
            thumbnail_path = self._download_thumbnail(video.video_id, snippet.get("thumbnails", {}))

            # Collect all video data
            video_row = {
                "Video ID": video.video_id,
                "Title": snippet.get("title", ""),
                "Description": (
                    snippet.get("description", "")[:500] + "..."
                    if len(snippet.get("description", "")) > 500
                    else snippet.get("description", "")
                ),
                "Channel ID": video.channel_id,
                "Channel Title": snippet.get("channelTitle", ""),
                "Published At": snippet.get("publishedAt", ""),
                "Duration": content_details.get("duration", ""),
                "View Count": int(statistics.get("viewCount", 0)),
                "Like Count": int(statistics.get("likeCount", 0)),
                "Comment Count": int(statistics.get("commentCount", 0)),
                "Category ID": snippet.get("categoryId", ""),
                "Default Language": snippet.get("defaultLanguage", ""),
                "Privacy Status": status.get("privacyStatus", ""),
                "Upload Status": status.get("uploadStatus", ""),
                "Tags": ", ".join(snippet.get("tags", [])),
                "Thumbnail Path": thumbnail_path,
                "Video URL": f"https://www.youtube.com/watch?v={video.video_id}",
            }

            self.video_data.append(video_row)
            logging.info(f"Collected data for: {snippet.get('title', '')[:50]}...")
            return True

        except Exception as e:
            logging.error(f"Error collecting video data: {e}")
            return False

    def _download_thumbnail(self, video_id: str, thumbnails: dict) -> str:
        """Download video thumbnail."""
        try:
            # Try to get the highest quality thumbnail available
            thumbnail_url = None
            for quality in ["maxres", "high", "medium", "default"]:
                if quality in thumbnails:
                    thumbnail_url = thumbnails[quality]["url"]
                    break

            if not thumbnail_url:
                return ""

            # Download thumbnail
            response = requests.get(thumbnail_url, timeout=10)
            response.raise_for_status()

            # Save thumbnail
            thumbnail_path = os.path.join(self.thumbnail_folder, f"{video_id}.jpg")

            # Convert and save as JPEG
            image = Image.open(BytesIO(response.content))
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGB")
            image.save(thumbnail_path, "JPEG", quality=85)

            return thumbnail_path

        except Exception as e:
            logging.debug(f"Could not download thumbnail for {video_id}: {e}")
            return ""

    def final_process(self) -> bool:
        """Export collected data to Excel."""
        if not self.video_data:
            logging.warning("No video data to export")
            return False

        try:
            # Create DataFrame
            df = pd.DataFrame(self.video_data)

            # Create Excel writer with formatting
            with pd.ExcelWriter(self.output_file, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Videos", index=False)

                # Get workbook and worksheet
                workbook = writer.book
                worksheet = writer.sheets["Videos"]

                # Auto-adjust column widths
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)  # Cap at 50 characters
                    worksheet.column_dimensions[column_letter].width = adjusted_width

            logging.info(f"Excel export completed: {self.output_file}")
            logging.info(f"Thumbnails saved in: {self.thumbnail_folder}")
            logging.info(f"Total videos exported: {len(self.video_data)}")
            return True

        except Exception as e:
            logging.error(f"Error exporting to Excel: {e}")
            return False

    def get_operation_name(self) -> str:
        return "export to Excel"


# ------------- end of operations -------------


class YouTubeChannelProcessor:
    """Main application class with multiple processing options."""

    def __init__(self, credentials_file: str = "credentials.json", credentials_out: str = "token.json"):
        self.authenticator = YouTubeAuthenticator(credentials_file, credentials_out)
        self.video_manager = VideoManager(self.authenticator)
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("youtube_processor.log"), logging.StreamHandler()],
        )

    def _create_processors(
        self, operations: List[str], playlist_id: Optional[str] = None, output_file: Optional[str] = None
    ) -> List[VideoProcessor]:
        """Create processor instances based on requested operations."""
        service = self.authenticator.get_service()
        processors = []

        processor_map = {
            "like": lambda: LikeVideoProcessor(service),
            "dislike": lambda: DislikeVideoProcessor(service),
            "remove-rating": lambda: RemoveRatingProcessor(service),
            "subscribe": lambda: SubscribeToChannelProcessor(service),
            "diagnose": lambda: DiagnosticProcessor(service),
            "export-excel": lambda: ExcelExportProcessor(service, output_file),
        }

        for operation in operations:
            if operation == "add-to-playlist":
                if not playlist_id:
                    logging.error("Playlist ID required for add-to-playlist operation")
                    continue
                processors.append(AddToPlaylistProcessor(service, playlist_id))
            elif operation in processor_map:
                processors.append(processor_map[operation]())
            else:
                logging.warning(f"Unknown operation: {operation}")

        return processors

    def process_channel(
        self,
        channel_identifier: str,
        operations: List[str],
        batch_size: int = 50,
        confirm: bool = True,
        playlist_id: Optional[str] = None,
        fail_on_error: bool = False,
    ) -> bool:
        """Process channel with specified operations."""
        operation_names = ", ".join(operations)
        logging.info(f"Starting to {operation_names} videos from channel: {channel_identifier}")

        if not self.video_manager.initialize():
            return False

        # Create and add processors
        processors = self._create_processors(operations, playlist_id)
        if not processors:
            logging.error("No valid processors created")
            return False

        for processor in processors:
            self.video_manager.add_processor(processor)

        # Process the channel
        results = self.video_manager.process_channel(channel_identifier, batch_size, confirm, fail_on_error)

        logging.info(f"Processing complete. Results: {results}")
        return results["successful"] > 0


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Process YouTube channel videos with various operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available operations:
  like            Like all videos
  dislike         Dislike all videos  
  remove-rating   Remove like/dislike rating from videos
  add-to-playlist Add videos to specified playlist (requires --playlist-id)
  subscribe       Subscribe to the channel
  diagnose        Run diagnostics on API permissions

Examples:
  %(prog)s @channelname --operations remove-rating
  %(prog)s channelname --operations like subscribe
  %(prog)s UC123... --operations add-to-playlist --playlist-id PLxxx...
  %(prog)s channelname --operations add-to-playlist like --no-confirm
        """,
    )

    parser.add_argument(
        "--operations",
        nargs="+",
        required=True,
        choices=["like", "dislike", "remove-rating", "add-to-playlist", "subscribe", "diagnose", "export-excel"],
        help="Operations to perform on videos",
    )

    parser.add_argument("channel", help="Channel username, handle (@channel), or ID")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for API requests (default: 50)")
    parser.add_argument("--credentials-in", default="credentials.json", help="Path to credentials file")
    parser.add_argument("--credentials-out", default="token.json", help="Path to credentials file")
    parser.add_argument("--no-confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--playlist-id", help="Playlist ID (required for add-to-playlist operation)")
    parser.add_argument("--fail-on-error", action="store_true", help="Exit on first error instead of continuing")
    parser.add_argument("--output-file", help="Output Excel file name (default: auto-generated)")

    args = parser.parse_args()

    if "add-to-playlist" in args.operations and not args.playlist_id:
        parser.error("--playlist-id is required when using 'add-to-playlist' operation")
    if "export-excel" in args.operations and not args.output_file:
        args.output_file = f"youtube_videos_{int(time())}.xlsx"

    return args


def main():
    """Main function for command line usage."""
    args = parse_args()

    processor = YouTubeChannelProcessor(args.credentials_in, args.credentials_out)
    success = processor.process_channel(
        channel_identifier=args.channel,
        operations=args.operations,
        batch_size=args.batch_size,
        confirm=not args.no_confirm,
        playlist_id=args.playlist_id,
        fail_on_error=args.fail_on_error,
    )

    if success:
        operations_text = ", ".join(args.operations)
        print(f"Successfully completed operations: {operations_text}")
    else:
        print("Failed to process videos. Check logs for details.")


if __name__ == "__main__":
    main()
