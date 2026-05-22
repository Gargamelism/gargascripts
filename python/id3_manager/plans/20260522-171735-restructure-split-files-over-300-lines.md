# Restructure: split files >300 lines into facade + injected collaborators

## Context

`id3_manager` has grown six source files past 300 lines, the largest being
`main.py` at 1107. Large single-class files are hard to navigate, test in
isolation, and reason about. The goal is a **pure structural refactor** — no
behavior change — so that no source file exceeds ~300 lines. Files over the
limit become a package folder of focused modules.

Two decisions from the user shape the approach:

1. **Coverage first, whole codebase.** Before touching any source, raise the
   *entire* codebase to ~100% test coverage (currently 72%, `276 passed`). The
   tests are the regression net that guarantees the refactor preserves behavior.
   This includes files not being split but currently under-tested:
   `acrcloud_client.py` (27%), `config.py` (35%), `check_malformed.py` (0%).
2. **Composition + dependency injection, not mixins.** Each oversized class
   becomes a thin **facade** that composes smaller **collaborator classes
   injected via the constructor** (with concrete defaults so existing call sites
   keep working and tests can inject fakes). The facade keeps the existing public
   and test-referenced-private method names as thin delegators.
3. **Zero test edits during the move; test migration is a follow-up.** The
   no-test-edit rule holds only through Phases 0–3, where the untouched suite is
   the proof that behavior is preserved. **After the refactor is complete and
   committed, tests may be updated to match the new package structure** — a new
   **Phase 4** migrates tests to target the submodules directly and removes the
   delegator shims that existed purely for test compatibility.

Baseline verified: `python -m pytest tests/` → **276 passed**, 72% coverage.

## Hard constraints (validated against the code + tests)

- **Flat imports.** The package dir is on `sys.path` (tests do
  `sys.path.insert(0, parent)`); everything imports siblings by top-level name
  (`from folder_manager import FolderManager`). Converting `foo.py` → package
  `foo/` with an `__init__.py` that re-exports the public class keeps every
  import site and every test working with zero edits.
- **`main.py` must stay a file** — it is the executable CLI entry point
  (`python main.py`, shebang, `+x`) *and* is imported by tests
  (`from main import ID3Processor, build_parser`). Extract into a `processor/`
  package + `cli.py`, keep a slim `main.py` that re-exports both.
- **`main.ID3Handler` patch target.** Tests do
  `patch('main.ID3Handler.is_supported')`. This works only if `main`,
  `processor.core`, and `processor.traversal` all bind the *same* class via
  `from id3_handler import ID3Handler` (and `id3_handler/__init__` re-exports the
  one class). Processor code calls `ID3Handler.is_supported(...)` as a module
  global (it already does).
- **Processor services read live attributes.** `test_main` reassigns collaborators
  on the instance after construction (`processor.discogs_client = Mock()`, etc.)
  then calls private methods directly. Any extracted service must hold a
  back-reference to the processor and read `self.proc.<client>` at call time —
  never snapshot clients in its `__init__`. The private methods the tests call
  stay as delegators on `ID3Processor`.
- **Preserve test-referenced privates as facade delegators** (grepped per file —
  see table below), and keep in-function imports verbatim
  (`from models import DiscogsRelease` inside `_process_files`; `import re` inside
  `get_discogs_url_or_id`).
- Dependency graph is acyclic and must stay so; `__init__` files import only from
  their own submodules.

## Package-conversion idiom

```python
# foo/__init__.py
from foo.facade import FooClass
__all__ = ["FooClass"]
```

## Facade ⇄ collaborator delegation contract (applies to every split)

Three concrete patterns, used consistently so the next developer never has to
invent one:

1. **Stateless / value-only collaborators** (e.g. `PositionParser`,
   `ReleaseParser`, `TrackMatcher`, `NameService`, `PathMapper`) — constructed
   once in the facade `__init__` with a concrete default, stored on `self`, and
   invoked by the facade's delegator shims. They read no facade state; all inputs
   arrive as method arguments. A facade private shim is a one-liner:
   `def _parse_position(self, position): return self._parser.parse_position(position)`.

2. **Back-reference collaborators that read live facade attributes**
   (`ID3Processor`'s `FolderTraversal`/`DiscogsMatchService`/`TagApplyService`,
   and `SafeWriter`). Constructed as `Service(self)`; store `self.proc = proc`
   (or `self.handler = handler`). At call time they reach back through the facade
   — `self.proc.discogs_client`, `self.proc._discover_audio_files(...)`,
   `getattr(self.handler, f"_write_{fmt}_tags")` — so test reassignment
   (`processor.discogs_client = Mock()`) and `patch.object(handler,
   "_write_mp3_tags")` are honored. **Services never call sibling services
   directly; they always route through `self.proc.<delegator>` so the patch/mock
   surface stays on the facade.** Never snapshot a client/method into `__init__`.

3. **Injected-dependency collaborators that must not back-import**
   (`RecoveryService`). Receive every dependency (`rclone`, `pathmap`,
   `metadata_reader`, `log`, `divergence_pattern`) as constructor args so the
   submodule imports nothing from its siblings → keeps the dependency graph
   acyclic. The facade wires them together in its `__init__`.

**Delegator shim rule:** every name in the "Keep on facade" column of the
test-referenced-privates table is a thin method on the facade whose body is a
single delegating call (or, for the loop-owning methods `confirm_tag_changes`,
`moveto`, `copyto`, `write_tags`, `process`, the real orchestration body that
calls into collaborators). Public methods not referenced by tests are still kept
as delegators on the facade because external call sites (`main.py`, etc.) invoke
them by their original name.

## Per-file decomposition

### `id3_handler.py` (376) → `id3_handler/`
- `facade.py` — `ID3Handler` facade. Keeps constants `SUPPORTED_EXTENSIONS`,
  `MP4_TAGS`; classmethods `is_supported`/`get_format`; `read_tags`/`write_tags`
  delegating to collaborators; delegator shims `_read_*`/`_write_*`/`_get_tag_str`/
  `_get_mp4_tag`/`_parse_track_disc`/`_parse_year`. `__init__(self, codecs=None,
  writer=None)`.
- `formats.py` — `TagCodec` ABC + `Mp3Codec`/`FlacCodec`/`M4aCodec` (per-format
  read/write) + stateless helpers (`parse_track_disc`, `parse_year`, etc.).
- `backup.py` — `SafeWriter` (backup → write → re-read validate → restore-on-
  corruption flow). **Must invoke per-format writes via `getattr(handler,
  f"_write_{fmt}_tags")`** so `patch.object(handler, "_write_mp3_tags")` is honored.
- Sizes: facade ~150, formats ~150, backup ~70.

