"""Configuration management for ID3 Manager."""

import os
import sys
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv


def eprint(*args, **kwargs):
    """Print to stderr."""
    print(*args, file=sys.stderr, **kwargs)


def load_config(env_file: Optional[str] = None) -> dict:
    """
    Load configuration from .env file.

    Args:
        env_file: Path to .env file. Defaults to .env in current directory.

    Returns:
        Dictionary of configuration values.
    """
    if env_file is None:
        env_file = ".env"

    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        eprint(f"Loaded environment from {env_path.resolve()}")
    else:
        eprint(
            f"Warning: .env file not found at {env_path.resolve()} "
            "- falling back to process env."
        )

    return {
        # ACRCloud credentials
        "acrcloud_host": os.getenv("ACRCLOUD_HOST"),
        "acrcloud_access_key": os.getenv("ACRCLOUD_ACCESS_KEY"),
        "acrcloud_access_secret": os.getenv("ACRCLOUD_ACCESS_SECRET"),
        # Discogs credentials
        "discogs_user_token": os.getenv("DISCOGS_USER_TOKEN"),
    }


def validate_config(config: dict, skip_acr: bool = False,
                    skip_discogs: bool = False) -> List[str]:
    """
    Validate configuration and return list of missing credentials.

    Args:
        config: Configuration dictionary from load_config()
        skip_acr: If True, don't require ACRCloud credentials
        skip_discogs: If True, don't require Discogs credentials

    Returns:
        List of missing credential names (empty if all present).
    """
    missing = []

    if not skip_acr:
        acr_keys = [
            ("acrcloud_host", "ACRCLOUD_HOST"),
            ("acrcloud_access_key", "ACRCLOUD_ACCESS_KEY"),
            ("acrcloud_access_secret", "ACRCLOUD_ACCESS_SECRET"),
        ]
        for key, env_name in acr_keys:
            if not config.get(key):
                missing.append(env_name)

    if not skip_discogs:
        if not config.get("discogs_user_token"):
            missing.append("DISCOGS_USER_TOKEN")

    return missing


def get_discogs_token_instructions() -> str:
    """Return instructions for obtaining a Discogs user token."""
    return """
To get a Discogs user token:
1. Go to https://www.discogs.com/settings/developers
2. Click "Generate new token"
3. Copy the token and add to your .env file:
   DISCOGS_USER_TOKEN=your_token_here
"""


def get_acrcloud_instructions() -> str:
    """Return instructions for obtaining ACRCloud credentials."""
    return """
To get ACRCloud credentials:
1. Sign up at https://console.acrcloud.com/
2. Create a new project (Audio & Video Recognition)
3. Copy the host, access key, and access secret to your .env file:
   ACRCLOUD_HOST=identify-eu-west-1.acrcloud.com
   ACRCLOUD_ACCESS_KEY=your_access_key
   ACRCLOUD_ACCESS_SECRET=your_access_secret
"""
