#!/usr/bin/env python3
"""Check for malformed audio files in a folder tree."""

import sys
from pathlib import Path
from id3_handler import ID3Handler


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <folder>")
        sys.exit(1)

    base = Path(sys.argv[1])
    h = ID3Handler()
    errors = []

    for f in sorted(base.rglob("*")):
        if f.is_file() and ID3Handler.is_supported(str(f)):
            try:
                h.read_tags(str(f))
            except Exception as e:
                errors.append((str(f.relative_to(base)), str(e)))

    if errors:
        print(f"Found {len(errors)} malformed file(s):")
        for path, err in errors:
            print(f"  {path}: {err}")
    else:
        print("No malformed files found.")


if __name__ == "__main__":
    main()