**Current inventory (id3_handler.py, 377 lines):** `ID3Handler` is **stateless
today — no `__init__`**. Classvars `SUPPORTED_EXTENSIONS` (L19),
`MP4_TAGS` (L22–31). Methods: `is_supported` (classmethod, L33–36), `get_format`
(classmethod, L38–44), `read_tags` (L46–67, dispatches on suffix), `_read_mp3_tags`
(L69–92), `_read_flac_tags` (L94–132), `_read_m4a_tags` (L134–158), `write_tags`
(L160–240, the backup/restore flow), `_write_mp3_tags` (L242–272), `_write_flac_tags`
(L274–300), `_write_m4a_tags` (L302–330), `_get_tag_str` (L332–338), `_get_mp4_tag`
(L340–348), `_parse_track_disc` (L350–366), `_parse_year` (L368–376).

**Method allocation:**
| Source method (lines) | Destination | Facade shim? |
|---|---|---|
| classvars `SUPPORTED_EXTENSIONS`/`MP4_TAGS` | `facade.py` (keep on `ID3Handler`) | n/a |
| `is_supported` (33–36), `get_format` (38–44) | `facade.py` classmethods (bodies stay; only use `SUPPORTED_EXTENSIONS`) | n/a (stay) |
| `read_tags` (46–67) | `facade.py` — dispatch on suffix to `self._codecs[fmt].read(path)` | real body |
| `write_tags` (160–240) | `backup.py` `SafeWriter.write(handler, path, metadata, preserve_existing)`; facade `write_tags` delegates to `self._writer.write(self, ...)` | real delegator |
| `_read_mp3_tags`/`_read_flac_tags`/`_read_m4a_tags` (69–158) | `formats.py` as `Mp3Codec.read`/`FlacCodec.read`/`M4aCodec.read` | yes (shim → codec) |
| `_write_mp3_tags`/`_write_flac_tags`/`_write_m4a_tags` (242–330) | `formats.py` codec `.write` methods | **yes — required** (`patch.object(handler,"_write_mp3_tags")`) |
| `_get_tag_str` (332–338), `_get_mp4_tag` (340–348), `_parse_track_disc` (350–366), `_parse_year` (368–376) | `formats.py` module-level stateless helpers | yes (shims, tests call `_parse_track_disc`/`_parse_year`) |

**New facade `__init__(self, codecs=None, writer=None)`:** `self._codecs =
codecs or {"mp3": Mp3Codec(), "flac": FlacCodec(), "m4a": M4aCodec()}`;
`self._writer = writer or SafeWriter()`. Each codec's `read`/`write` call the
module-level helpers in `formats.py` directly (not through the facade), since
those helpers are pure.

**Critical SafeWriter contract (preserves both patched targets):** `SafeWriter.write`
receives the facade `handler` and must (a) call `handler.read_tags(path)` for the
pre-write and post-write validation reads — so `patch.object(handler,"read_tags")`
is honored; (b) dispatch the per-format write via `getattr(handler,
f"_write_{fmt}_tags")(path, metadata)` — so `patch.object(handler,"_write_mp3_tags")`
is honored; (c) keep the in-memory `original_bytes = path.read_bytes()` backup and
restore-on-corruption / restore-on-write-failure branches verbatim (current L184–240),
including `existing.merge_with(metadata)` when `preserve_existing`.

### `discogs_client.py` (381) → `discogs_client/`
- `facade.py` — `DiscogsClient(user_token, http=None, release_parser=None,
  matcher=None)`. Delegators for `search`/`get_release`/`find_best_release`/
  `match_track_to_release` + private shims `_parse_release`/`_parse_position`/
  `_is_vinyl_position`/`_parse_vinyl_position`.
- `http.py` — `DiscogsHttp` (session, rate limiting, raw search/get_release).
- `parsing.py` — `PositionParser` (stateless) + `ReleaseParser(position_parser)`.
- `matching.py` — `TrackMatcher.match(release, title)`.
- Sizes: facade ~120, http ~110, parsing ~150, matching ~50.

**Current inventory (discogs_client.py, 382 lines):** classvars `BASE_URL` (L16),
`USER_AGENT` (L17). `__init__(self, user_token: str)` (L19–33) builds
`self.session` (`requests.Session()` + auth/UA headers), `self.user_token`,
`self.rate_limit_remaining = 60`, `self._last_request_time = 0`. Methods:
`_respect_rate_limit` (L35–45), `_update_rate_limit` (L47–52), `search` (L54–89),
`get_release` (L91–123, calls `_parse_release`; handles 404/HTTPError/RequestException),
`_parse_release` (L125–233, the 109-line vinyl/non-vinyl dispatch), `_is_vinyl_position`
(L235–237), `_parse_vinyl_position` (L239–249), `_parse_position` (L251–294),
`find_best_release` (L296–337, calls `search`+`get_release`), `match_track_to_release`
(L339–381, fuzzy >0.7).

**Method allocation:**
| Source method (lines) | Destination | Facade shim? |
|---|---|---|
| `BASE_URL`/`USER_AGENT` (16–17), session+headers, `_respect_rate_limit` (35–45), `_update_rate_limit` (47–52) | `http.py` `DiscogsHttp(user_token)` | n/a |
| `search` (54–89, returns `List[dict]` raw, no parsing) | `http.py` `DiscogsHttp.search`; facade `search` delegates | real delegator |
| `get_release` (91–123) | **split**: `http.py` `DiscogsHttp.get_release(release_id) -> Optional[dict]` (the GET + 404/HTTPError/RequestException handling, returns raw json or None); facade `get_release` does `data = self._http.get_release(id); return self._release_parser.parse(data) if data else None` | real delegator |
| `_parse_release` (125–233) | `parsing.py` `ReleaseParser(position_parser).parse(data)` | yes (test calls `_parse_release`) |
| `_is_vinyl_position` (235–237), `_parse_vinyl_position` (239–249), `_parse_position` (251–294) | `parsing.py` `PositionParser` methods `is_vinyl_position`/`parse_vinyl_position`/`parse_position` | yes (tests call `_parse_position`, `_is_vinyl_position`) |
| `find_best_release` (296–337) | `facade.py` — orchestration calling `self.search`/`self.get_release` (i.e. through facade delegators) | real body |
| `match_track_to_release` (339–381) | `matching.py` `TrackMatcher.match(release, track_title)` | yes (test calls `match_track_to_release`) |

**New facade `__init__(self, user_token, http=None, release_parser=None,
matcher=None)`:** `self._http = http or DiscogsHttp(user_token)`;
`self._release_parser = release_parser or ReleaseParser(PositionParser())`;
`self._matcher = matcher or TrackMatcher()`. `ReleaseParser.parse` calls
`self._position_parser.parse_position(...)` / `is_vinyl_position` /
`parse_vinyl_position` internally (held via its own ctor, not the facade).
Tests construct `DiscogsClient("fake_token")` and call the private shims directly.

