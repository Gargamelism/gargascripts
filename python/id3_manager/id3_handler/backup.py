"""Backup-aware tag writer for ID3Handler."""

from pathlib import Path

from config import eprint


class SafeWriter:
    """Writes tags with in-memory backup and restore on failure."""

    def write(self, handler, file_path: str, metadata, preserve_existing: bool = True) -> bool:
        path = Path(file_path)
        ext = path.suffix.lower()

        try:
            handler.read_tags(file_path)
        except Exception as e:
            eprint(f"Skipping unreadable file (won't write): {path.name} - {e}")
            return False

        try:
            original_bytes = path.read_bytes()
        except OSError as e:
            eprint(f"Cannot read file for backup: {path.name} - {e}")
            return False

        try:
            if preserve_existing:
                existing = handler.read_tags(file_path)
                metadata = existing.merge_with(metadata)

            fmt = ext[1:]
            write_fn = getattr(handler, f"_write_{fmt}_tags", None)
            if write_fn is None:
                return False
            ok = write_fn(file_path, metadata)

            if not ok:
                try:
                    path.write_bytes(original_bytes)
                except (OSError, IOError) as restore_err:
                    raise RuntimeError(
                        f"Write failed for {path.name} and restore also failed: {restore_err}"
                    )
                return False

            try:
                handler.read_tags(file_path)
            except Exception as e:
                try:
                    path.write_bytes(original_bytes)
                except (OSError, IOError) as restore_err:
                    raise RuntimeError(
                        f"Write corrupted {path.name} and restore also failed: {restore_err}"
                    ) from e
                raise RuntimeError(
                    f"Write corrupted {path.name} — original restored"
                ) from e

            return True

        except RuntimeError:
            raise
        except Exception as e:
            try:
                path.write_bytes(original_bytes)
            except (OSError, IOError) as restore_err:
                raise RuntimeError(
                    f"Failed to write tags to {path.name} and restore also failed: {restore_err}"
                ) from e
            raise RuntimeError(
                f"Failed to write tags to {path.name} — original restored"
            ) from e
