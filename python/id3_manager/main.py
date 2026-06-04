#!/usr/bin/env python3
"""
ID3 Manager - Audio tag management with ACRCloud and Discogs integration.

Usage:
    python main.py /path/to/album [options]
"""

import argparse
import os
import sys
from pathlib import Path

from config import (
    load_config,
    validate_config,
    eprint,
    get_discogs_token_instructions,
    get_acrcloud_instructions,
)
from id3_handler import ID3Handler  # noqa: F401 — tests patch main.ID3Handler
from interactive import InteractivePrompts
from onedrive_sync import OneDriveSync
from processor import ID3Processor


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="ID3 tag manager: identify songs via ACRCloud, "
        "fetch metadata from Discogs, and organize album folders.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single album folder
  python -m id3_manager /path/to/album

  # Process with auto-confirmation
  python -m id3_manager /path/to/album --yes

  # Dry run to preview changes
  python -m id3_manager /path/to/album --dry-run

  # Process recursively
  python -m id3_manager /path/to/music --recursive

  # Skip folder renaming
  python -m id3_manager /path/to/album --no-rename

  # Only rename files based on existing ID3 tags (no lookups)
  python -m id3_manager /path/to/album --rename-only
""",
    )

    # Required arguments
    parser.add_argument("path", help="Path to audio file or folder to process")

    # Processing options
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Recursively process all subfolders",
    )

    parser.add_argument(
        "--include-root",
        action="store_true",
        help="Include files in root folder when using --recursive (skipped by default)",
    )

    parser.add_argument(
        "--start-at",
        help="When using --recursive, start processing from this folder path (skips earlier folders)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without applying them"
    )

    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-confirm all changes (non-interactive)",
    )

    # Tag handling
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process files even if they have complete tags",
    )

    parser.add_argument(
        "--skip-acr",
        action="store_true",
        help="Skip ACRCloud lookup (use existing tags for Discogs search)",
    )

    parser.add_argument(
        "--skip-discogs",
        action="store_true",
        help="Skip Discogs lookup (use ACRCloud results only)",
    )

    parser.add_argument(
        "--rename-only",
        action="store_true",
        help="Only rename files based on existing ID3 tags (skip all lookups)",
    )

    # Folder handling
    parser.add_argument(
        "--no-rename", action="store_true", help="Skip folder renaming step"
    )

    parser.add_argument(
        "--no-file-rename", action="store_true", help="Skip file renaming step"
    )

    # OneDrive mirroring (keeps bisync in lockstep with local renames)
    parser.add_argument(
        "--mirror-onedrive",
        action="store_true",
        help="Mirror every local rename/move to OneDrive via rclone server-side "
        "moves, so rclone bisync sees matching names on both sides.",
    )

    parser.add_argument(
        "--onedrive-root",
        default=None,
        help="Local root of the OneDrive sync. Required when --mirror-onedrive "
        "is set. Renames outside this root are not mirrored.",
    )

    parser.add_argument(
        "--onedrive-remote",
        default="onedrive:",
        help="rclone remote for OneDrive (default: onedrive:)",
    )

    parser.add_argument(
        "--rclone-path",
        default=None,
        help="Path to the rclone binary (default: auto-detect via PATH, "
        "falling back to /opt/homebrew/bin/rclone)",
    )

    # Configuration
    parser.add_argument(
        "--env-file", default=".env", help="Path to .env file (default: ./.env)"
    )

    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )

    # Verbosity
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress non-essential output"
    )

    return parser


def main():
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate path
    if not os.path.exists(args.path):
        parser.error(f"Path does not exist: {args.path}")

    # Validate --start-at usage
    if args.start_at:
        if not args.recursive:
            eprint("Warning: --start-at has no effect without --recursive")
        elif not os.path.exists(args.start_at):
            parser.error(f"Start folder does not exist: {args.start_at}")
        elif not os.path.isdir(args.start_at):
            parser.error(f"Start path is not a folder: {args.start_at}")

    # Validate --onedrive-root when mirroring is requested so misconfiguration
    # fails loudly instead of silently no-op'ing every mirror call.
    if args.mirror_onedrive:
        if not args.onedrive_root:
            parser.error("--onedrive-root is required when --mirror-onedrive is set")
        onedrive_root = Path(args.onedrive_root)
        if not onedrive_root.exists():
            parser.error(f"OneDrive root does not exist: {args.onedrive_root}")
        elif not onedrive_root.is_dir():
            parser.error(f"OneDrive root is not a directory: {args.onedrive_root}")

    # --rename-only implies skipping all lookups
    if args.rename_only:
        args.skip_acr = True
        args.skip_discogs = True

    # Load configuration
    config = load_config(args.env_file)
    missing = validate_config(config, args.skip_acr, args.skip_discogs)

    if missing:
        eprint(f"\nMissing required credentials: {', '.join(missing)}")
        if "DISCOGS_USER_TOKEN" in missing:
            eprint(get_discogs_token_instructions())
        if any("ACRCLOUD" in m for m in missing):
            eprint(get_acrcloud_instructions())
        eprint("Use --skip-acr or --skip-discogs to proceed without them.\n")
        sys.exit(1)

    # Initialize prompts
    prompts = InteractivePrompts(
        no_color=args.no_color, auto_yes=args.yes, quiet=args.quiet
    )

    # Run processor
    onedrive_sync = (
        OneDriveSync(
            local_root=Path(args.onedrive_root),
            remote=args.onedrive_remote,
            rclone_path=args.rclone_path,
        )
        if args.mirror_onedrive
        else None
    )
    processor = ID3Processor(config, args, prompts, onedrive_sync=onedrive_sync)

    try:
        processor.process(args.path)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