### `onedrive_sync.py` (456) → `onedrive_sync/`
- `facade.py` — `OneDriveSync` (unchanged ctor signature + optional `rclone`,
  `pathmap`, `recovery` injections). Keeps `moveto`/`copyto` orchestration and
  delegators `_to_remote`/`_confirm_source_missing`/`_looks_like_source_missing`/
  `_copyto_explicit`/`_lsjson`/`_deletefile`. Defines and **re-exports
  `_default_log`** + `_DIVERGENCE_PATTERN`.
- `pathmap.py` — `PathMapper(local_root, remote)`: `is_in_sync_root`, `to_remote`.
- `rclone.py` — `RcloneOps(rclone_path, timeout, log)`: subprocess wrappers
  (`moveto_raw`, `copyto`, `lsjson`, `deletefile`). **Calls module-level
  `subprocess.run`** so `patch("subprocess.run")` intercepts.
- `recovery.py` — `RecoveryService(rclone, pathmap, metadata_reader, log,
  divergence_pattern)`. Receives deps by injection → no back-import → no cycle.
  Default `metadata_reader` keeps the existing `id3_handler`+`mutagen` edges.
- Sizes: facade ~170, rclone ~90, pathmap ~30, recovery ~180.

**Current inventory (onedrive_sync.py, 457 lines):** module fn `_default_log`
(L31–32); class `OneDriveSync` (L35–457) with classvar `_DIVERGENCE_PATTERN`
(L38–41, compiled regex). `__init__(self, local_root, remote="onedrive:",
rclone_path=None, timeout=120, log=_default_log)` (L43–57) → `self.local_root`
(resolved strict), `self.remote` (trailing `:`), `self.rclone_path`
(`shutil.which` fallback), `self.timeout`, `self.log`. Methods: `is_in_sync_root`
(L59–65), `_to_remote` (L67–72), `moveto` (L74–145, calls `subprocess.run` at
**L108**), `copyto` (L147–172), `_copyto_explicit` (L174–217, `subprocess.run`
at **L200**), `_lsjson` (L219–238, `subprocess.run` at **L223**), `_deletefile`
(L240–253, `subprocess.run` at **L243**), `_looks_like_source_missing` (L255–259),
`_confirm_source_missing` (L261–298), `_recover_diverged_rename` (L300–363),
`_match_diverged_old_name` (L365–426), `_read_recovery_metadata` (L428–448, uses
`ID3Handler().read_tags` + `MutagenFile`), `_normalize_for_match` (staticmethod,
L450–456). Module imports include `from id3_handler import ID3Handler` (L21) and
`from mutagen import File as MutagenFile` (L19).

**Method allocation:**
| Source (lines) | Destination | Facade shim? |
|---|---|---|
| `_default_log` (31–32), `_DIVERGENCE_PATTERN` (38–41) | define in `facade.py`, **re-export both from `onedrive_sync/__init__.py`** | n/a |
| `__init__` (43–57) | `facade.py`; wires `pathmap`/`rclone`/`recovery` (see below) | n/a |
| `is_in_sync_root` (59–65) | `pathmap.py` `PathMapper.is_in_sync_root`; facade delegates | real delegator |
| `_to_remote` (67–72) | `pathmap.py` `PathMapper.to_remote` | yes (test calls `_to_remote`) |
| `moveto` (74–145) | `facade.py` orchestration: calls `self._to_remote`, `self._rclone.moveto_raw(...)` (which does the `subprocess.run`), interprets result, on divergence calls `self._confirm_source_missing` then `self._recovery._recover_diverged_rename` | real body — keeps `moveto` |
| `copyto` (147–172) | `facade.py` orchestration → `self._copyto_explicit` | real body — keeps `copyto` |
| `_copyto_explicit` (174–217, `subprocess.run`) | `rclone.py` `RcloneOps.copyto`; facade `_copyto_explicit` delegates | yes |
| `_lsjson` (219–238, `subprocess.run`) | `rclone.py` `RcloneOps.lsjson`; facade `_lsjson` delegates | yes |
| `_deletefile` (240–253, `subprocess.run`) | `rclone.py` `RcloneOps.deletefile`; facade `_deletefile` delegates | yes |
| `subprocess.run` at L108 (inside moveto) | `rclone.py` `RcloneOps.moveto_raw(cmd-or-args) -> CompletedProcess/result` | n/a |
| `_looks_like_source_missing` (255–259) | `recovery.py` `RecoveryService.looks_like_source_missing` (uses injected `divergence_pattern`) | yes |
| `_confirm_source_missing` (261–298) | `recovery.py` `RecoveryService.confirm_source_missing` | **yes — required** (`patch.object(sync,"_confirm_source_missing")`) |
| `_recover_diverged_rename` (300–363) | `recovery.py` | facade shim `_recover_diverged_rename` |
| `_match_diverged_old_name` (365–426) | `recovery.py` | (internal to recovery) |
| `_read_recovery_metadata` (428–448) | `recovery.py` via injected `metadata_reader` (default reads `ID3Handler().read_tags` + `MutagenFile`) | (internal) |
| `_normalize_for_match` (450–456) | `recovery.py` staticmethod | (internal) |

**New facade `__init__`** — same public signature, plus optional `*, rclone=None,
pathmap=None, recovery=None`. Wiring (defaults):
- `self._pathmap = pathmap or PathMapper(self.local_root, self.remote)` (PathMapper
  ctor does the resolve(strict) + trailing-`:` normalization currently in L53–54).
- `self._rclone = rclone or RcloneOps(self.rclone_path, self.timeout, self.log)`.
- `self._recovery = recovery or RecoveryService(rclone=self._rclone,
  pathmap=self._pathmap, metadata_reader=_default_metadata_reader, log=self.log,
  divergence_pattern=_DIVERGENCE_PATTERN)`.
- `_default_metadata_reader` (a small module-level fn or callable in `recovery.py`)
  encapsulates the `ID3Handler().read_tags` + `MutagenFile` edges so only
  `recovery.py` imports `id3_handler`/`mutagen` → **breaks the potential
  `onedrive_sync → folder_manager → onedrive_sync` / `id3_handler` cycle.**

**Subprocess patch invariant:** `rclone.py` does `import subprocess` and calls
`subprocess.run(...)` at module-call time, so the existing `patch("subprocess.run")`
in `test_onedrive_sync.py` intercepts all four call sites. `moveto`/`copyto`
still call `self._confirm_source_missing` (facade shim) so `patch.object(sync,
"_confirm_source_missing")` works.

