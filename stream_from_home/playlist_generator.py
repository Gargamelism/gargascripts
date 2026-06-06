import json
import os
import re
import random
import argparse
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple, Dict


@dataclass
class FolderInfo:
    immediate_subfolders: List[str]  # Only direct subfolders
    all_subfolders: List[str]  # All subfolders recursively


@dataclass
class SpecialBandsConfig:
    preferred_bands: List[str] = None
    pending_bands: List[str] = None


def scan_subfolders(base_folder: str) -> FolderInfo:
    """Scan and return both immediate and recursive subfolders from the base folder."""
    immediate_subfolders = []
    all_subfolders = []
    folders_to_scan = [base_folder]

    try:
        while folders_to_scan:
            current_folder = folders_to_scan.pop()
            with os.scandir(current_folder) as entries:
                for entry in entries:
                    if entry.is_dir():
                        subfolder_path = entry.path
                        immediate_subfolders.append(subfolder_path)
                        all_subfolders.append(subfolder_path)
                        folders_to_scan.append(subfolder_path)

    except (FileNotFoundError, PermissionError):
        print(f"Access denied or folder not found: {base_folder}")
    except Exception as e:
        print(f"Error accessing {base_folder}: {e}")

    return FolderInfo(immediate_subfolders, all_subfolders)


@lru_cache(maxsize=1)
def get_folder_info(base_folder: str) -> FolderInfo:
    """Get all subfolders recursively from the base folder."""
    return scan_subfolders(base_folder)


def get_random_subfolder(base_folder: str, recursive: bool = True) -> Optional[str]:
    """
    Get a random subfolder from the base folder.
    Always includes all nested subfolders in the selection pool.

    Args:
        base_folder: The folder to get a subfolder from
        recursive: Parameter kept for compatibility, but defaults to True
    """
    folder_info = get_folder_info(base_folder)
    subfolders = (
        folder_info.all_subfolders if recursive else folder_info.immediate_subfolders
    )
    return random.choice(subfolders) if subfolders else None


def validate_folder(folder_path: str) -> Optional[str]:
    """Validate if the folder exists and is accessible."""
    if not folder_path:
        print("No folder path provided.")
        return None

    if not os.path.isdir(folder_path):
        print(f"Folder not found: {folder_path}")
        return None

    return folder_path


def get_albums(base_folder: str, number_of_albums: int) -> List[str]:
    """Get the specified number of albums from the base folder."""
    playlist_paths = []
    print("\nScanning folders recursively...")
    while len(playlist_paths) < number_of_albums:
        current_folder = get_random_subfolder(
            base_folder
        )  # recursive is True by default

        if not current_folder:
            print("No more subfolders available.")
            break

        print(f"\nFound folder: {current_folder}")
        user_response = input("Add this folder to playlist? (y/n): ").lower()

        if user_response == "y":
            playlist_paths.append(current_folder)
            print(f"Added! ({len(playlist_paths)}/{number_of_albums})")

    return playlist_paths


def get_additional_band_album(band_name: str, folder_info: FolderInfo) -> Optional[str]:
    """Try to get an album from the predefined list of preferred bands."""
    band_folder = next(
        (
            folder
            for folder in folder_info.all_subfolders
            if os.path.basename(folder) == band_name
        ),
        None,
    )

    if not band_folder:
        print(f"Preferred band '{band_name}' not found in the music collection.")
        return None

    return get_random_subfolder(band_folder)


def get_server_prefix() -> str:
    """Get the server path prefix from user."""
    return input("\nEnter the server path prefix (e.g., /music/): ")


def get_relative_path(full_path: str, root_path: str) -> str:
    """Get the relative path from root to the full path."""
    try:
        return os.path.relpath(full_path, root_path)
    except ValueError:
        # If paths are on different drives, just use the basename
        return os.path.basename(full_path)


def convert_to_server_paths(
    paths: List[str], roots: Dict[str, str], server_prefix: str
) -> List[str]:
    """
    Convert local paths to server paths maintaining folder structure.

    Args:
        paths: List of full local paths
        roots: Dictionary mapping full local root paths to their corresponding server prefixes
        server_prefix: Default server prefix for paths without a matching root
    """
    server_paths = []
    for path in paths:
        # Find the matching root for this path
        matching_root = None
        for root in roots:
            if path.startswith(root):
                matching_root = root
                break

        if matching_root:
            # Use the specific prefix for this root
            rel_path = get_relative_path(path, matching_root)
            # Use forward slashes for server paths (URL-style)
            server_path = os.path.join(roots[matching_root], rel_path).replace(
                os.sep, "/"
            )
        else:
            # Fallback to just using the basename with the default prefix
            server_path = os.path.join(server_prefix, os.path.basename(path)).replace(
                os.sep, "/"
            )

        server_paths.append(server_path)

    return server_paths


