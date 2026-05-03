# Auto-recover from local↔remote name divergence in OneDriveSync

## Context

When id3_manager renames a local file, `OneDriveSync.moveto()` issues `rclone moveto` to mirror the rename on OneDrive. This assumes the remote source path matches the local source path. In practice the user has files where local and remote diverged — local: `Black Sun Empire - Driving Insane CD1 - 07 - Stasis.mp3`, remote: `1.07 - Black Sun Empire - Stasis.mp3`. rclone fails with `Server side directory move failed: directory not found` (Graph returns `itemNotFound` because the source path doesn't resolve), and the current code aborts the local rename entirely.

The fix: when the source is confirmed missing on the remote (and the local item is a single file), transparently recover by uploading the (already-tag-edited) local file to the NEW remote path, then best-effort identify and delete the OLD remote file under its diverged name. The user accepts the risk that the OLD remote file may not always be findable (would leave an orphan — bisync will not auto-clean these; user resolves manually).

## Files to modify

- [sync_results.py](../sync_results.py) — **NEW MODULE** containing all dataclass return types (`RcloneResult`, `MoveResult`, `LsJsonResult`, `DivergenceConfirmation`, `RecoveryMetadata`, `CommitResult`). Single source of truth so `onedrive_sync.py`, `folder_manager.py`, and tests all import the same types.
- [onedrive_sync.py](../onedrive_sync.py) — divergence detection + recovery; `moveto`/`copyto` migrate to dataclass returns; new helpers (`_lsjson`, `_copyto_explicit`, `_deletefile`, `_recover_diverged_rename`, `_confirm_source_missing`, etc.) all use dataclasses.
- [folder_manager.py](../folder_manager.py) — `_mirror_rename` returns `MoveResult`; `_commit_with_rollback` returns `CommitResult` and accepts a `MoveResult`; the 4 public rename/move methods return `CommitResult`.
- [main.py](../main.py) — call-site updates: `_handle_file_renames`, `_push_tag_writes_to_onedrive`, and the 4 callers of folder_manager rename/move methods unpack via attribute access (`result.success`, `result.message`) instead of tuple unpack.
- [tests/test_onedrive_sync.py](../tests/test_onedrive_sync.py) and [tests/test_folder_manager.py](../tests/test_folder_manager.py) — assertions migrate to attribute access; new tests for recovery helpers.

No changes needed to [reorganize_multi_disc_album](../folder_manager.py#L357) (still returns `Tuple[bool, str]` — out of scope) or [create_multi_disc_structure](../folder_manager.py#L284) (untouched here, separate ticket noted at bottom).

## Existing-code summary (anchors used below)

| Item | Location | Current shape |
|---|---|---|
| `OneDriveSync.__init__(local_root, remote="onedrive:", rclone_path=None, timeout=120, log=_default_log)` | [onedrive_sync.py:25-39](../onedrive_sync.py#L25-L39) | `self.timeout=120` (moveto), `self.timeout*5=600s` (copyto effective) |
| `OneDriveSync._to_remote(local_path) -> str` | [onedrive_sync.py:49-54](../onedrive_sync.py#L49-L54) | NFC-normalized; returns `"<remote>:<rel-posix-path>"`. Works on `Path.parent` too. |
| `OneDriveSync.moveto(local_src, local_dst, dry_run=False) -> Tuple[bool, str]` | [onedrive_sync.py:56-104](../onedrive_sync.py#L56-L104) | argv: `[rclone, "moveto", remote_src, remote_dst]` (+ `--dry-run`). `subprocess.run(..., capture_output=True, text=True, timeout=self.timeout)`. Error: `stderr = (result.stderr or result.stdout).strip()` |
| `OneDriveSync.copyto(local_path, dry_run=False, timeout=None) -> Tuple[bool, str]` | [onedrive_sync.py:106-165](../onedrive_sync.py#L106-L165) | argv: `[rclone, "copyto", str(local), remote_dst, "--checksum"]` (+ `--dry-run`). Default timeout `self.timeout * 5`. `copyto` keys destination off `_to_remote(local_path)`. |
| `_mirror_rename(local_src, local_dst, dry_run) -> Tuple[bool, str]` | [folder_manager.py:37-43](../folder_manager.py#L37-L43) | Returns `(True, "")` if no onedrive_sync; else delegates to `moveto`. |
| `_commit_with_rollback(local_src, local_dst, commit_fn) -> Tuple[bool, str]` | [folder_manager.py:45-67](../folder_manager.py#L45-L67) | Order: `commit_fn()` runs **first** locally; on exception, `_mirror_rename(local_dst, local_src, dry_run=False)` reverses remote. |
| Callers of `_mirror_rename` | folder_manager.py | 4 public-method sites + 1 rollback inside `_commit_with_rollback` — see Section 2. |
| `ID3Handler.read_tags(file_path) -> TrackMetadata` | [id3_handler.py:46-67](../id3_handler.py#L46-L67) | Reads `.mp3`/`.flac`/`.m4a`. `TrackMetadata` carries `title`, `track_number`, `total_tracks`. **Does NOT carry duration**. |
| `ID3Handler._parse_track_disc(value) -> (int|None, int|None)` | [id3_handler.py:350-366](../id3_handler.py#L350-L366) | Parses `"7"`, `"7/12"`, `"07/12"`. Reusable. (Out of scope for dataclass migration — internal helper that returns a 2-tuple of independent values; not modified here.) |
| `FolderManager._sanitize_name(name)` | [folder_manager.py:211-222](../folder_manager.py#L211-L222) | Strips invalid chars + NFC normalize. Not directly reusable for our case. |
| Supported audio extensions | [id3_handler.py:19](../id3_handler.py#L19) | `{".mp3", ".flac", ".m4a"}` |
| Test files | [tests/test_onedrive_sync.py](../tests/test_onedrive_sync.py), [tests/test_folder_manager.py](../tests/test_folder_manager.py) | pytest. Run: `pytest tests/` |
| Imports already in onedrive_sync.py | top of file | `shlex`, `shutil`, `subprocess`, `unicodedata`, `Path`, `Callable`, `Optional`, `Tuple`. **Need to add at module level** (no lazy/inline imports): `re`, `json`, `from typing import List`, `from mutagen import File as MutagenFile`, `from id3_handler import ID3Handler`, `from sync_results import (RcloneResult, MoveResult, LsJsonResult, DivergenceConfirmation, RecoveryMetadata)`. (Remove `Tuple` if no longer used after migration.) `mutagen>=1.47.0` is already a declared dependency in [requirements.txt](../requirements.txt) and `id3_handler` is already imported elsewhere (e.g. [main.py:26](../main.py#L26)) — no circular-import risk. |
| `FolderManager.__init__` | [folder_manager.py:28-35](../folder_manager.py#L28-L35) | Single attribute `self.onedrive_sync`. No logger. Constructed in [main.py:60](../main.py#L60) as `FolderManager(onedrive_sync=onedrive_sync)`. |
| `TrackMetadata` dataclass | [models.py:17-29](../models.py#L17-L29) | Fields: `title`, `artist`, `album`, `album_artist`, `track_number`, `total_tracks`, `disc_number`, `total_discs`, `year`, `genre`. All `Optional` with defaults. |

## Implementation

### 1. New module: `sync_results.py`

Create a new file [sync_results.py](../sync_results.py) at the project root (sibling of `onedrive_sync.py`, `folder_manager.py`). All cross-module result types live here so producer and consumer modules import from the same place.

```python
# sync_results.py
"""Dataclasses for sync-operation return values (rclone wrappers, rename/move flows)."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class RcloneResult:
    """Result of a single rclone subprocess invocation (copyto, deletefile, copyto_explicit)."""
    success: bool
    message: str  # human-readable status ("pushed ...", "deleted ...") or error string


@dataclass(frozen=True)
class MoveResult:
    """Result of OneDriveSync.moveto, FolderManager._mirror_rename, and _recover_diverged_rename.

    `mode` values:
      - "moveto"    — rclone moveto succeeded normally; rollback-safe by reverse moveto.
      - "recovered" — divergence detected and recovery performed (copyto + best-effort delete).
                      NOT cleanly reversible by moveto alone.
      - "skipped"   — no-op (src/dst out of sync root, identical paths, or no onedrive_sync configured).
      - "failed"    — non-recoverable error.
    """
    success: bool
    message: str
    mode: str


@dataclass(frozen=True)
class LsJsonResult:
    """Result of `rclone lsjson`. On success, `entries` is the parsed JSON list of dicts.
    On failure, `error` is the error message and `entries` is empty."""
    success: bool
    entries: List[dict] = field(default_factory=list)
    error: str = ""


@dataclass(frozen=True)
class DivergenceConfirmation:
    """Output of OneDriveSync._confirm_source_missing.

    `confirmed=True` ⇒ src is genuinely absent on remote AND dst_parent exists; recovery should proceed.
    `confirmed=False` ⇒ at least one probe failed (transient error, dst missing, or src present).
    """
    confirmed: bool
    reason: str


@dataclass(frozen=True)
class RecoveryMetadata:
    """Local-file metadata used to identify the OLD diverged remote filename."""
    title: Optional[str]
    track_number: Optional[int]
    duration_seconds: Optional[float]


@dataclass(frozen=True)
class CommitResult:
    """Result of FolderManager._commit_with_rollback and the 4 public rename/move methods.

    On success, `message` is the destination path string. On failure, it's an error description.
    """
    success: bool
    message: str
```

All dataclasses are `frozen=True` so they're immutable and hashable (helpful for testing equality with mocks).

**Why a new module instead of putting types in `models.py`**: `models.py` holds **domain models** (`TrackMetadata`, `AudioFile`, `ACRCloudResult`, `DiscogsRelease`, etc.). Result types are infrastructure. Keeping them separate avoids circular-import risk and matches the project's existing convention of single-responsibility module names.

### 2. `mode` enum semantics for `MoveResult`

| `mode` | When | `success` |
|---|---|---|
| `"skipped"` | Source/dst outside sync root, or `remote_src == remote_dst` (current early-returns in [onedrive_sync.py:65-79](../onedrive_sync.py#L65-L79)). Also: `_mirror_rename` returning when `onedrive_sync is None`. | `True` |
| `"moveto"` | rclone `moveto` succeeded normally — fully reversible by re-running `moveto` reversed. | `True` |
| `"recovered"` | Divergence detected and recovery executed (copyto + best-effort delete). **Not cleanly reversible** by `moveto` alone. | `True` |
| `"failed"` | Any non-recoverable error: timeout, missing binary, non-zero exit not matching divergence pattern, divergence detected but `dst_parent` missing, recovery itself failed. | `False` |

(We use string literals rather than an `Enum` to keep the wire format simple for tests/logs. Could be promoted to `enum.Enum` in a follow-up if mode-set grows.)

### 3. `OneDriveSync.moveto` migration

#### 3a. New signature

```python
# Top of onedrive_sync.py — module-level imports (NOT inside the class):
# from sync_results import (
#     RcloneResult, MoveResult, LsJsonResult, DivergenceConfirmation, RecoveryMetadata,
# )

def moveto(
    self,
    local_src: Path,
    local_dst: Path,
    dry_run: bool = False,
    *,
    allow_recovery: bool = True,
) -> MoveResult:
```

The internal early-returns ([onedrive_sync.py:65-79](../onedrive_sync.py#L65-L79)) become:
- `MoveResult(True, "skipped: source outside sync root", "skipped")`
- `MoveResult(True, "skipped: destination outside sync root", "skipped")`
- `MoveResult(True, "skipped: remote src and dst identical", "skipped")`

Success path: `MoveResult(True, f"renamed {remote_src} -> {remote_dst}", "moveto")`.
Failure paths (timeout, missing binary, generic non-zero exit): `MoveResult(False, msg, "failed")`.

#### 3b. Divergence-detection branch (new logic, after `subprocess.run` returns non-zero)

```python
if result.returncode != 0:
    stderr = (result.stderr or result.stdout).strip()
    if allow_recovery and self._looks_like_source_missing(result.returncode, stderr):
        confirmation = self._confirm_source_missing(local_src, local_dst)
        if confirmation.confirmed:
            return self._recover_diverged_rename(local_src, local_dst, dry_run)
        return MoveResult(
            success=False,
            message=f"rclone exit {result.returncode}: {stderr} ({confirmation.reason})",
            mode="failed",
        )
    return MoveResult(
        success=False,
        message=f"rclone exit {result.returncode}: {stderr}",
        mode="failed",
    )
```

#### 3c. `_looks_like_source_missing` (single bool — no dataclass)

```python
_DIVERGENCE_PATTERN = re.compile(
    r"(directory|item)\s*not\s*found|directoryNotFound|itemNotFound",
    re.IGNORECASE,
)

def _looks_like_source_missing(self, returncode: int, stderr: str) -> bool:
    # rclone returns exit 3 ("directory not found") for OneDrive Graph itemNotFound.
    # Also accept exit 1 if the stderr text is unambiguous (rclone has been inconsistent
    # across versions about which exit code OneDrive 404s map to).
    return returncode in (1, 3) and bool(self._DIVERGENCE_PATTERN.search(stderr))
```

(Add `re` to imports.)

#### 3d. `_confirm_source_missing` → `DivergenceConfirmation`

```python
def _confirm_source_missing(
    self, local_src: Path, local_dst: Path
) -> DivergenceConfirmation:
    src_parent_remote = self._to_remote(local_src.parent)
    dst_parent_remote = self._to_remote(local_dst.parent)

    # Probe 1: dst parent must exist (otherwise this is "wrong destination", not divergence).
    dst_listing = self._lsjson([dst_parent_remote, "--no-modtime", "--dirs-only"])
    if not dst_listing.success:
        return DivergenceConfirmation(
            confirmed=False,
            reason=f"dst parent listing failed: {dst_listing.error}",
        )

    # Probe 2: src parent listing — does it contain a file with the exact local_src.name?
    src_listing = self._lsjson([src_parent_remote, "--no-modtime", "--files-only"])
    if not src_listing.success:
        # If src_parent is also missing, the divergence is at folder level — out of scope.
        return DivergenceConfirmation(
            confirmed=False,
            reason=f"src parent listing failed: {src_listing.error}",
        )

    target_name_nfc = unicodedata.normalize("NFC", local_src.name)
    found = any(
        unicodedata.normalize("NFC", entry.get("Name", "")) == target_name_nfc
        for entry in src_listing.entries
    )
    if found:
        # rclone said "not found" but the listing shows it — likely a transient 5xx. Don't recover.
        return DivergenceConfirmation(
            confirmed=False,
            reason="src exists in listing — likely transient error",
        )
    return DivergenceConfirmation(
        confirmed=True,
        reason="confirmed: src absent from src_parent",
    )
```

#### 3e. `_lsjson` → `LsJsonResult`

```python
def _lsjson(self, args: List[str]) -> LsJsonResult:
    """Run `rclone lsjson <args>`. On success, .entries is the parsed list. On failure, .error is set."""
    cmd = [self.rclone_path, "lsjson", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=self.timeout
        )
    except subprocess.TimeoutExpired:
        return LsJsonResult(success=False, error=f"lsjson timed out after {self.timeout}s")
    except FileNotFoundError:
        return LsJsonResult(success=False, error=f"rclone binary not found at {self.rclone_path}")
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout).strip()
        return LsJsonResult(
            success=False, error=f"lsjson exit {result.returncode}: {stderr}"
        )
    try:
        return LsJsonResult(success=True, entries=json.loads(result.stdout or "[]"))
    except json.JSONDecodeError as e:
        return LsJsonResult(success=False, error=f"lsjson JSON parse failure: {e}")
```

(Add `json` to imports. `List` from `typing`.)

**Why no `--include`**: rclone `--include` uses glob semantics (`*`, `?`, `[…]` are wildcards). Listing the parent and comparing exact names in Python is safer.

### 4. Recovery: `_recover_diverged_rename` → `MoveResult`

```python
def _recover_diverged_rename(
    self, local_src: Path, local_dst: Path, dry_run: bool
) -> MoveResult:
    self.log(f"[onedrive] divergence detected: remote source missing for {local_src.name}")

    # Step 1: copyto to NEW remote path. We need to upload the bytes that ARE at local_src
    # to a remote dst that maps from local_dst. Use _copyto_explicit with explicit remote_dst.
    remote_dst = self._to_remote(local_dst)
    copy_result = self._copyto_explicit(local_src, remote_dst, dry_run=dry_run)
    if not copy_result.success:
        return MoveResult(
            success=False,
            message=f"recovery copyto failed: {copy_result.message}",
            mode="failed",
        )
    self.log(f"[onedrive] recovery: copyto {local_src.name} -> {remote_dst}")

    # Step 2: list candidates in src_parent_remote and identify the OLD diverged remote name.
    src_parent_remote = self._to_remote(local_src.parent)
    listing = self._lsjson([src_parent_remote, "--no-modtime", "--files-only"])
    if not listing.success:
        self.log(
            f"[onedrive] recovery: candidate listing failed ({listing.error}); "
            f"orphan may remain at {src_parent_remote}"
        )
        return MoveResult(
            success=True,
            message="recovered: copyto only — could not list to find old name",
            mode="recovered",
        )

    old_name = self._match_diverged_old_name(local_src, local_dst, listing.entries)
    if old_name is None:
        self.log(f"[onedrive] recovery: no unique match — orphan may remain at {src_parent_remote}")
        return MoveResult(
            success=True,
            message="recovered: copyto only — no unique old-name match",
            mode="recovered",
        )

    if dry_run:
        self.log(f"[onedrive] recovery: would deletefile {src_parent_remote}/{old_name} (dry-run)")
        return MoveResult(
            success=True,
            message=f"DRY-RUN: would recover via copyto + delete {old_name}",
            mode="recovered",
        )

    # Step 3: deletefile.
    delete_result = self._deletefile(f"{src_parent_remote}/{old_name}")
    if not delete_result.success:
        self.log(f"[onedrive] recovery: deletefile failed ({delete_result.message}); orphan may remain")
        return MoveResult(
            success=True,
            message=f"recovered: copyto OK; deletefile failed: {delete_result.message}",
            mode="recovered",
        )

    self.log(f"[onedrive] recovery: matched {old_name}; deleted")
    return MoveResult(
        success=True,
        message=f"recovered: copyto + deleted {old_name}",
        mode="recovered",
    )
```

**Flow note**: At the moment `_mirror_rename` runs in `rename_audio_file`/`move_file_to_disc_folder`, `commit_fn()` has not yet executed (see [folder_manager.py:525-532](../folder_manager.py#L525-L532) and [folder_manager.py:348-355](../folder_manager.py#L348-L355)). So `local_src` exists on disk — recovery can read it.

#### 4a. `_copyto_explicit` → `RcloneResult`

```python
def _copyto_explicit(
    self,
    local_path: Path,
    remote_dst: str,
    dry_run: bool,
    timeout: Optional[int] = None,
) -> RcloneResult:
    """Like copyto() but takes an explicit remote destination (not derived from local_path)."""
    cmd = [
        self.rclone_path,
        "copyto",
        str(local_path),
        remote_dst,
        "--checksum",
    ]
    if dry_run:
        cmd.append("--dry-run")
    effective_timeout = timeout if timeout is not None else self.timeout * 5
    self.log(f"    {'[DRY-RUN] ' if dry_run else ''}copyto {local_path} -> {remote_dst}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=effective_timeout
        )
    except subprocess.TimeoutExpired:
        return RcloneResult(False, f"rclone copyto timed out after {effective_timeout}s")
    except FileNotFoundError:
        return RcloneResult(False, f"rclone binary not found at {self.rclone_path}")
    if result.returncode == 0:
        return RcloneResult(True, f"pushed {local_path} -> {remote_dst}")
    stderr = (result.stderr or result.stdout).strip()
    return RcloneResult(False, f"rclone exit {result.returncode}: {stderr}")
```

#### 4b. Refactor existing `copyto` to delegate, also returning `RcloneResult`

```python
def copyto(
    self,
    local_path: Path,
    dry_run: bool = False,
    timeout: Optional[int] = None,
) -> RcloneResult:
    """Push a single local file up to its mapped OneDrive path via `rclone copyto`."""
    if not self.is_in_sync_root(local_path):
        return RcloneResult(True, "skipped: outside sync root")
    if not local_path.is_file():
        return RcloneResult(False, f"not a file: {local_path}")
    remote_dst = self._to_remote(local_path)
    return self._copyto_explicit(local_path, remote_dst, dry_run=dry_run, timeout=timeout)
```

Existing in/out of-sync-root checks at [onedrive_sync.py:113-130](../onedrive_sync.py#L113-L130) move into `copyto` (above) — they should NOT be in `_copyto_explicit` so recovery can hit `_copyto_explicit` directly with a remote_dst that maps from `local_dst` (which doesn't yet exist locally).

#### 4c. `_match_diverged_old_name` → `Optional[str]` (single value — no dataclass)

```python
def _match_diverged_old_name(
    self, local_src: Path, local_dst: Path, listing: List[dict]
) -> Optional[str]:
    meta = self._read_recovery_metadata(local_src)
    if not meta.title or meta.track_number is None:
        self.log(
            f"[onedrive] recovery: insufficient metadata to match "
            f"(title={meta.title!r}, track={meta.track_number})"
        )
        return None

    src_ext = local_src.suffix.lower()
    dst_name_nfc = unicodedata.normalize("NFC", local_dst.name)
    src_name_nfc = unicodedata.normalize("NFC", local_src.name)

    candidates = []
    for entry in listing:
        name = entry.get("Name", "")
        if not name:
            continue
        name_nfc = unicodedata.normalize("NFC", name)
        if Path(name_nfc).suffix.lower() != src_ext:
            continue
        if name_nfc == dst_name_nfc or name_nfc == src_name_nfc:
            continue  # Exclude the file we just copyto'd and (defensive) the canonical OLD name.
        candidates.append(name_nfc)

    title_norm = self._normalize_for_match(meta.title)
    if len(title_norm) < 3:
        self.log(f"[onedrive] recovery: title {meta.title!r} too short for safe matching")
        self.log(f"[onedrive] recovery: candidates in {local_src.parent}: {candidates}")
        return None

    track_re = re.compile(rf"(?<!\d)0*{meta.track_number}(?!\d)")

    matches = [
        name_nfc
        for name_nfc in candidates
        if title_norm in self._normalize_for_match(name_nfc)
        and track_re.search(name_nfc)
    ]

    if len(matches) == 1:
        self.log(f"[onedrive] recovery: matched {matches[0]} (unique)")
        return matches[0]

    if not matches:
        self.log(
            f"[onedrive] recovery: no candidates matched "
            f"title={meta.title!r} + track={meta.track_number}"
        )
        self.log(f"[onedrive] recovery: candidates in {local_src.parent}: {candidates}")
        return None

    # 2+ matches: duration tiebreaker would require fetching remote tags (expensive).
    # Skip delete on ambiguity.
    self.log(f"[onedrive] recovery: ambiguous — {len(matches)} candidates matched: {matches}")
    self.log(
        f"[onedrive] recovery: skipping delete to avoid wrong-file deletion; "
        f"user must clean up manually"
    )
    return None
```

#### 4d. `_read_recovery_metadata` → `RecoveryMetadata`

`mutagen` and `ID3Handler` are imported at the **top of `onedrive_sync.py`** (see Existing-code summary table — added there in Phase A step 2). No lazy/inline imports inside the method body.

```python
# At top of onedrive_sync.py (module-level):
# from mutagen import File as MutagenFile
# from id3_handler import ID3Handler

def _read_recovery_metadata(self, local_src: Path) -> RecoveryMetadata:
    """Return RecoveryMetadata(title, track_number, duration_seconds) from the local file."""
    try:
        meta = ID3Handler().read_tags(str(local_src))
    except Exception as e:
        self.log(f"[onedrive] recovery: read_tags failed for {local_src}: {e}")
        return RecoveryMetadata(title=None, track_number=None, duration_seconds=None)

    duration = None
    try:
        audio = MutagenFile(str(local_src))
        if audio is not None and getattr(audio, "info", None) is not None:
            duration = getattr(audio.info, "length", None)
    except Exception:
        duration = None

    return RecoveryMetadata(
        title=meta.title,
        track_number=meta.track_number,
        duration_seconds=duration,
    )
```

`ID3Handler.read_tags()` already handles the per-format dispatch and `TRCK` parsing via `_parse_track_disc` ([id3_handler.py:350-366](../id3_handler.py#L350-L366)). Duration is not in `TrackMetadata` so we fetch it via mutagen separately.

Note: duration is currently only used as a future tiebreaker hook; the current matcher logs it for diagnostics in the ambiguous case but does not act on it. Storing it on `RecoveryMetadata` keeps the API forward-compatible.

#### 4e. `_normalize_for_match(s)` (single str — no dataclass)

```python
@staticmethod
def _normalize_for_match(s: str) -> str:
    """NFC → casefold → strip non-alphanumeric → collapse whitespace."""
    s = unicodedata.normalize("NFC", s).casefold()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s
```

Worked example for the user's case:
- `title` = `"Stasis"` → normalized `"stasis"`.
- candidate remote name `"1.07 - Black Sun Empire - Stasis.mp3"` → normalized `"107 black sun empire stasismp3"` → contains `"stasis"` ✓.
- `track` = `7` → regex `(?<!\d)0*7(?!\d)` is searched against the **original NFC** name (not the normalized form). In `"1.07 - ..."` the `"07"` is preceded by `.` (not `\d`) → matches ✓. The `"107"` doesn't appear as a substring because of the `.`.
- Counter-case `"2007 - Stasis.mp3"` for track=7: `"7"` in `"2007"` is preceded by `0` (a digit) — lookbehind fails → no match ✓.

#### 4f. `_deletefile` → `RcloneResult`

```python
def _deletefile(self, remote_path: str) -> RcloneResult:
    cmd = [self.rclone_path, "deletefile", remote_path]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=self.timeout
        )
    except subprocess.TimeoutExpired:
        return RcloneResult(False, f"rclone deletefile timed out after {self.timeout}s")
    except FileNotFoundError:
        return RcloneResult(False, f"rclone binary not found at {self.rclone_path}")
    if result.returncode == 0:
        return RcloneResult(True, f"deleted {remote_path}")
    stderr = (result.stderr or result.stdout).strip()
    return RcloneResult(False, f"rclone exit {result.returncode}: {stderr}")
```

(Dry-run is handled in `_recover_diverged_rename` — it returns before calling `_deletefile`.)

### 5. `FolderManager` migration to dataclasses

#### 5a. `_mirror_rename` → `MoveResult`

```python
# Top of folder_manager.py — module-level imports (NOT inside the class):
# from sync_results import MoveResult, CommitResult

def _mirror_rename(
    self,
    local_src: Path,
    local_dst: Path,
    dry_run: bool,
    *,
    allow_recovery: bool = True,
) -> MoveResult:
    if self.onedrive_sync is None:
        return MoveResult(success=True, message="", mode="skipped")
    return self.onedrive_sync.moveto(
        local_src, local_dst, dry_run=dry_run, allow_recovery=allow_recovery
    )
```

The `allow_recovery` kwarg is the gate: file-level callers pass `True` (default), folder-level callers pass `False`. Recovery via `copyto` is meaningless for folders.

#### 5b. `_commit_with_rollback` → `CommitResult`

```python
def _commit_with_rollback(
    self,
    local_src: Path,
    local_dst: Path,
    commit_fn: Callable[[], None],
    *,
    mirror_result: MoveResult,
) -> CommitResult:
    """Run commit_fn() and roll back the remote rename on local-commit failure.

    `mirror_result` is the MoveResult from the forward _mirror_rename; its `mode` controls
    whether rollback is attempted (only "moveto" is rollback-safe).
    """
    try:
        commit_fn()
        return CommitResult(success=True, message=str(local_dst))
    except Exception as e:
        if mirror_result.mode == "recovered":
            if self.onedrive_sync is not None:
                self.onedrive_sync.log(
                    f"[onedrive] WARNING: local commit failed after recovered rename "
                    f"({local_src.name} -> {local_dst.name}); remote at NEW path, "
                    f"local at OLD path. Next bisync will reconcile by downloading the NEW name."
                )
            return CommitResult(
                success=False,
                message=f"{e} (remote already recovered to NEW name; not rolled back)",
            )
        rollback = self._mirror_rename(
            local_dst, local_src, dry_run=False, allow_recovery=False
        )
        if rollback.success:
            return CommitResult(success=False, message=str(e))
        return CommitResult(
            success=False, message=f"{e} (rollback also failed: {rollback.message})"
        )
```

The shape change from `mirror_mode: str` to `mirror_result: MoveResult` is intentional: passing the whole result keeps the API self-documenting (the caller doesn't have to extract `mode` separately) and makes future extensions (e.g. checking `mirror_result.message`) trivial.

#### 5c. The 4 public rename/move methods → `CommitResult`

Each currently returns `Tuple[bool, str]` and unpacks `_mirror_rename`'s old 2-tuple. Migrate:

| Line | Method | Current signature | New signature |
|---|---|---|---|
| [folder_manager.py:133-164](../folder_manager.py#L133-L164) | `normalize_disc_folder_name` | `-> Tuple[bool, str]` | `-> CommitResult` |
| [folder_manager.py:253-282](../folder_manager.py#L253-L282) | `rename_folder` | `-> Tuple[bool, str]` | `-> CommitResult` |
| [folder_manager.py:326-355](../folder_manager.py#L326-L355) | `move_file_to_disc_folder` | `-> Tuple[bool, str]` | `-> CommitResult` |
| [folder_manager.py:503-532](../folder_manager.py#L503-L532) | `rename_audio_file` | `-> Tuple[bool, str]` | `-> CommitResult` |

For each, the method body changes shape like this (taking `rename_audio_file` as the canonical example):

```python
def rename_audio_file(
    self, file_path: str, new_name: str, dry_run: bool = False
) -> CommitResult:
    current = Path(file_path)
    new_path = current.parent / new_name
    if new_path.exists() and new_path.resolve() != current.resolve():
        return CommitResult(success=False, message=f"Target exists: {new_path}")
    if current.name == new_name:
        return CommitResult(success=True, message="File already has correct name")

    mirror = self._mirror_rename(current, new_path, dry_run)  # MoveResult
    if not mirror.success:
        return CommitResult(success=False, message=f"Remote rename failed: {mirror.message}")

    if dry_run:
        return CommitResult(success=True, message=f"Would rename to: {new_name}")

    return self._commit_with_rollback(
        current, new_path, lambda: current.rename(new_path), mirror_result=mirror
    )
```

`normalize_disc_folder_name` and `rename_folder` (folder renames) call `_mirror_rename(..., allow_recovery=False)` and pass the same `mirror_result` to `_commit_with_rollback`. Since folder ops never produce `mode="recovered"`, the rollback branch is unaffected for them.

`move_file_to_disc_folder` and `rename_audio_file` call `_mirror_rename` with default `allow_recovery=True` and pass `mirror_result` through.

#### 5d. Rollback inside `_commit_with_rollback` — already handled

The internal `self._mirror_rename(local_dst, local_src, dry_run=False, allow_recovery=False)` call (Section 5b) now returns `MoveResult`; we read `.success` and `.message` directly.

### 6. `main.py` call-site migration

Five call sites consume `Tuple[bool, str]` from migrated methods. All change from tuple-unpack to attribute access.

| Line | Caller | Current | New |
|---|---|---|---|
| [main.py:193-206](../main.py#L193-L206) | `_process_folder` calls `normalize_disc_folder_name` | `success, result = self.folder_manager.normalize_disc_folder_name(...)` then `if success and result != folder_path:` | `result = self.folder_manager.normalize_disc_folder_name(...)` then `if result.success and result.message != folder_path:`. Replace later `result` references with `result.message` for the path string. |
| [main.py:736](../main.py#L736) | `_push_tag_writes_to_onedrive` calls `copyto` | `ok, msg = onedrive.copyto(...)` then `if not ok:` and `elif not msg.startswith("skipped"):` | `result = onedrive.copyto(...)` then `if not result.success:` (use `result.message` in error logs) and `elif not result.message.startswith("skipped"):` (still string-based — see Section 6a) |
| [main.py:792-803](../main.py#L792-L803) | `_handle_file_renames` calls `rename_audio_file` | `success, result = self.folder_manager.rename_audio_file(...)` then `if result == "File already has correct name":` | `commit = self.folder_manager.rename_audio_file(...)` then `if commit.success: ...; if commit.message == "File already has correct name":` |
| [main.py:830-837](../main.py#L830-L837) | `_handle_folder_rename` calls `reorganize_multi_disc_album` | `success, msg = ...reorganize_multi_disc_album(...)` | **Unchanged** — `reorganize_multi_disc_album` is out of scope. Still returns `Tuple[bool, str]`. |
| [main.py:848-855](../main.py#L848-L855) | `_handle_folder_rename` calls `rename_folder` | `success, msg = ...rename_folder(...)` | `commit = self.folder_manager.rename_folder(...)` then `if commit.success: ...` |

#### 6a. `_push_tag_writes_to_onedrive` — keep string-based skip detection

`copyto` still uses `result.message.startswith("skipped")` to suppress the duplicate `Pushed:` print. Could be migrated to a `mode`-style return on `RcloneResult`, but that would require adding a third field; keeping the simple `RcloneResult(success, message)` shape and the existing string check keeps the diff focused. **No further `copyto` change in this PR.**

(Follow-up option: extend `RcloneResult` with `skipped: bool = False` field, set `True` for skip cases. Out of scope here.)

### 7. Logging

`OneDriveSync.log` (`Callable[[str], None]`, [onedrive_sync.py:18](../onedrive_sync.py#L18)) is the sink for all recovery-related logs. Emit at minimum:
- Detection: `"[onedrive] divergence detected: remote source missing for <name>"`
- Each recovery step: `"[onedrive] recovery: copyto …"`, `"[onedrive] recovery: candidates in <dir>: [<files>]"`, `"[onedrive] recovery: matched <name>; deleted"`, `"[onedrive] recovery: no unique match — orphan may remain at <dir>"`, `"[onedrive] recovery: deletefile failed (<err>); orphan may remain"`.
- Rollback refusal in `_commit_with_rollback`: `"[onedrive] WARNING: local commit failed after recovered rename — remote at NEW path, local at OLD path. Next bisync will reconcile."`

`FolderManager` has no logger today and we don't add one — the recovery-rollback warning is the only `FolderManager`-side log and it goes through `self.onedrive_sync.log(...)` (only fires when `onedrive_sync` is not None, which is a precondition for recovery anyway).

## Parallelization plan

**Phase A — strictly sequential (foundation):**
1. Create [sync_results.py](../sync_results.py) with all six dataclasses. (Trivial; foundation for everything.)
2. Migrate `OneDriveSync.moveto` and `copyto` to dataclass returns. Add `_lsjson`, `_copyto_explicit`, `_deletefile` helpers (all dataclass returns). Refactor `copyto` to delegate to `_copyto_explicit`.
3. Add divergence-detection logic to `OneDriveSync`: `_DIVERGENCE_PATTERN`, `_looks_like_source_missing`, `_confirm_source_missing`, `_recover_diverged_rename`, `_match_diverged_old_name`, `_normalize_for_match`, `_read_recovery_metadata`.
4. Migrate `_mirror_rename` and `_commit_with_rollback` to dataclass returns; thread `mirror_result` through.
5. Migrate the 4 public rename/move methods in `folder_manager.py` to return `CommitResult`.
6. Update `main.py` call sites (5 sites) to attribute access.

**Phase B — can run in parallel after Phase A:**
- B1. Update [tests/test_onedrive_sync.py](../tests/test_onedrive_sync.py) — see test inventory below.
- B2. Update [tests/test_folder_manager.py](../tests/test_folder_manager.py) — any tests asserting on `_mirror_rename` or the 4 public methods' return tuples migrate to attribute access.
- B3. Add new unit tests for: `_looks_like_source_missing`, `_confirm_source_missing`, `_normalize_for_match`, `_match_diverged_old_name`, `_recover_diverged_rename`, `_lsjson`, `_copyto_explicit`, `_deletefile` (all with mocked subprocess).
- B4. Add a small unit test in `tests/test_sync_results.py` (new) that constructs each dataclass and asserts default values — protects against accidental signature drift.
- B5. Manual verification (Section 9).

B1 / B2 / B3 / B4 are independent and can be authored in parallel.

## Test inventory (callers that will break and need updating)

### `tests/test_onedrive_sync.py` — 7 `sync.moveto(...)` call sites + any `copyto` sites

| Line | Test purpose | Current unpack | New shape | New assertion |
|---|---|---|---|---|
| [82](../tests/test_onedrive_sync.py#L82) | outside sync root | `ok, msg = sync.moveto(...)` | `result = sync.moveto(...)` | `result.success is True; result.mode == "skipped"; "outside sync root" in result.message` |
| [89](../tests/test_onedrive_sync.py#L89) | identical src/dst | `ok, msg = ...` | `result = ...` | `result.success is True; result.mode == "skipped"; "identical" in result.message` |
| [97](../tests/test_onedrive_sync.py#L97) | successful rename | `ok, msg = ...` | `result = ...` | `result.success is True; result.mode == "moveto"; run.call_count == 1` |
| [111](../tests/test_onedrive_sync.py#L111) | dry-run flag | no unpack (just call) | unchanged (no unpack) | n/a |
| [118](../tests/test_onedrive_sync.py#L118) | nonzero exit (`exit 3 ... directory not found`) | `ok, msg = ...` | `result = ...` | **Must mock `_lsjson` too** — the new code will run real `subprocess.run` on confirmation probes. Recommended: `with patch.object(sync, "_confirm_source_missing", return_value=DivergenceConfirmation(False, "test stub"))`. Then assert `result.success is False; result.mode == "failed"; "exit 3" in result.message`. |
| [126](../tests/test_onedrive_sync.py#L126) | timeout | `ok, msg = ...` | `result = ...` | `result.success is False; result.mode == "failed"; "timed out" in result.message` |
| [133](../tests/test_onedrive_sync.py#L133) | missing binary | `ok, msg = ...` | `result = ...` | `result.success is False; result.mode == "failed"; "not found" in result.message` |

Any test that calls `sync.copyto(...)` and unpacks `ok, msg = ...` — same migration: `result = sync.copyto(...); result.success; result.message`.

### `tests/test_folder_manager.py`

Any test that calls `normalize_disc_folder_name`, `rename_folder`, `move_file_to_disc_folder`, or `rename_audio_file` and unpacks `success, msg = ...` migrates to attribute access. Search for those method names + `success,` to enumerate before editing.

Mocked `OneDriveSync.moveto` return values must be updated from `(True, "...")` to `MoveResult(True, "...", "moveto")` (or appropriate mode).

## Dropped: stale `af.file_path` after disc-folder normalization

On closer reading the bug doesn't manifest in current code:

- [`_process_folder`](../main.py#L165) discovers `audio_files` non-recursively at the album root ([main.py:168](../main.py#L168)) — these files live in the parent dir, not inside any disc subfolder, so renaming `CD 1` → `CD1` ([main.py:193](../main.py#L193)) doesn't shift their paths.
- Per-disc files are freshly re-discovered AFTER disc-folder normalization at [main.py:210](../main.py#L210), so they carry current paths.
- The `af.file_path` update inside `_handle_file_renames` ([main.py:799](../main.py#L799), introduced in commit `2e24a70`) keeps in-disc renames current.
- `reorganize_multi_disc_album` ([folder_manager.py:357](../folder_manager.py#L357)) computes the destination via `new_base / generate_disc_folder_name(disc_num)` from scratch — does not depend on existing disc-folder names.

Separate latent bug — `create_multi_disc_structure` ([folder_manager.py:284](../folder_manager.py#L284)) creates the new base + CD subfolders only on local disk via `mkdir`, so the subsequent `move_file_to_disc_folder` → `rclone moveto` would fail because the dst parent doesn't exist on OneDrive. Out of scope here. **Recommend a separate ticket**: have `create_multi_disc_structure` also `rclone mkdir <remote_dst>` (or rely on rclone moveto auto-creating parents — verify experimentally).

## Verification

1. **Unit-level dry-run**: pick a known diverged file (the user's `Stasis` example). Run id3_manager against just that album with `--dry-run` (after the change). Expect logs in this order: `divergence detected` → `[DRY-RUN] copyto ... -> onedrive:.../CD 1/<NEW name>` → `candidates in <dir>: [...]` → `would deletefile onedrive:.../CD 1/1.07 - Black Sun Empire - Stasis.mp3 (dry-run)`. No actual rclone writes.
2. **Live recovery on one album**: drop `--dry-run`. After: `rclone lsf "onedrive:.../CD 1/"` should show the NEW name, no `1.07 - ...` file. Local file at NEW name. Run `rclone bisync` (via [rclone_sync.py](../../rclone_sync.py)) afterward — expect no `quickxor differ` warnings and no delete+add.
3. **Negative case 1 (no divergence)**: a file whose remote name matches local. Confirm fast-path: rclone moveto succeeds on first try, no recovery code runs, returned `MoveResult.mode == "moveto"`.
4. **Negative case 2 (dst parent missing)**: simulate by attempting a moveto into a non-existent remote subfolder. `_confirm_source_missing` returns `DivergenceConfirmation(confirmed=False, reason="dst parent listing failed: ...")`, the function returns `MoveResult(success=False, message="...", mode="failed")`, recovery does NOT execute.
5. **Folder rename with divergent remote**: rename a folder where the remote folder name differs. `allow_recovery=False` is passed by `normalize_disc_folder_name`/`rename_folder`, so recovery is skipped. Expect `MoveResult.mode == "failed"`. Confirm no copyto attempted.
6. **Ambiguous match**: contrive a `CD 1/` with two remote candidates that both pass the title+track filter. Confirm: copyto succeeds, both candidates logged, delete is skipped, function returns `MoveResult(success=True, mode="recovered", message="recovered: copyto only — no unique old-name match")`.
7. **No metadata fallback**: rename a file whose tags are missing/corrupted. Confirm: `_match_diverged_old_name` logs "insufficient metadata" and returns `None`; outer function returns `MoveResult(success=True, mode="recovered", ...)` with copyto-only message; no delete attempted.
8. **Rollback after recovery**: simulate by patching `commit_fn` to raise after a recovered rename. Confirm: WARNING log fires; `_mirror_rename` is NOT called for rollback (verify via mock); `_commit_with_rollback` returns `CommitResult(success=False, message="... not rolled back")`.
9. **Existing tests**: `pytest tests/` — confirm no regressions after updating the 7 unpack sites in `test_onedrive_sync.py` and any `test_folder_manager.py` sites that touch `_mirror_rename`, `_commit_with_rollback`, or the 4 public rename/move methods.
10. **New unit tests** (Phase B3): each new helper has a focused test using `unittest.mock.patch("subprocess.run")`. Cover: divergence pattern matching (positive + negative cases), confirmation probe (src present, src absent, dst missing, lsjson timeout/parse-error), match scoring (unique, ambiguous, no match, short title, track edge cases like `01` vs `2001`), normalize_for_match unicode round-trips, dataclass round-trip equality.