### `folder_manager.py` (574) → `folder_manager/`
- `facade.py` — `FolderManager(onedrive_sync=None, *, name_service=None,
  disc_detector=None, ops=None)`. Keeps `onedrive_sync` as a public attribute,
  constants `DISC_PATTERNS`/`ALBUM_FOLDER_PATTERN`, delegators for all public
  methods + private shims `_sanitize_name`/`_extract_disc_number`.
- `naming.py` — `NameService`: sanitize/generate/parse/should_rename/album-info.
- `discinfo.py` — `DiscDetector(name_service)`: multi-disc detection + inference.
- `operations.py` — `FolderOps(onedrive_sync, name_service, disc_detector)`:
  rename/move/create/reorganize **+ the sync helpers** `_mirror_rename`/
  `_commit_with_rollback`.
- Sizes: facade ~90, naming ~150, discinfo ~90, operations ~240.

**Current inventory (folder_manager.py, 574 lines):** classvars `DISC_PATTERNS`
(L20–24), `ALBUM_FOLDER_PATTERN` (L27). `__init__(self, onedrive_sync=None)`
(L29–36) → `self.onedrive_sync` (L36, **public attribute**). Methods:
`_mirror_rename` (L38–51, calls `self.onedrive_sync.moveto`), `_commit_with_rollback`
(L53–96, calls `self.onedrive_sync.log` + `_mirror_rename` on rollback),
`detect_multi_disc_structure` (L98–134), `_extract_disc_number` (L136–143),
`infer_disc_info_from_path` (L145–160), `normalize_disc_folder_name` (L162–197),
`detect_multi_disc_from_metadata` (L199–216), `generate_folder_name` (L218–230),
`generate_disc_folder_name` (L232–242), `_sanitize_name` (L244–255),
`is_folder_properly_named` (L257–268), `parse_folder_name` (L270–284),
`rename_folder` (L286–317), `create_multi_disc_structure` (L319–359),
`move_file_to_disc_folder` (L361–395), `reorganize_multi_disc_album` (L397–462),
`get_album_info_from_files` (L464–489), `generate_filename` (L491–520),
`should_rename_file` (L522–541), `rename_audio_file` (L543–574).

**Method allocation:**
| Source (lines) | Destination | Facade shim? |
|---|---|---|
| `DISC_PATTERNS` (20–24), `ALBUM_FOLDER_PATTERN` (27) | `facade.py` classvars | n/a |
| `__init__` (29–36), `self.onedrive_sync` | `facade.py`; **keep `self.onedrive_sync` as a real public attribute** | n/a |
| `_sanitize_name` (244–255) | `naming.py` `NameService.sanitize` | yes (6 test calls) |
| `generate_folder_name` (218–230), `generate_disc_folder_name` (232–242), `is_folder_properly_named` (257–268), `parse_folder_name` (270–284), `get_album_info_from_files` (464–489), `generate_filename` (491–520), `should_rename_file` (522–541) | `naming.py` `NameService` | delegators (public) |
| `_extract_disc_number` (136–143) | `discinfo.py` `DiscDetector._extract` / `extract_disc_number` | yes (8 test calls) |
| `detect_multi_disc_structure` (98–134), `infer_disc_info_from_path` (145–160), `detect_multi_disc_from_metadata` (199–216) | `discinfo.py` `DiscDetector(name_service)` | delegators (public) |
| `_mirror_rename` (38–51), `_commit_with_rollback` (53–96) | `operations.py` `FolderOps` | delegators if needed (not in test table, keep as `FolderOps` methods) |
| `normalize_disc_folder_name` (162–197), `rename_folder` (286–317), `create_multi_disc_structure` (319–359), `move_file_to_disc_folder` (361–395), `reorganize_multi_disc_album` (397–462), `rename_audio_file` (543–574) | `operations.py` `FolderOps(onedrive_sync, name_service, disc_detector)` | delegators (public) |

**New facade `__init__(self, onedrive_sync=None, *, name_service=None,
disc_detector=None, ops=None)`:** `self.onedrive_sync = onedrive_sync` (public);
`self._naming = name_service or NameService()`; `self._discinfo = disc_detector
or DiscDetector(self._naming)`; `self._ops = ops or FolderOps(self.onedrive_sync,
self._naming, self._discinfo)`. `FolderOps` reads `self.onedrive_sync` (the
injected ref) in `_mirror_rename`/`_commit_with_rollback`. **`test_folder_manager.py`
constructs `FolderManager(onedrive_sync=MagicMock())` and never reassigns
`.onedrive_sync` after construction** (verified) — so injecting the ref into
`FolderOps` at construction time is safe; no live-read needed here. `DiscDetector`
and `NameService` are stateless w.r.t. sync.

### `interactive.py` (747) → `interactive/`
- `facade.py` — `InteractivePrompts(no_color, auto_yes, quiet, console=None,
  prompt_service=None, edit_service=None, display_service=None)`. Owns `COLORS` +
  the `confirm_tag_changes` loop (drives edit/display); delegators for all public
  methods + shims `_c`/`_prompt_choice`.
- `console.py` — `Console(no_color, quiet)`: `_c`, `_prompt_choice`, `print`,
  `COLORS` (applies the no_color emptying).
- `prompts.py` — `PromptService(console, auto_yes)`: menu/entry prompts.
- `editing.py` — `EditService(console)`: track/album field editors.
- `display.py` — `DisplayService(console, quiet)`: comparisons/progress/summary.
- Sizes: facade ~120, console ~60, prompts ~290, editing ~170, display ~190.
  Fallback if `prompts.py` >300: peel `handle_no_*`/`handle_track_not_in_release`
  into `interactive/menus.py`.

**Current inventory (interactive.py, 748 lines):** classvar `COLORS` (L16–24,
ANSI dict). `__init__(self, no_color=False, auto_yes=False, quiet=False)`
(L26–41) → `self.no_color`, `self.auto_yes`, `self.quiet`, and if `no_color`
replaces `self.COLORS` with `{k: "" for k in self.COLORS}` (L40–41). Methods:
`_c` (L43–45), `_prompt_choice` (L47–63), `print` (L65–68), `show_file_comparison`
(L70–114), `show_acr_result` (L116–123), `show_discogs_candidates` (L125–175),
`get_discogs_url_or_id` (L177–211, **local `import re` at L184**),
`confirm_tag_changes` (L213–256, the review/edit/album-edit loop),
`_handle_edit_track` (L258–293), `_handle_edit_album` (L295–351), `_edit_track_fields`
(L353–419), `confirm_folder_rename` (L421–443), `handle_no_acr_match` (L445–467),
`handle_no_discogs_match` (L469–495), `get_manual_metadata` (L497–554, local
`prompt_field`/`prompt_int` fns), `prompt_missing_fields` (L556–621),
`get_modified_search_query` (L623–640), `show_file_rename` (L642–645),
`confirm_file_renames` (L647–672), `show_progress` (L674–689), `show_summary`
(L691–716), `show_folder_status` (L718–724), `handle_track_not_in_release`
(L726–747).

