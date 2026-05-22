# Fix: duplicate track numbers when a file is misidentified

> All paths below are relative to `gargascripts/python/id3_manager/`.
> Line numbers verified against the working tree on 2026-05-22.
> Main class is **`ID3Processor`** ([main.py:32](../gargascripts/python/id3_manager/main.py#L32)).

## Context
On the David Bowie *Heathen* album, the tool proposes renaming the track-4 file
`Slow Burn.mp3` to `David Bowie - Heathen - 01 - Sunday.mp3`, colliding with the
real track-1 file and producing two files numbered `01`.

(The rename format is `{artist} - {album} - {NN} - {title}{ext}` from
`generate_expected_filename()` [utils.py:20](../gargascripts/python/id3_manager/utils.py#L20)
and the identical `FolderManager.generate_filename()`
[folder_manager.py:491](../gargascripts/python/id3_manager/folder_manager.py#L491);
the track number is zero-padded via `f"{track_number:02d}"`. So both files would
render `... - 01 - <title>.mp3`.)

**Root cause.** ACRCloud is enabled, so with `--force` every file is
re-fingerprinted. ACRCloud misidentified the *Slow Burn* audio as *Sunday*
(another track on the same album). In `_match_track_from_cached_release()`
([main.py:436](../gargascripts/python/id3_manager/main.py#L436)) the ACR title is
matched against the cached release's tracklist first; `proposed` is built from the
matched track at [main.py:464-475](../gargascripts/python/id3_manager/main.py#L464-L475).
Because "Sunday" matched a valid track (#1), `proposed` got
`title="Sunday", track_number=1`, `prompt_missing_fields()` had nothing missing to
backfill ([main.py:478](../gargascripts/python/id3_manager/main.py#L478)), and the
tags were assigned at [main.py:483](../gargascripts/python/id3_manager/main.py#L483).
There is **no cross-file validation** in `_process_files()` — two files mapping to
the same `(disc, track#)` is never detected, so a single bad fingerprint silently
creates the duplicate.

The other 4 renames in the run are legitimate (capitalization/punctuation fixes)
and are unaffected.

## Approach
Two **independent** layers (can be implemented in parallel — see Work breakdown),
both confirmed with the user:
1. **Collision detection** (safety net) — catches the duplicate-number outcome
   regardless of cause. On collision: skip the conflicting files, apply the rest.
2. **Force-override guard** — flags discrepancies between already-correct existing
   tags and a fresh `--force` result at the source, before they become collisions.

## Resolved design decisions
- **What `_process_files()` actually receives.** Both call sites pass
  `files_to_process`, which under `--force` is the *entire* `audio_files` list of
  the folder/disc, and otherwise only `files_needing_work`:
  - `_process_folder()` single-disc branch: builds `files_to_process` at
    [main.py:224](../gargascripts/python/id3_manager/main.py#L224) and calls
    `_process_files()` at [main.py:225](../gargascripts/python/id3_manager/main.py#L225).
  - `_process_disc()`: same pattern at [main.py:244](../gargascripts/python/id3_manager/main.py#L244)
    / [main.py:253](../gargascripts/python/id3_manager/main.py#L253).
  - **Consequence:** In the Heathen `--force` case, `_process_files()` sees *all*
    sibling files, so any two-file collision is visible. **Known limitation
    (document, do not fix here):** without `--force`, only `files_needing_work`
    is passed, so a collision between a processed file and an unprocessed
    complete-tags sibling would not be detected. ACR misidentification only
    happens under `--force`, so this gap does not affect the target bug.
  - `process()` dispatch ([main.py:74-94](../gargascripts/python/id3_manager/main.py#L74-L94)):
    file → `_process_single_file()`; dir + `--recursive` → `_process_recursive()`;
    dir → `_process_folder()`, which detects multi-disc and delegates to
    `_process_disc()` per disc.
- **`needs_rename` reads `current_tags` only** ([models.py:157-159](../gargascripts/python/id3_manager/models.py#L157-L159)
  → `file_needs_rename(self.file_path, self.current_tags)`). Therefore setting
  `af.proposed_tags = None` does **not** stop a rename — the file would still be
  picked up by `files_only_needing_rename` and renamed from its (bad) current tags
  by `_handle_file_renames()`, which uses `af.proposed_tags or af.current_tags`
  ([main.py:769](../gargascripts/python/id3_manager/main.py#L769)). The skipped
  files **must** be excluded from the rename list explicitly (see §1 snippet).
- **Collision-prompt return type: plain strings `"skip"`/`"apply"`/`"quit"`.**
  This mirrors the existing string-returning handlers
  (`handle_no_acr_match`, `handle_no_discogs_match`, `handle_track_not_in_release`).
  Do **not** reuse `ConfirmAction` ([models.py:17-25](../gargascripts/python/id3_manager/models.py#L17-L25))
  — it carries unrelated members (REVIEW/EDIT/ALBUM_EDIT).
- **Force-guard return values (corrected from the original draft).** A bare
  `return False` / `return None` is wrong:
  - **Cached path** (`_match_track_from_cached_release`, returns `bool`): the caller
    at [main.py:405-407](../gargascripts/python/id3_manager/main.py#L405-L407) treats
    `False` as "track not in this release" and then prompts
    `handle_track_not_in_release()` — a confusing **second** prompt. Instead, on a
    declined override, **do not set `af.proposed_tags`** and **`return True`**. The
    caller then `return folder_release` with no further prompt; `proposed_tags`
    stays `None`, so `has_actual_changes` is `False` and the existing tags are kept.
  - **Search path** (`_search_and_match_discogs`, returns `Optional[DiscogsRelease]`):
    on a declined override, **do not set `af.proposed_tags`** but still
    **`return release`** (not `None`) so the valid release is still cached for
    subsequent files in the folder. Callers at
    [main.py:416](../gargascripts/python/id3_manager/main.py#L416) /
    [main.py:425](../gargascripts/python/id3_manager/main.py#L425) handle a release
    return cleanly; `proposed_tags` stays `None` → existing tags kept.

## Changes

### 1. Collision detection  *(Work stream A — independent of stream B)*

**`models.py` — new named types** so the collision map never appears as a bare
`Dict[Tuple[int, int], ...]` (which doesn't say what the two ints are). Define
next to the other dataclasses. models.py currently imports
`from typing import Optional, List` ([models.py:5](../gargascripts/python/id3_manager/models.py#L5))
— add `Dict, NamedTuple`:
```python
class DiscTrack(NamedTuple):
    """A (disc, track) position; the key used to detect rename collisions."""
    disc: int
    track: int


# A bucket of files that resolve to the same DiscTrack position.
CollisionMap = Dict[DiscTrack, List["AudioFile"]]
```
- `AudioFile` is defined later in the same module, so the alias uses a forward
  reference (string). Defining `CollisionMap` *after* `AudioFile` instead would
  let it be unquoted — either is fine; pick whichever reads cleaner in context.
- `DiscTrack(disc=..., track=...)` is self-documenting at every call site and at
  the prompt (`f"Disc {key.disc}, track {key.track}"`).

**`main.py` — new `_detect_track_collisions(self, audio_files)`** placed
immediately before `_backfill_disc_info()` (~[main.py:749](../gargascripts/python/id3_manager/main.py#L749)):
```python
def _detect_track_collisions(self, audio_files: List[AudioFile]) -> CollisionMap:
    """Group files that would share the same (disc, track) number.

    Uses effective tags (proposed_tags or current_tags). Files with no
    track_number are excluded. Returns only keys with >1 file.
    """
    buckets: Dict[DiscTrack, List[AudioFile]] = defaultdict(list)
    for af in audio_files:
        tags = af.proposed_tags or af.current_tags          # idiom: main.py:752
        if tags.track_number is None:
            continue
        disc = tags.disc_number if tags.disc_number is not None else 1
        buckets[DiscTrack(disc=disc, track=tags.track_number)].append(af)
    return {key: files for key, files in buckets.items() if len(files) > 1}
```
- **Imports to add** (verified missing): main.py currently has
  `from typing import List, Optional` ([main.py:15](../gargascripts/python/id3_manager/main.py#L15))
  and no `collections` import. Add `Dict, Set` to the typing line, import the new
  names from models (`DiscTrack, CollisionMap`), and add
  `from collections import defaultdict`. (`Tuple` is no longer needed in main.py
  — the named `DiscTrack` replaces it. `sys` is already imported at
  [main.py:11](../gargascripts/python/id3_manager/main.py#L11), so `sys.exit(0)`
  in the wiring works; `Path` is imported at
  [main.py:14](../gargascripts/python/id3_manager/main.py#L14).)
- Pure read logic; no I/O, no prompts → trivially `--dry-run` safe and unit-testable.

**`main.py` `_process_files()`** — **replace** the `files_with_changes`
computation at [main.py:270](../gargascripts/python/id3_manager/main.py#L270) with
the block below, which relocates that computation to *after* the collision loop
(so it reflects any edits/skips). The line is already after `_backfill_disc_info()`
at [main.py:267](../gargascripts/python/id3_manager/main.py#L267), so disc numbers
are populated. The existing block uses `match result:` against
`ConfirmAction` ([main.py:277-285](../gargascripts/python/id3_manager/main.py#L277-L285));
the collision block runs *before* that confirmation. It is a **loop**: after a
manual edit, collisions are re-detected and the user is re-prompted, so an edit
that fails to clear the collision (or introduces a new one) cannot slip through:
```python
conflicting: Set[AudioFile] = set()
collisions: CollisionMap = self._detect_track_collisions(audio_files)
while collisions:
    action: str = self.prompts.confirm_collision_resolution(collisions)
    if action == "quit":
        sys.exit(0)
    if action == "edit":
        # Scoped editor: lets the user fix fields on the conflicting files,
        # seeding proposed_tags from current_tags where needed. Reuses
        # _edit_track_fields. Then loop back to re-detect.
        self.prompts.edit_collision_files(collisions)
        collisions = self._detect_track_collisions(audio_files)
        continue
    if action == "skip":
        conflicting = {af for grp in collisions.values() for af in grp}
        for af in conflicting:
            af.proposed_tags = None          # cancels apply for these files
        self.stats.files_skipped += len(conflicting)
    # action == "apply" -> keep tags as-is
    break

files_with_changes = [af for af in audio_files if af.has_actual_changes]
```
(`files_with_changes` is computed *after* the loop so it reflects any edits,
skips, or applies. `conflicting` stays empty unless the user chose `skip`.)
Then update the rename-only filter at
[main.py:289-292](../gargascripts/python/id3_manager/main.py#L289-L292) to also
exclude the skipped files (since `needs_rename` reads `current_tags` and would
otherwise rename them from bad tags):
```python
files_only_needing_rename = [
    af for af in audio_files
    if not af.has_actual_changes and af.needs_rename and af not in conflicting
]
```
(`conflicting` is initialised to an empty set above so the comprehension is valid
when there are no collisions.)

`_process_disc()` delegates to `_process_files()`
([main.py:253](../gargascripts/python/id3_manager/main.py#L253)), so multi-disc is
covered automatically and collisions are scoped per disc. The single-file path
(`_process_single_file()` [main.py:296-327](../gargascripts/python/id3_manager/main.py#L296-L327))
operates on one `AudioFile` and can't self-collide — no change.

**`interactive.py` — new `confirm_collision_resolution(self, collisions) -> str`**
placed near `confirm_file_renames()` ([interactive.py:647](../gargascripts/python/id3_manager/interactive.py#L647)),
reusing `self._c(color, text)` ([interactive.py:43](../gargascripts/python/id3_manager/interactive.py#L43))
and `self._prompt_choice(prompt, valid_choices, default)`
([interactive.py:47](../gargascripts/python/id3_manager/interactive.py#L47)):
```python
def confirm_collision_resolution(self, collisions: CollisionMap) -> str:
    """Prompt for how to resolve duplicate (disc, track#) assignments.

    Returns "skip" (cancel conflicting files), "apply" (keep anyway),
    "edit" (manually fix fields on the conflicting files), or "quit".
    """
    print(f"\n{self._c('red', 'Track-number collisions detected:')}")
    for key, files in sorted(collisions.items()):
        print(self._c('yellow', f"  Disc {key.disc}, track {key.track}:"))
        for af in files:
            tags = af.proposed_tags or af.current_tags
            print(f"    {Path(af.file_path).name}  ->  {tags.title}")

    if self.auto_yes:
        # NEVER auto-apply a collision (contrast confirm_tag_changes which
        # auto-applies under auto_yes). Manual edit is impossible under --yes
        # (no one to type values). Conservative default: skip.
        print(self._c('red', '[AUTO] Collision detected - skipping conflicting files.'))
        return "skip"

    return self._prompt_choice(
        "Resolve collisions? [s]kip conflicting / [e]dit fields / [a]pply anyway / [q]uit:",
        {"s": "skip", "skip": "skip",
         "e": "edit", "edit": "edit",
         "a": "apply", "apply": "apply",
         "q": "quit", "quit": "quit"},
        default="skip",
    )
```
- `Path` is already imported in interactive.py (used by `confirm_file_renames`).

**`interactive.py` — new `edit_collision_files(self, collisions) -> None`**
(scoped manual editor, placed next to `_handle_edit_track`
[interactive.py:258](../gargascripts/python/id3_manager/interactive.py#L258)).
Unlike `_handle_edit_track` (which lists *all* files with proposed tags), this
lists only the files participating in collisions, seeds `proposed_tags` from a
copy of `current_tags` where it is `None` (so the existing `_edit_track_fields`
editor — which early-returns on `proposed_tags is None`
[interactive.py:355-357](../gargascripts/python/id3_manager/interactive.py#L355-L357)
— can run on the "innocent" sibling too), then delegates to `_edit_track_fields`:
```python
def edit_collision_files(self, collisions: CollisionMap) -> None:
    """Let the user manually edit fields on the colliding files.

    Seeds proposed_tags from current_tags where missing so _edit_track_fields
    can run. Caller re-detects collisions afterwards and re-prompts.
    """
    # Flatten + de-dupe the conflicting files (a file may appear once per group)
    files: List[AudioFile] = list({af for files in collisions.values() for af in files})

    print(f"\n{self._c('cyan', 'Select a file to edit:')}")
    for i, af in enumerate(files, 1):
        tags = af.proposed_tags or af.current_tags
        print(f"  [{i}] {Path(af.file_path).name}  ->  "
              f"track {tags.track_number}, {tags.title}")
    print(f"  [c] Cancel (back to collision menu)")

    while True:
        choice = input(
            f"\n{self._c('bold', f'Select file [1-{len(files)}/c]: ')} "
        ).strip().lower()
        if choice == "c":
            return
        try:
            idx = int(choice)
            if 1 <= idx <= len(files):
                af = files[idx - 1]
                if af.proposed_tags is None:
                    af.proposed_tags = dataclasses.replace(af.current_tags)
                self._edit_track_fields(af)
                return
        except ValueError:
            pass
        print(self._c("red", "Invalid selection. Try again."))
```
- **Import to add:** `import dataclasses` at the top of interactive.py (verify it
  is not already imported; `dataclasses.replace` gives a shallow copy of the flat
  `TrackMetadata` dataclass, which is sufficient).
- Returns after one edit; the caller's `while collisions:` loop re-detects and
  re-prompts, so the user can edit several files across iterations.
- The `auto_yes` → `"skip"` branch is the **key guarantee**: a bad fingerprint can
  never silently produce a duplicate under `--yes`.

### 2. Force-override guard  *(Work stream B — independent of stream A)*

**`interactive.py` — new `confirm_force_override(self, filename, current, proposed) -> bool`**
placed near the other confirm/handle methods (same style; under `auto_yes` return
`False` = keep existing tags, the conservative choice):
```python
def confirm_force_override(
    self, filename: str, current: TrackMetadata, proposed: TrackMetadata
) -> bool:
    """Ask whether a --force result should overwrite already-complete tags.

    Returns True to accept the new (proposed) tags, False to keep existing.
    """
    print(f"\n{self._c('yellow', f'--force changes already-complete tags for {filename}:')}")
    print(f"  track#:  {current.track_number}  ->  {proposed.track_number}")
    print(f"  title:   {current.title}  ->  {proposed.title}")

    if self.auto_yes:
        print(self._c('red', '[AUTO] Keeping existing tags (force override not auto-applied).'))
        return False

    return self._prompt_choice(
        f"Override existing tags for {filename}? [y/N]:",
        {"y": True, "yes": True, "n": False, "no": False},
        default=False,
    )
```

**`main.py` cached path** — in `_match_track_from_cached_release()`, replace the
assignment block at [main.py:482-484](../gargascripts/python/id3_manager/main.py#L482-L484):
```python
if proposed:
    if self.args.force and af.current_tags.is_complete():
        cur = af.current_tags
        if proposed.track_number != cur.track_number or (
            proposed.title and cur.title
            and proposed.title.lower() != cur.title.lower()
        ):
            if not self.prompts.confirm_force_override(
                Path(af.file_path).name, cur, proposed
            ):
                return True          # keep existing tags, no second prompt
    af.proposed_tags = proposed
    return True
```
(Returns `True` without setting `proposed_tags` on decline — see Resolved design
decisions for why `return False` is wrong here.)

**`main.py` search path** — in `_search_and_match_discogs()`, insert before the
assignment at [main.py:693](../gargascripts/python/id3_manager/main.py#L693)
(after the `if proposed is None:` skip block at
[main.py:688-691](../gargascripts/python/id3_manager/main.py#L688-L691)):
```python
if self.args.force and af.current_tags.is_complete():
    cur = af.current_tags
    if proposed.track_number != cur.track_number or (
        proposed.title and cur.title
        and proposed.title.lower() != cur.title.lower()
    ):
        if not self.prompts.confirm_force_override(
            Path(af.file_path).name, cur, proposed
        ):
            return release          # cache the release, keep existing tags

af.proposed_tags = proposed
return release
```
(Returns `release` (not `None`) on decline so the valid release is still cached
for later files — see Resolved design decisions.)

`is_complete()` ([models.py:41-46](../gargascripts/python/id3_manager/models.py#L41-L46))
defaults `is_multi_disc=False`, so the gate requires `title`, `artist`,
`track_number` — only already-trusted files trigger the guard, limiting prompt
noise. The case-insensitive title compare means pure capitalization fixes do **not**
prompt (see Edge cases for the punctuation caveat).

## Critical files
- [models.py](../gargascripts/python/id3_manager/models.py) — **new** `DiscTrack`
  (`NamedTuple`) and `CollisionMap` (`Dict[DiscTrack, List[AudioFile]]`) type alias;
  add `Dict, NamedTuple` to the `typing` import (L5). Reuse
  `TrackMetadata.is_complete()` (L41), `AudioFile.has_actual_changes` (L135),
  `AudioFile.needs_rename` (L157), `ProcessingStats.files_skipped` (L194).
- [main.py](../gargascripts/python/id3_manager/main.py) — `_detect_track_collisions`
  (new, ~L749, returns `CollisionMap`), `_process_files` wiring loop (L270/L289),
  force guard in `_match_track_from_cached_release` (L482) and
  `_search_and_match_discogs` (L693). Add `Dict, Set` to the `typing` import (L15),
  import `DiscTrack, CollisionMap` from models, and add
  `from collections import defaultdict`. (`Tuple` not needed — `DiscTrack` replaces it.)
- [interactive.py](../gargascripts/python/id3_manager/interactive.py) — new
  prompts: `confirm_collision_resolution` (str, now incl. `"edit"`) and
  `confirm_force_override` (bool) near `confirm_file_renames` (L647), plus
  `edit_collision_files` (scoped manual editor) near `_handle_edit_track` (L258),
  reusing `_edit_track_fields` (L353); reuse `_c` (L43), `_prompt_choice` (L47),
  `auto_yes`. Add `import dataclasses` and import `CollisionMap` from models.
- [utils.py](../gargascripts/python/id3_manager/utils.py) /
  [folder_manager.py](../gargascripts/python/id3_manager/folder_manager.py) —
  read-only reference for the rename filename format (no change).

## Work breakdown (parallelism)
- **Stream A — Collision detection** (independent): `_detect_track_collisions` +
  `_process_files` wiring loop (main.py) and `confirm_collision_resolution` +
  `edit_collision_files` (interactive.py, the latter reusing `_edit_track_fields`).
- **Stream B — Force-override guard** (independent): `confirm_force_override`
  (interactive.py) + two guard insertions (main.py).
- Streams A and B touch the same two files but **disjoint regions**
  (A: L270-292 & ~L749; B: L482 & L693), so they can be developed in parallel and
  merged without conflict.
- **Stream C — Tests** (depends on A and B): see Verification §5. Also add the two
  new prompt methods to the `mock_prompts` fixture (see below) — required before
  A's wiring is exercised by any existing `_process_files` test.

## Edge cases
- **Single-disc (the Bowie case):** both files have `disc_number=None` → bucketed
  as disc `1` by the `disc if not None else 1` rule.
- **Multi-disc:** same track# on different discs must NOT collide — the key
  includes disc, and `_backfill_disc_info()` (run before detection) populates disc
  numbers from folder structure.
- **`track_number is None`:** excluded from detection (cannot form a numbered
  collision).
- **`--yes`:** collisions are skipped, not applied (manual edit is unavailable —
  no one to type values); force overrides are declined (existing tags kept).
- **Manual edit re-detect loop:** after an edit the `while collisions:` loop
  re-runs `_detect_track_collisions`. If the edit clears the collision the loop
  exits and processing continues; if a collision remains (or the edit created a
  new one), the user is re-prompted. Editing the "innocent" sibling (which may
  have `proposed_tags=None`) is supported by seeding `proposed_tags` from a copy
  of `current_tags` first; if the user changes nothing, `has_actual_changes` stays
  `False` so nothing is written.
- **`--dry-run`:** `_detect_track_collisions` is pure read logic; apply/rename
  already branch on `self.args.dry_run`
  ([main.py:791](../gargascripts/python/id3_manager/main.py#L791) in
  `_handle_file_renames`).
- **Without `--force`:** collision detection only sees `files_needing_work`
  (documented limitation — does not affect the target bug, which is force-only).
- **Force-guard prompt noise:** capitalization-only title changes do **not**
  prompt (case-insensitive compare); a **punctuation-only** title change (e.g.
  `Slow Burn` → `Slow Burn.`) on an otherwise-matching track# **will** prompt.
  This is acceptable (user can accept) and was accepted as part of "flag
  discrepancies."

## Verification (use `.venv`, all non-destructive via `--dry-run`)
> Run from `gargascripts/python/id3_manager/` with its `.venv` active. Tests:
> `pytest` (config in `pyproject.toml`, `testpaths = ["tests"]`).

1. **Reproduce on Heathen:**
   `./main.py --recursive --force --dry-run '/Volumes/data_2/onedrive/Music' --start-at '/Volumes/data_2/onedrive/Music/Bowie, David/2002 - Heathen/'`
   — confirm the collision report fires and there is no
   `[DRY RUN] Would rename: Slow Burn.mp3 -> David Bowie - Heathen - 01 - Sunday.mp3`.
   (Discogs release: https://www.discogs.com/release/10291300)
2. **Re-run with `--yes` added** — confirm collisions are skipped, not applied
   (the `auto_yes` branch returns `"skip"`).
3. **A known multi-disc album with `--dry-run`** — confirm no false positive on a
   track# shared across discs.
4. **A clean single-disc album with `--dry-run`** — confirm zero collisions, normal
   proposals flow, and the force guard does not prompt when nothing changes.
5. **Add `tests/test_main.py` unit tests** (instantiate
   `ID3Processor(mock_config, mock_args, mock_prompts)` — fixtures already exist in
   test_main.py; construct `AudioFile`/`TrackMetadata` per `conftest.py`):
   - `_detect_track_collisions`:
     - single-disc duplicate (two files, `disc_number=None`, same `track_number`)
       → one key `DiscTrack(disc=1, track=N)` with both files.
     - multi-disc same-track (`disc_number=1` vs `2`, same `track_number`) → empty.
     - `track_number=None` ignored (mixed with a valid pair) → only the valid pair.
     - proposed-vs-current precedence (`proposed_tags` track# differs from
       `current_tags`; collision keys off proposed).
   - `confirm_force_override` / `confirm_collision_resolution` (in
     `tests/test_interactive.py`, using the existing `prompts`/`prompts_auto_yes`
     fixtures): assert `auto_yes` returns `False` / `"skip"` respectively without
     reading input.
   - **`_process_files` edit loop:** mock `confirm_collision_resolution` to return
     `"edit"` once then `"apply"`/`"skip"`, and `edit_collision_files` to mutate a
     file's `proposed_tags.track_number` so the second `_detect_track_collisions`
     returns empty — assert the loop terminates and no duplicate remains. (Without
     this, a `Mock` returning `"edit"` every call would loop forever, so the test
     also guards against a missing re-detect.)
   - `edit_collision_files` (in `tests/test_interactive.py`): with one colliding
     file whose `proposed_tags=None`, assert it is seeded from `current_tags`
     before `_edit_track_fields` runs (patch `_edit_track_fields` and `input` to
     select that file).
   - **Update the `mock_prompts` fixture** in test_main.py to add
     `confirm_collision_resolution = Mock(return_value="skip")`,
     `edit_collision_files = Mock()`, and
     `confirm_force_override = Mock(return_value=False)` so existing `_process_files`
     tests keep passing once detection is wired in.
