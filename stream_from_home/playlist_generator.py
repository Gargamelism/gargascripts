import os
import re
import random
import argparse
from typing import List, Optional, Tuple, Dict, Set
from dataclasses import dataclass


@dataclass
class FolderInfo:
    immediate_subfolders: List[str]  # Only direct subfolders
    all_subfolders: List[str]  # All subfolders recursively


def scan_subfolders(base_folder: str) -> FolderInfo:
    """Scan and return both immediate and recursive subfolders from the base folder."""
    immediate_subfolders = []
    all_subfolders = []

    try:
        # Get immediate subfolders
        with os.scandir(base_folder) as entries:
            for entry in entries:
                if entry.is_dir():
                    subfolder_path = entry.path
                    immediate_subfolders.append(subfolder_path)
                    all_subfolders.append(subfolder_path)

                    # Recursively scan subfolders
                    nested_info = scan_subfolders(subfolder_path)
                    all_subfolders.extend(nested_info.all_subfolders)
    except (FileNotFoundError, PermissionError):
        print(f"Access denied or folder not found: {base_folder}")
    except Exception as e:
        print(f"Error accessing {base_folder}: {e}")

    return FolderInfo(immediate_subfolders, all_subfolders)


def get_random_subfolder(base_folder: str, recursive: bool = True) -> Optional[str]:
    """
    Get a random subfolder from the base folder.
    Always includes all nested subfolders in the selection pool.

    Args:
        base_folder: The folder to get a subfolder from
        recursive: Parameter kept for compatibility, but defaults to True
    """
    global _scandir_cache
    if "_scandir_cache" not in globals():
        _scandir_cache = {}

    if base_folder not in _scandir_cache:
        _scandir_cache[base_folder] = scan_subfolders(base_folder)

    folder_info = _scandir_cache[base_folder]
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


def get_preferred_album() -> str:
    """Try to get an album from the predefined list of preferred bands."""
    preferred_bands = {
        "System of a Down": "E:\\OneDrive\\Music\\System of a Down\\",
        "Deftones": "E:\\OneDrive\\Music\\Deftones\\",
        "Tool": "E:\\OneDrive\\Music\\Tool\\",
        "Metallica": "E:\\OneDrive\\Music\\Metallica\\",
        "The Cat Empire": "E:\\OneDrive\\Music\\Cat Empire, The\\",
        "Rage Against the Machine": "E:\\OneDrive\\Music\\Rage Against The Machine",
        "Cake": "E:\\OneDrive\\Music\\Cake\\",
        "Marilyn Manson": "E:\\OneDrive\\Music\\Marilyn Manson\\",
        "Chemical Brothers": "E:\\OneDrive\\Music\\Chemical Brothers, The\\",
        "The Offspring": "E:\\OneDrive\\Music\\Offspring, The\\",
        "Primus": "E:\\OneDrive\\Music\\Primus\\",
        "Zappa": "E:\\OneDrive\\Music\\Zappa, Frank\\",
        "The Residents": "E:\\OneDrive\\Music\\Residents, The\\",
    }

    selected_band = random.choice(list(preferred_bands.keys()))
    band_folder = preferred_bands[selected_band]

    return get_random_subfolder(band_folder)


def get_server_prefix() -> str:
    """Get the server path prefix from user."""
    return input("\nEnter the server path prefix (e.g., /music/): ")


def get_relative_path(full_path: str, root_path: str) -> str:
    """Get the relative path from root to the full path."""
    try:
        rel_path = os.path.relpath(full_path, root_path)
        return rel_path.replace("\\", "/")
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
            server_path = os.path.join(roots[matching_root], rel_path).replace(
                "\\", "/"
            )
        else:
            # Fallback to just using the basename with the default prefix
            server_path = os.path.join(server_prefix, os.path.basename(path)).replace(
                "\\", "/"
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

    # Scan directory for existing numbered playlists
    max_number = 0
    existing_files = set()
    try:
        if os.path.exists(directory):
            for existing_file in os.listdir(directory):
                existing_files.add(existing_file.lower())
                match = re.match(r"^(\d{3})_", existing_file)
                if match:
                    num = int(match.group(1))
                    max_number = max(max_number, num)
    except (OSError, PermissionError):
        pass

    # Check if filename already has 3-digit prefix
    prefix_match = re.match(r"^(\d{3})_", filename)
    if prefix_match:
        # File has a prefix - check if it would clash
        if filename.lower() not in existing_files:
            # No clash, keep the existing prefix
            return None, output_path
        # Clash detected - fall through to renumber

    # Next number is max + 1, or 1 if no numbered files exist
    next_number = max_number + 1
    new_filename = f"{next_number:03d}_{filename}"

    # If filename already had a prefix, remove it before adding new one
    if prefix_match:
        base_filename = re.sub(r"^\d{3}_", "", filename)
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
        print(f"\nPlaylist saved successfully to: {output_path}")
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
        "--pending-base", help="Base folder containing pending/new music"
    )
    parser.add_argument(
        "--pending-prefix",
        default="/pending/",
        help="Server prefix for pending music (default: /pending/)",
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

        # skip non-existent paths
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

    # Get main albums
    playlist_paths = get_albums(music_base, args.number)

    # add pending albums
    pending_base = validate_folder(args.pending_base) if args.pending_base else None
    if pending_base:
        playlist_paths.extend(get_albums(pending_base, 1))

    # add preferred album
    playlist_paths.append(get_preferred_album())

    # Try to add a preferred band album
    playlist_tracks = get_album_tracks(playlist_paths)

    if not args.keep_local_paths:
        # Initialize roots dictionary with the main music folder
        roots = {music_base: args.music_prefix, pending_base: args.pending_prefix}
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