**Decision — apply the menus.py split up front (not as a fallback).** Counting
prompt-method bodies puts `prompts.py` at ~349 lines (`get_discogs_url_or_id` 35 +
`handle_no_acr_match` 23 + `handle_no_discogs_match` 27 + `get_manual_metadata` 58 +
`prompt_missing_fields` 66 + `get_modified_search_query` 18 + `confirm_folder_rename`
23 + `confirm_file_renames` 26 + `handle_track_not_in_release` 22 +
`show_discogs_candidates` 51), which exceeds 300. So move the four menu/selection
methods (`handle_no_acr_match`, `handle_no_discogs_match`, `handle_track_not_in_release`,
`show_discogs_candidates`, ~123 lines) into `interactive/menus.py`
`MenuService(console, auto_yes)`, leaving `prompts.py` ~226.

**Method allocation:**
| Source (lines) | Destination | Facade shim? |
|---|---|---|
| `COLORS` (16–24), `_c` (43–45), `_prompt_choice` (47–63), `print` (65–68), no_color emptying (40–41) | `console.py` `Console(no_color, quiet)` | `_c`, `_prompt_choice` are facade shims (tests call both) |
| `confirm_tag_changes` (213–256) | `facade.py` real body — drives `edit_service` + `display_service` via facade shims; reads `self.auto_yes` | real body |
| `_handle_edit_track` (258–293), `_handle_edit_album` (295–351), `_edit_track_fields` (353–419) | `editing.py` `EditService(console)` | facade shims (called by `confirm_tag_changes`) |
| `show_file_comparison` (70–114), `show_acr_result` (116–123), `show_file_rename` (642–645), `show_progress` (674–689), `show_summary` (691–716), `show_folder_status` (718–724) | `display.py` `DisplayService(console, quiet)` | delegators (public) |
| `get_discogs_url_or_id` (177–211, **keep local `import re`**), `get_manual_metadata` (497–554, keep local helper fns), `prompt_missing_fields` (556–621), `get_modified_search_query` (623–640), `confirm_folder_rename` (421–443), `confirm_file_renames` (647–672) | `prompts.py` `PromptService(console, auto_yes)` | delegators (public) |
| `handle_no_acr_match` (445–467), `handle_no_discogs_match` (469–495), `handle_track_not_in_release` (726–747), `show_discogs_candidates` (125–175) | `menus.py` `MenuService(console, auto_yes)` | delegators (public) |

**New facade `__init__(self, no_color=False, auto_yes=False, quiet=False,
console=None, prompt_service=None, edit_service=None, display_service=None,
menu_service=None)`:** keep `self.no_color`/`self.auto_yes`/`self.quiet`;
`self._console = console or Console(no_color, quiet)`; `self._prompts =
prompt_service or PromptService(self._console, auto_yes)`; `self._edit =
edit_service or EditService(self._console)`; `self._display = display_service or
DisplayService(self._console, quiet)`; `self._menus = menu_service or
MenuService(self._console, auto_yes)`. All collaborators call `self._console._c` /
`self._console._prompt_choice` for I/O — `no_color` lives once in `Console`. Tests
construct `InteractivePrompts(no_color=True[, auto_yes=True][, quiet=True])` and
call `_c`/`_prompt_choice` directly via facade shims that forward to `self._console`.

### `main.py` (1107) → slim `main.py` + `cli.py` + `processor/`
- `main.py` (slim, ~95) — imports incl. `from id3_handler import ID3Handler`,
  re-exports `ID3Processor` + `build_parser`, `main()`, `if __name__ ==
  "__main__"`, shebang, `+x`.
- `cli.py` (~155) — `build_parser()` verbatim.
- `processor/core.py` (~250) — `ID3Processor` facade. Real bodies for `__init__`,
  `process`, `_discover_audio_files`, `_process_single_file`,
  `_process_single_file_obj`, `_match_track_from_cached_release`. Builds services
  with `self` injected + defaulted. All test-called privates stay here as
  methods/delegators.
- `processor/traversal.py` (~230) — `FolderTraversal(proc)`: bodies of
  `_filter_folders_from_start`, `_process_recursive`, `_process_folder`,
  `_process_disc`, `_process_files`, `_handle_folder_rename`.
- `processor/discogs_match.py` (~215) — `DiscogsMatchService(proc)`: the 200-line
  `_search_and_match_discogs`.
- `processor/apply.py` (~150) — `TagApplyService(proc)`: `_apply_tag_changes`,
  `_push_tag_writes_to_onedrive`, `_backfill_disc_info`, `_handle_file_renames`.

**Current inventory (main.py, 1107 lines):** shebang at L1; module imports L9–29
including `from id3_handler import ID3Handler` (L24) and the other collaborator
imports. `class ID3Processor` (L32–887); `build_parser()` (L889–1039); `main()`
(L1042–1104); `if __name__ == "__main__"` (L1106–1107).
`ID3Processor.__init__(self, config, args, prompts)` (L35–59) assigns: `self.config`
(L45), `self.args` (L46), `self.prompts` (L47), `self.stats` (L48), `self.id3_handler`
(L51), `self.folder_manager` (L60), `self.acr_client` (L62–68, conditional/None),
`self.discogs_client` (L70–72, conditional/None). Note: a local `onedrive_sync` is
built in `__init__` (L53) and passed into `FolderManager`, not stored as a direct
attribute. **In-function import:** `from models import DiscogsRelease` inside
`_process_files` at **L257** — keep verbatim in `processor/traversal.py`.

Method line ranges & primary calls:
- `process` (74–94) → `_process_single_file`, `_process_recursive`, `_process_folder`
- `_filter_folders_from_start` (96–135) — isolated
- `_process_recursive` (137–163) → `_filter_folders_from_start`, `_process_folder`
- `_process_folder` (165–229) → `_discover_audio_files`, `_handle_file_renames`,
  `_handle_folder_rename`, `_process_disc`, `_process_files`, `folder_manager.*`
- `_process_disc` (231–253) → `_process_files`
- `_process_files` (255–294) → `_process_single_file_obj`, `_backfill_disc_info`,
  `_apply_tag_changes`, `_handle_file_renames`
- `_process_single_file` (296–327) → `ID3Handler.is_supported`, `_process_single_file_obj`,
  `_apply_tag_changes`, `_handle_file_renames`
- `_process_single_file_obj` (329–434) → `_match_track_from_cached_release`,
  `_search_and_match_discogs`, `prompts.*`
- `_match_track_from_cached_release` (436–486) → `discogs_client.match_track_to_release`,
  `prompts.prompt_missing_fields`
