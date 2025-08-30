#!/usr/bin/env python3
"""
IG → Spotify Playlist (Reels to Tracks)

This script:
1) Pulls audio (or metadata) from an Instagram Reel.
2) Identifies the song using ACRCloud (audio fingerprinting).
3) Finds the track on Spotify and adds it to a playlist (creates it if needed).

Now supports loading credentials from a .env file.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from yt_dlp import YoutubeDL
from pydub import AudioSegment
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

try:
    from acrcloud.recognizer import ACRCloudRecognizer
except Exception:
    ACRCloudRecognizer = None
    import hmac, hashlib, base64, time, requests


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def load_env_file(env_file: str | None):
    """
    Load environment variables from a .env file (default: .env in cwd).
    """
    if env_file is None:
        env_file = ".env"
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        eprint(f"Loaded environment from {env_path.resolve()}")
    else:
        eprint(
            f"Warning: .env file not found at {env_path.resolve()} — falling back to process env."
        )


def fetch_ig_metadata_and_audio(url: str, tmpdir: Path) -> dict:
    """
    Use yt_dlp to retrieve metadata and download audio if possible.
    Respects optional .env hints:
      - IG_COOKIEFILE: path to a Netscape cookie file
      - IG_COOKIES_FROM_BROWSER: e.g., 'chrome' or 'firefox' to import from the local browser
    """
    ydl_opts = {
        "outtmpl": str(tmpdir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    cookiefile = os.getenv("IG_COOKIEFILE")
    cookies_from_browser = os.getenv("IG_COOKIES_FROM_BROWSER")
    if cookiefile and Path(cookiefile).exists():
        ydl_opts["cookiefile"] = cookiefile
        eprint(f"Using Instagram cookies file: {cookiefile}")
    elif cookies_from_browser:
        # e.g., 'chrome' or 'firefox'
        ydl_opts["cookiesfrombrowser"] = cookies_from_browser
        eprint(f"Using cookies from browser: {cookies_from_browser}")

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        audio_path = None
        for p in tmpdir.glob("*.mp3"):
            audio_path = p
            break
        info["_audio_path"] = str(audio_path) if audio_path else None
    return info


def parse_title_artist_from_info(info: dict):
    title = None
    artist = None
    if info.get("track"):
        title = info.get("track")
    if info.get("artist"):
        artist = info.get("artist")
    if not title and info.get("title"):
        title = info.get("title")
    if not artist and info.get("uploader"):
        artist = info.get("uploader")
    return title, artist


def acrcloud_recognize_multiple(audio_file: Path):
    """
    Requires .env with: ACRCLOUD_HOST, ACRCLOUD_ACCESS_KEY, ACRCLOUD_ACCESS_SECRET
    Returns list of (title, artist) tuples for all identified songs
    """
    host = os.getenv("ACRCLOUD_HOST")
    key = os.getenv("ACRCLOUD_ACCESS_KEY")
    secret = os.getenv("ACRCLOUD_ACCESS_SECRET")
    if not (host and key and secret):
        eprint("ACRCloud credentials not set. Skipping audio fingerprinting.")
        return []

    audio = AudioSegment.from_file(audio_file)
    audio_len = len(audio)
    
    # Try multiple segments to catch different songs, advancing in 3-second increments
    segments_to_try = []
    advance_step = 3000     # 3 seconds
    
    if audio_len < 12000:  # Less than 12 seconds
        segments_to_try.append((0, audio_len))
    else:
        # Dynamic segment length based on audio length
        if audio_len <= 30000:  # 30 seconds or less
            segment_length = min(14000, audio_len)
        elif audio_len <= 60000:  # 1 minute or less
            segment_length = 15000  # 15 seconds
        elif audio_len <= 120000:  # 2 minutes or less
            segment_length = 18000  # 18 seconds
        else:  # Longer than 2 minutes
            segment_length = 20000  # 20 seconds
        
        # Sample the audio in 3-second advancing steps
        start_pos = 0
        while start_pos < audio_len - 5000:  # Ensure at least 5 seconds remaining
            end_pos = min(start_pos + segment_length, audio_len)
            if end_pos - start_pos >= 5000:  # Only add segments of at least 5 seconds
                segments_to_try.append((start_pos, end_pos))
            start_pos += advance_step
            
            # Limit to reasonable number of segments to avoid excessive API calls
            if len(segments_to_try) >= 20:
                break

    all_songs = []
    seen_songs = set()  # To avoid duplicates
    
    for i, (start_ms, end_ms) in enumerate(segments_to_try):
        start_ms = max(0, start_ms)
        end_ms = min(audio_len, end_ms)
        
        if end_ms - start_ms < 5000:  # Skip segments shorter than 5 seconds
            continue
            
        eprint(f"Trying segment {i+1}/{len(segments_to_try)}: {start_ms/1000:.1f}s - {end_ms/1000:.1f}s")
        
        snippet = audio[start_ms:end_ms]
        snippet_path = audio_file.with_name(f"{audio_file.stem}_snippet_{i}.mp3")
        snippet.export(snippet_path, format="mp3")

        try:
            data = None
            if ACRCloudRecognizer is not None:
                config = {
                    "host": host,
                    "access_key": key,
                    "access_secret": secret,
                    "timeout": 10,
                }
                rec = ACRCloudRecognizer(config)
                res = rec.recognize_by_file(str(snippet_path), 0)
                data = json.loads(res) if isinstance(res, str) else res
            else:
                http_method = "POST"
                http_uri = "/v1/identify"
                data_type = "audio"
                signature_version = "1"
                timestamp = str(int(time.time()))
                string_to_sign = "\n".join(
                    [http_method, http_uri, key, data_type, signature_version, timestamp]
                )
                sign = base64.b64encode(
                    hmac.new(
                        bytes(secret, "utf-8"),
                        bytes(string_to_sign, "utf-8"),
                        digestmod=hashlib.sha1,
                    ).digest()
                ).decode("utf-8")

                with open(snippet_path, "rb") as f:
                    files = {
                        "sample": f,
                        "access_key": (None, key),
                        "data_type": (None, data_type),
                        "signature_version": (None, signature_version),
                        "signature": (None, sign),
                        "timestamp": (None, timestamp),
                    }
                    resp = requests.post(f"https://{host}/v1/identify", files=files, timeout=15)
                    resp.raise_for_status()
                    data = resp.json()

            # Process ALL songs in the response, not just the first one
            music = (data.get("metadata", {}) or {}).get("music", [])
            for song in music:
                title = song.get("title")
                artists = song.get("artists") or []
                artist = artists[0]["name"] if artists else None
                
                if title:
                    # Create a unique identifier to avoid duplicates
                    song_id = (title.lower(), (artist or "").lower())
                    if song_id not in seen_songs:
                        seen_songs.add(song_id)
                        all_songs.append((title, artist))
                        eprint(f"Found: {title} by {artist}")
            
        except Exception as ex:
            eprint(f"ACRCloud recognition error for segment {i+1}: {ex}")
        
        finally:
            # Clean up temporary file
            if snippet_path.exists():
                snippet_path.unlink()

    return all_songs


def acrcloud_recognize(audio_file: Path):
    """
    Legacy function that returns only the first identified song
    """
    songs = acrcloud_recognize_multiple(audio_file)
    if songs:
        return songs[0]
    return None, None


def ensure_spotify_client(
    scope: str = "playlist-modify-public playlist-modify-private user-read-private",
):
    """
    Requires .env with: SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI
    """
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")
    if not (client_id and client_secret and redirect_uri):
        raise RuntimeError("Missing Spotify credentials. Set them in your .env file.")
    auth = SpotifyOAuth(scope=scope, open_browser=True)
    return spotipy.Spotify(auth_manager=auth)


def get_or_create_playlist(sp, playlist_name: str, public: bool = False) -> str:
    results = sp.current_user_playlists(limit=50)
    for pl in results["items"]:
        if pl["name"].lower() == playlist_name.lower():
            return pl["id"]

    user_id = sp.current_user()["id"]
    new_pl = sp.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=public,
        description="Made from Instagram Reels via script",
    )
    return new_pl["id"]


def search_spotify_track(sp, title: str, artist: str | None) -> str | None:
    if artist:
        q = f'track:"{title}" artist:"{artist}"'
    else:
        q = f'track:"{title}"'
    res = sp.search(q=q, type="track", limit=5)
    items = res.get("tracks", {}).get("items", [])
    if items:
        return items[0]["id"]
    res = sp.search(q=title, type="track", limit=5)
    items = res.get("tracks", {}).get("items", [])
    return items[0]["id"] if items else None


def main():
    parser = argparse.ArgumentParser(
        description="Create/append a Spotify playlist from an Instagram Reel URL."
    )
    parser.add_argument("instagram_url", help="Instagram Reel URL")
    parser.add_argument(
        "playlist_name", help="Spotify playlist name (will be created if missing)"
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="Create playlist as public (default: private)",
    )
    parser.add_argument(
        "--skip-acr",
        action="store_true",
        help="Skip ACRCloud recognition (use IG metadata only)",
    )
    parser.add_argument(
        "--env-file", default=".env", help="Path to .env file (default: ./.env)"
    )
    args = parser.parse_args()

    # Load .env before reading any credentials
    load_env_file(args.env_file)

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        eprint("Fetching Instagram media/metadata...")
        info = fetch_ig_metadata_and_audio(args.instagram_url, tmpdir)
        eprint(
            json.dumps(
                {
                    k: info[k]
                    for k in info
                    if k in ("id", "title", "artist", "track", "uploader")
                },
                indent=2,
            )
        )

        title, artist = parse_title_artist_from_info(info)

        songs_to_add = []
        
        # Start with metadata-based song if available
        if title and "original audio" not in (title or "").lower():
            songs_to_add.append((title, artist))

        # Try ACRCloud recognition for better results
        if not args.skip_acr:
            audio_path = info.get("_audio_path")
            if audio_path and Path(audio_path).exists():
                eprint("Trying ACRCloud recognition on multiple audio segments...")
                acr_songs = acrcloud_recognize_multiple(Path(audio_path))
                
                # Add ACR songs, avoiding duplicates with metadata song
                existing_songs = {(t.lower(), (a or "").lower()) for t, a in songs_to_add}
                for acr_title, acr_artist in acr_songs:
                    song_id = (acr_title.lower(), (acr_artist or "").lower())
                    if song_id not in existing_songs:
                        songs_to_add.append((acr_title, acr_artist))
                        existing_songs.add(song_id)
            else:
                eprint(
                    "No downloadable audio found. Consider adding cookies via IG_COOKIEFILE or IG_COOKIES_FROM_BROWSER in .env, or use --skip-acr."
                )

        if not songs_to_add:
            eprint("Could not identify any tracks. Exiting.")
            sys.exit(2)

        # Remove duplicates while preserving order
        unique_songs = []
        seen_songs = set()
        for title, artist in songs_to_add:
            # Create normalized identifier for comparison
            normalized_title = title.lower().strip() if title else ""
            normalized_artist = (artist or "").lower().strip()
            song_key = (normalized_title, normalized_artist)
            
            if song_key not in seen_songs:
                seen_songs.add(song_key)
                unique_songs.append((title, artist))
            else:
                eprint(f"Removed duplicate: {title!r} by {artist!r}")
        
        songs_to_add = unique_songs

        eprint(f"Found {len(songs_to_add)} unique song(s):")
        for i, (t, a) in enumerate(songs_to_add, 1):
            eprint(f"  {i}. {t!r} by {a!r}")

        sp = ensure_spotify_client()
        playlist_id = get_or_create_playlist(sp, args.playlist_name, public=args.public)

        added_tracks = []
        failed_tracks = []
        
        for song_title, song_artist in songs_to_add:
            track_id = search_spotify_track(sp, song_title, song_artist)
            if track_id:
                try:
                    sp.playlist_add_items(playlist_id, [track_id])
                    added_track = sp.track(track_id)
                    added_tracks.append({
                        "name": added_track["name"],
                        "artists": [a["name"] for a in added_track["artists"]],
                        "id": track_id,
                        "external_urls": added_track["external_urls"],
                    })
                    eprint(f"✓ Added: {added_track['name']} by {', '.join(a['name'] for a in added_track['artists'])}")
                except Exception as e:
                    failed_tracks.append({"title": song_title, "artist": song_artist, "error": str(e)})
                    eprint(f"✗ Failed to add {song_title} by {song_artist}: {e}")
            else:
                failed_tracks.append({"title": song_title, "artist": song_artist, "error": "Not found on Spotify"})
                eprint(f"✗ Could not find on Spotify: {song_title} by {song_artist}")

        if not added_tracks:
            eprint("No tracks were successfully added to the playlist.")
            sys.exit(3)

        result = {
            "status": "ok",
            "playlist_name": args.playlist_name,
            "playlist_id": playlist_id,
            "added_tracks": added_tracks,
            "songs_found": len(songs_to_add),
            "tracks_added": len(added_tracks),
        }
        
        if failed_tracks:
            result["failed_tracks"] = failed_tracks
            
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