def get_next_playlist_number(output_path: str) -> Tuple[int, str]:
    """
    Check if filename needs a numeric prefix and determine the next number.
    Returns tuple of (next_number, updated_filename).
    If the file already has a prefix but would cause a clash, it gets renumbered.
    """
    filename = os.path.basename(output_path)
    directory = os.path.dirname(os.path.abspath(output_path))

    prefix_match = re.match(r"^(\d{3})_", filename)
    base_filename = re.sub(r"^\d{3}_", "", filename) if prefix_match else filename

    # Scan directory for existing numbered playlists with the same base name
    max_number = 0
    existing_files = set()
    try:
        if os.path.exists(directory):
            for existing_file in os.listdir(directory):
                existing_files.add(existing_file.lower())
                match = re.match(r"^(\d{3})_(.+)$", existing_file)
                if match and match.group(2).lower() == base_filename.lower():
                    max_number = max(max_number, int(match.group(1)))
    except (OSError, PermissionError):
        pass

    # Check if filename already has 3-digit prefix
    if prefix_match:
        if filename.lower() not in existing_files:
            return None, output_path
        # Clash detected - fall through to renumber

    next_number = max_number + 1
    new_filename = f"{next_number:03d}_{base_filename}"
    new_path = os.path.join(directory, new_filename)

    return next_number, new_path


def save_playlist(playlist_content: List[str], output_path: str) -> None:
    """
    Save the playlist to a file.
    Wraps paths in quotes to handle spaces and special characters properly.
    Automatically adds numeric prefix if not present.
    """
    # Ensure the file has .m3u extension
    if not output_path.endswith(".m3u"):
        output_path += ".m3u"

    # Add numeric prefix if needed
    number, output_path = get_next_playlist_number(output_path)
    if number:
        print(f"Adding prefix {number:03d}_ to filename")

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # any additional processing
    playlist_items = [path for path in playlist_content]

    try:
        with open(output_path, "w", encoding="utf-8") as file:
            file.write("\n".join(playlist_items))
        print(f"\nPlaylist saved successfully to: {output_path} containing {len(playlist_items)} tracks.")
    except IOError as e:
        print(f"Error saving playlist: {e}")


@dataclass
class PathRoot:
    local_path: str
    server_prefix: str


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a music playlist from folders."
    )
    parser.add_argument("output", help="Output path for the playlist file")
    parser.add_argument(
        "--music-base",
        required=True,
        help="Base folder containing main music collection",
    )
    parser.add_argument(
        "--music-prefix",
        default="/music/",
        help="Server prefix for main music collection (default: /music/)",
    )
    parser.add_argument(
        "--keep-local-paths",
        action="store_true",
        help="Convert local paths to server paths in the playlist",
    )
    parser.add_argument(
        "-n",
        "--number",
        type=int,
        default=10,
        help="Number of albums to include (default: 10)",
    )
    parser.add_argument(
        "--special-bands",
        help="Special bands to include in the playlist",
    )
    return parser.parse_args()


def get_album_tracks(playlist_paths) -> List[str]:
    """
    Expand folder entries in playlist_paths into individual music files.
    This function mutates the input list to contain files (absolute paths)
    and also returns the resulting list.
    """
    music_exts = {
        ".mp3",
        ".flac",
        ".m4a",
        ".wav",
        ".ogg",
        ".aac",
        ".wma",
        ".alac",
        ".aiff",
        ".opus",
    }

    found_files = []

    for path in list(playlist_paths):
        if not path:
            continue

        if os.path.isdir(path):
            for root, _, files in os.walk(path):
                # filter and sort to keep deterministic ordering
                music_files = [
                    file_name
                    for file_name in files
                    if os.path.splitext(file_name)[1].lower() in music_exts
                ]
                music_files.sort()
                for file_name in music_files:
                    full = os.path.abspath(os.path.join(root, file_name))
                    found_files.append(full)
        else: 
            print(f"Skipping missing or unsupported path: {path}")

    return found_files


def generate_playlist() -> None:
    """Main function to generate the playlist."""
    # Parse command line arguments
    args = parse_arguments()

    # Validate music base folder
    music_base = validate_folder(args.music_base)
    if not music_base:
        return

    special_bands = None
    if args.special_bands:
        if not os.path.isfile(args.special_bands):
            print(f"Error: Additional config file not found: {args.special_bands}")
            return
        with open(args.special_bands, "r") as f:
            special_bands = SpecialBandsConfig(**json.load(f))

    # Get main albums
    playlist_paths = get_albums(music_base, args.number)

    # add preferred album if preferred base is provided
    if special_bands and special_bands.preferred_bands:
        preferred_band = random.choice(special_bands.preferred_bands)
        preferred_album = get_additional_band_album(preferred_band, folder_info=get_folder_info(music_base))
        if preferred_album:
            playlist_paths.append(preferred_album)

    if special_bands and special_bands.pending_bands:
        pending_band = random.choice(special_bands.pending_bands)
        pending_album = get_additional_band_album(pending_band, folder_info=get_folder_info(music_base))
        if pending_album:
            playlist_paths.append(pending_album)

    # Try to add a preferred band album
    playlist_tracks = get_album_tracks(playlist_paths)

    if not args.keep_local_paths:
        # Initialize roots dictionary with the main music folder
        roots = {music_base: args.music_prefix}
        # Convert paths using the collected roots
        playlist_tracks = convert_to_server_paths(
            paths=playlist_tracks,
            roots=roots,
            server_prefix=args.music_prefix,  # Use music prefix as default
        )

    # Save the playlist
    save_playlist(playlist_tracks, args.output)


if __name__ == "__main__":
    generate_playlist()