- `_search_and_match_discogs` (488–694, ~207 lines) → `discogs_client.*`, `prompts.*`
- `_apply_tag_changes` (696–730) → `id3_handler.write_tags`, `_handle_file_renames`,
  `_push_tag_writes_to_onedrive`
- `_push_tag_writes_to_onedrive` (732–747) → `folder_manager.onedrive_sync.copyto`
- `_backfill_disc_info` (749–761) → `folder_manager.infer_disc_info_from_path`
- `_handle_file_renames` (763–805) → `folder_manager.*`, `prompts.confirm_file_renames`
- `_handle_folder_rename` (807–857) → `folder_manager.*`, `prompts.confirm_folder_rename`
- `_discover_audio_files` (859–886) → `ID3Handler.is_supported`/`get_format`,
  `id3_handler.read_tags`

**Method allocation:**
| Source (lines) | Destination | On facade `ID3Processor` |
|---|---|---|
| `__init__` (35–59) | `processor/core.py` — also builds services (below) | real body |
| `process` (74–94) | `core.py` | real body |
| `_discover_audio_files` (859–886) | `core.py` | real body (test calls it) |
| `_process_single_file` (296–327) | `core.py` | real body (test calls it) |
| `_process_single_file_obj` (329–434) | `core.py` | real body (test calls it) |
| `_match_track_from_cached_release` (436–486) | `core.py` | real body (test calls it) |
| `_filter_folders_from_start` (96–135), `_process_recursive` (137–163), `_process_folder` (165–229), `_process_disc` (231–253), `_process_files` (255–294, keep L257 import) | `traversal.py` `FolderTraversal(proc)` | delegator shims (`_filter_folders_from_start`, `_process_folder`, `_process_files` called by tests) |
| `_handle_folder_rename` (807–857) | `traversal.py` | delegator shim |
| `_search_and_match_discogs` (488–694) | `discogs_match.py` `DiscogsMatchService(proc)` | delegator shim (test calls it) |
| `_apply_tag_changes` (696–730), `_push_tag_writes_to_onedrive` (732–747), `_backfill_disc_info` (749–761), `_handle_file_renames` (763–805) | `apply.py` `TagApplyService(proc)` | delegator shims (`_apply_tag_changes`, `_handle_file_renames` called by tests) |

**`core.py` `__init__` builds services after assigning the collaborator
attributes:** `self._traversal = FolderTraversal(self)`; `self._discogs_match =
DiscogsMatchService(self)`; `self._apply = TagApplyService(self)`. Each stores
`self.proc = proc` and reads `self.proc.discogs_client` / `self.proc.acr_client` /
`self.proc.id3_handler` / `self.proc.folder_manager` / `self.proc.prompts` / `self.proc.args`
/ `self.proc.stats` **live at call time** — never snapshotting — because
`test_main.py` reassigns these (e.g. `processor.discogs_client = Mock()`,
`processor.id3_handler = Mock()`, `processor.folder_manager = Mock()`,
`processor.acr_client = Mock()`) after construction and then invokes the private
delegators. Services route cross-service calls through `self.proc.<delegator>`
(e.g. traversal's `_process_folder` calls `self.proc._discover_audio_files(...)`
and `self.proc._handle_file_renames(...)`), so all patch/mock surfaces stay on the
`ID3Processor` instance.

**`main.ID3Handler` patch invariant (HIGHEST risk):** `processor/core.py` and
`processor/traversal.py` call `ID3Handler.is_supported(...)`/`get_format(...)` as
module globals; therefore `main.py`, `processor/core.py`, and `processor/traversal.py`
must each do `from id3_handler import ID3Handler` so they bind the **one** class
object that `id3_handler/__init__.py` re-exports. Then `patch('main.ID3Handler.is_supported')`
(which patches the attribute on the shared class object) is visible everywhere.
`patch('models.file_needs_rename')` is unaffected (it patches the `models` module).

**`main.py` slim (~95 lines):** shebang, module imports (incl. `from id3_handler
import ID3Handler` so `main.ID3Handler` resolves, `from processor import
ID3Processor`, `from cli import build_parser`), re-export `ID3Processor` and
`build_parser` at module level (so `from main import ID3Processor, build_parser`
works), `main()` body (verbatim from L1042–1104), `if __name__ == "__main__"`,
keep `+x` permission. `processor/__init__.py` re-exports `ID3Processor` from
`processor.core`.

### Left as-is (tests added only)
`acrcloud_client.py` (290), `models.py`, `config.py`, `utils.py`,
`sync_results.py`, `check_malformed.py`, top-level `__init__.py`.

## Test-referenced privates to preserve (per file)

These shims keep the existing suite green **through Phases 0–3** (zero test edits).
Most are *test-only* and become removable in **Phase 4** once tests are re-pointed
at the new submodules — see the Phase 4 test-only-shim inventory for what stays vs.
goes.

| File | Referenced/patched in tests | Keep on facade |
|---|---|---|
| id3_handler | `_parse_track_disc`, `_parse_year`, `patch.object(_write_mp3_tags)`, `is_supported`/`get_format` | those + `_read_*`/`_write_*`/`_get_tag_str`/`_get_mp4_tag` |
| discogs_client | `_parse_position`, `_is_vinyl_position`, `_parse_release` | those + `_parse_vinyl_position` |
| onedrive_sync | `_to_remote`, `patch.object(_confirm_source_missing)`, global `patch("subprocess.run")` | `_to_remote`/`_confirm_source_missing`/`_looks_like_source_missing`/`moveto`/`copyto`; re-export `_default_log` |
| folder_manager | `_sanitize_name`, `_extract_disc_number`, ctor `onedrive_sync=`, `.onedrive_sync` attr | those + public attr |
| interactive | `_c`, `_prompt_choice`, ctor `(no_color,auto_yes,quiet)` | those + Console no_color behavior |
| main | `_search_and_match_discogs`, `_match_track_from_cached_release`, `_apply_tag_changes`, `_process_single_file_obj`, `_process_single_file`, `_process_files`, `_process_folder`, `_filter_folders_from_start`, `_discover_audio_files`; `patch('main.ID3Handler.*')`; `patch('models.file_needs_rename')` | all listed privates as methods/delegators on `ID3Processor` |

## Work ordering

### Phase 0 — prep
Commit clean tree so each step is bisectable. (Baseline already verified.)

### Phase 1 — whole-codebase coverage to ~100% (no source changes)
Add tests; re-run after each; never touch source.

**Test harness facts (verified):** `tests/conftest.py` puts the source dir on
`sys.path` via `sys.path.insert(0, str(Path(__file__).parent.parent))` (so
`from acrcloud_client import ACRCloudClient` works flat). conftest provides reusable
fixtures: `sample_metadata`, `multi_disc_metadata`, `incomplete_metadata`
(`TrackMetadata` variants), `sample_discogs_track`, `sample_discogs_release`
(`DiscogsRelease` with multiple tracks), `sample_audio_file` (`AudioFile`). Reuse
these rather than rebuilding objects. New test files use the same `sys.path`
mechanism automatically (conftest is shared).

1. **check_malformed.py (0%)** — new `tests/test_check_malformed.py`. Entry point
   is `main() -> None` (L9–30), a script with `if __name__ == "__main__"` (L33).
   It reads `sys.argv[1]` as a folder; `len(sys.argv) < 2` →
   `print(f"Usage: {sys.argv[0]} <folder>")` to stdout + `sys.exit(1)`. For each
   `Path(folder).rglob("*")` it calls `ID3Handler.is_supported(str(f))` then
   `h.read_tags(str(f))` in a try/except catching **any `Exception`**, appending
   `(relative_path, error_str)`. Clean run → `print("No malformed files found.")`;
   malformed → `print(f"Found {len(errors)} malformed file(s):")` then per-file
   `print(f"  {path}: {err}")`. Tests: drive via `monkeypatch.setattr(sys, "argv",
   [...])` + `capsys`; usage/exit (assert `SystemExit` code 1); clean (real temp
   file or monkeypatch `ID3Handler.read_tags` to succeed); malformed (monkeypatch
   `ID3Handler.read_tags` to raise). Mock surface: `ID3Handler`, `Path.rglob`.
2. **config.py (35%)** — new `tests/test_config.py`. Signatures:
   `eprint(*args, **kwargs)` (L10–12, writes to `sys.stderr`);
   `load_config(env_file: Optional[str] = None) -> dict` (L15–45, calls
   `dotenv.load_dotenv`, returns dict keyed `acrcloud_host`/`acrcloud_access_key`/
   `acrcloud_access_secret`/`discogs_user_token` from `os.getenv`);
   `validate_config(config: dict, skip_acr: bool = False, skip_discogs: bool =
   False) -> List[str]` (L48–77, returns list of **missing** credential names);
   `get_discogs_token_instructions() -> str` (L80–88); `get_acrcloud_instructions()
   -> str` (L91–101). Env var names: `ACRCLOUD_HOST`, `ACRCLOUD_ACCESS_KEY`,
   `ACRCLOUD_ACCESS_SECRET`, `DISCOGS_USER_TOKEN`. **No `sys.exit` in this module.**
   Tests: `load_config` env-present (monkeypatch `os.getenv`, mock `load_dotenv`) /
   env-missing; `validate_config` all-present (→ `[]`) / missing-ACR-trio /
   skip_acr=True (ACR not required) / missing-token / skip_discogs=True; `eprint`
   via `capsys` (check `err`); instruction helpers return non-empty str.
3. **acrcloud_client.py (27%)** — extend existing `tests/test_acrcloud_client.py`
   (already covers `_parse_response` ×10 and `__init__` ×2; uses
   `ACRCloudClient("fake.host.com","fake_key","fake_secret")` fixture and raw-dict
   responses). **CORRECTION: this module uses `pedalboard.io.AudioFile`, NOT pydub.**
   Signatures: `__init__(host, access_key, access_secret)` (sets `self.timeout=15`);
   `recognize(audio_path, duration_seconds=15) -> Optional[ACRCloudResult]` (L76–120,
   extracts middle segment → MP3 → `_call_api` → `_parse_response` → unlink temp);
   `_extract_audio_segment(audio_path, start_sec, duration_sec) -> Tuple[np.ndarray,
   int]` (L35–59, `pedalboard.io.AudioFile`); `_export_to_mp3(audio_data, sample_rate,
   output_path) -> None` (L61–74, `pedalboard.io.AudioFile` write, quality=128);
   `_call_api(file_path) -> dict` (L122–166, HMAC-SHA1 sig, `open(file_path,"rb")`,
   `requests.post(...)`, `.raise_for_status()`, `.json()`); `recognize_with_retry(
   audio_path, max_retries=2)` (L198–242, catches `requests.exceptions.Timeout`
   → `time.sleep(2)`, `requests.exceptions.RequestException` → 429 via
   `"429" in str(e)` → `time.sleep(60)` else `time.sleep(2)`; no-match →
   `_recognize_alternate_segment`); `_recognize_alternate_segment(audio_path,
   attempt)` (L244–290, alternate 0%/25%/75% positions). **Mock surface:**
   `requests.post` (patch `acrcloud_client.requests.post` or `requests.post`),
   `pedalboard.io.AudioFile` (context manager exposing `.samplerate`, `.duration`,
   `.seek`, `.read`), `builtins.open`, `time.sleep`, `time.time`, and
   `Path.exists`/`Path.unlink` for temp cleanup. Patch `time.sleep` so retry tests
   don't actually wait.
4. **id3_handler.py (37%)** — real temp MP3/FLAC/M4A round-trips; preserve_existing
   merge; backup/restore-on-corruption; `_get_mp4_tag` list/scalar/empty; FLAC
   total* fallbacks; unsupported read.
5. **onedrive_sync.py (33%)** — script `subprocess.run`: `moveto` success/skip/
   timeout/notfound; `_looks_like_source_missing`; `_confirm_source_missing` 4
   branches; `_recover_diverged_rename` all branches; `_match_diverged_old_name`
   unique/none/ambiguous; `_read_recovery_metadata`; `_normalize_for_match`;
   `copyto`; `_lsjson` decode-error; `_deletefile`.
6. **interactive.py (39%)** — monkeypatch `input`: each prompt valid/invalid/
   default; `confirm_tag_changes` loop; editors int-parse/keep/clear/invalid;
   `prompt_missing_fields`; `get_manual_metadata` cancel/fill; `show_*` via capsys.
7. **folder_manager.py (63%)** — `_commit_with_rollback` rollback/recovered/fail;
   `create_multi_disc_structure` OSError; `reorganize_multi_disc_album` dry-run/
   partial/empty/not-multi; `move_file_to_disc_folder`; `normalize_disc_folder_name`;
   `infer_disc_info_from_path`.
8. **discogs_client.py (60%)** — `search` exception; rate-limit sleep/wait;
   `_update_rate_limit`; `get_release` 404/HTTPError/RequestException;
   `find_best_release` fallback chain; `match_track_to_release` exact/substring/
   threshold/none.
9. **main.py (46%)** — rename-only; multi-disc per-disc; `_backfill_disc_info`;
   `_apply_tag_changes` dry-run/write-fail/onedrive; `_handle_file_renames`
   confirm/deny/already/fail; `_handle_folder_rename` single/multi;
   `_filter_folders_from_start` found/parent/not-found; `_search_and_match_discogs`
   menu actions + ambiguous loop; `_process_recursive`; `main()` arg validation.

**Gate:** ~95-100% per module via `--cov-report=term-missing`. Commit. This is the net.

### Phase 2 — leaf-first refactor, full suite green after EACH split
1. `id3_handler/` → run suite + verify `patch.object(_write_mp3_tags)` & classmethod patch.
2. `discogs_client/` → verify private shims.
3. `onedrive_sync/` → verify global `subprocess.run` patch, `_to_remote`,
   `_confirm_source_missing`, `from onedrive_sync import OneDriveSync, _default_log`.
4. `folder_manager/` → verify `_sanitize_name`/`_extract_disc_number` + injected-sync `.moveto`.
5. `interactive/` → verify `_c`/`_prompt_choice` + no_color.
6. `main → slim + cli.py + processor/` (LAST) → verify imports, `python main.py
   --help`, `patch('main.ID3Handler.is_supported')`, post-construct `processor.<client>=Mock()`.

After each: delete old `foo.py`, clear stale `__pycache__`, run `python -m pytest tests/`.

### Phase 3 — verify
- `python -m pytest tests/ --cov=. --cov-report=term-missing` → same pass count, ~100%.
- `python main.py --help`; a `--dry-run` smoke run on a sample folder.
- `wc -l` every source file → all < ~300.
- `git diff --stat` for Phase-2 commits → existing test files untouched.

### Phase 4 — post-refactor test migration to the new structure (optional cleanup)

**Premise (new):** the zero-test-edit rule is a *Phase 0–3* constraint only — it
makes the structural move provably behavior-preserving with the existing suite as
the net. **Once Phase 3 is green and committed, tests may be updated to match the
new package layout**, which lets us shed the shims that exist *purely* for test
compatibility. This phase is still a pure refactor (no behavior change); only tests
and now-redundant delegators move. It is lower priority and must not start until
Phase 3 is committed (so it stays trivially revertible).

**What this unlocks — the "test-only shim" inventory.** A facade private is
*test-only* if, after Phase 2, its sole remaining caller is a test (the facade
orchestration and external code now call the collaborator directly, e.g. `moveto`
calls `self._pathmap.to_remote`, not `self._to_remote`). These become removable
once the corresponding tests are re-pointed:

| File | Test-only shims (removable in P4) | Migrate test to target |
|---|---|---|
| id3_handler | `_parse_track_disc`, `_parse_year`, `_get_tag_str`, `_get_mp4_tag`, `_read_mp3_tags`/`_read_flac_tags`/`_read_m4a_tags` | `id3_handler.formats` (helpers + codec `read`) |
| id3_handler | `_write_mp3_tags`/`_write_flac_tags`/`_write_m4a_tags` (also called by `SafeWriter` via `getattr`) | rewire `SafeWriter` to dispatch on the codec, then `patch.object(codec, "write")` / inject a fake codec; remove the facade shims together |
| discogs_client | `_parse_position`, `_parse_release`, `_is_vinyl_position`, `_parse_vinyl_position` | `discogs_client.parsing` (`PositionParser`, `ReleaseParser`) |
| discogs_client | `match_track_to_release` stays public, but unit could target `discogs_client.matching.TrackMatcher` | `discogs_client.matching` |
| onedrive_sync | `_to_remote` (→ `pathmap`), `_looks_like_source_missing`/`_confirm_source_missing`/`_recover_diverged_rename`/`_match_diverged_old_name`/`_read_recovery_metadata`/`_normalize_for_match` (→ `recovery`) | `onedrive_sync.pathmap.PathMapper`, `onedrive_sync.recovery.RecoveryService` (inject fake `rclone`/`pathmap`/`metadata_reader`) |
| folder_manager | `_sanitize_name` (→ `naming`), `_extract_disc_number` (→ `discinfo`) | `folder_manager.naming.NameService`, `folder_manager.discinfo.DiscDetector` |
| interactive | `_c`, `_prompt_choice` | `interactive.console.Console` |
| main/processor | the private delegators (`_search_and_match_discogs`, `_apply_tag_changes`, `_process_*`, `_filter_folders_from_start`, `_handle_file_renames`, …) — **only removable if cross-service calls are rewired service→service instead of routing through `self.proc.<delegator>`** | `processor.traversal`/`processor.discogs_match`/`processor.apply` with a fake `proc` |

**Must NOT be removed (not test-only — real API / hard constraints):**
- Public methods external code calls by name: `read_tags`/`write_tags`,
  `is_supported`/`get_format`, `search`/`get_release`/`find_best_release`/
  `match_track_to_release`, `moveto`/`copyto`/`is_in_sync_root`, all
  `FolderManager`/`InteractivePrompts` public methods, `build_parser`,
  `ID3Processor.process`.
- `folder_manager.onedrive_sync` public attribute (used by
  `processor.apply._push_tag_writes_to_onedrive`).
- `main.py` as an executable file; `from main import ID3Processor, build_parser`;
  `from onedrive_sync import OneDriveSync` (drop `_default_log` re-export only after
  tests stop importing it); the `id3_handler/__init__` single-`ID3Handler` re-export.

**Procedure (per file, leaf-first, same order as Phase 2):**
1. Add new unit tests targeting the submodule/collaborator directly (import from
   `pkg.submodule`, construct the small class, inject fakes).
2. Delete the now-duplicated facade-shim-based tests (or re-point them).
3. Remove the test-only shims; for shims with an internal caller (`_write_*` via
   `SafeWriter`, processor delegators), rewire the caller first.
4. `python -m pytest tests/` green; `wc -l` still < ~300; commit per file.

**Phase-4 gate:** full suite green, coverage still ~100%, every source file < ~300,
no facade carries a private whose only purpose was test compatibility.

## Risks / gotchas
1. `main.ID3Handler` patch — verify right after the main split (HIGHEST).
2. Services read `self.proc.<client>` live, never snapshot (test reassigns clients).
3. `SafeWriter` invokes per-format writes via `getattr(handler, "_write_…")`.
4. OneDrive recovery cycle broken by injecting rclone/pathmap/metadata_reader.
5. `RcloneOps` calls module-level `subprocess.run`.
6. Re-export `_default_log` from `onedrive_sync/__init__.py`.
7. Preserve in-function imports.
8. Remove old `foo.py` + clear `__pycache__` when creating `foo/`.
9. `main.py` stays an executable file.
10. `folder_manager.onedrive_sync` stays a real public attribute.

## Critical files
- `main.py`, `onedrive_sync.py`, `folder_manager.py`, `interactive.py`,
  `id3_handler.py`, `discogs_client.py`
- `tests/test_main.py`, `tests/test_onedrive_sync.py`, `tests/test_id3_handler.py`
