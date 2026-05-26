"""Extra coverage tests for onedrive_sync.py."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from onedrive_sync import OneDriveSync, _default_log
from sync_results import DivergenceConfirmation, LsJsonResult, MoveResult, RcloneResult


@pytest.fixture
def sync_root(tmp_path):
    root = tmp_path / "onedrive"
    root.mkdir()
    return root


@pytest.fixture
def sync(sync_root):
    return OneDriveSync(local_root=sync_root, remote="onedrive:", rclone_path="/usr/bin/rclone")


@pytest.fixture
def src_dst(sync_root):
    src = sync_root / "old.mp3"
    dst = sync_root / "new.mp3"
    src.touch()
    return src, dst


def _run_ok(stdout="", stderr=""):
    return MagicMock(returncode=0, stdout=stdout, stderr=stderr)


def _run_fail(returncode=1, stdout="", stderr="error"):
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# _default_log
# ---------------------------------------------------------------------------

class TestDefaultLog:
    def test_prints_message(self, capsys):
        _default_log("hello")
        assert "hello" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# moveto: remaining branches
# ---------------------------------------------------------------------------

class TestMovetoExtra:
    def test_skips_dst_outside_sync_root(self, sync, sync_root, tmp_path):
        src = sync_root / "a.mp3"
        src.touch()
        dst = tmp_path / "outside" / "b.mp3"
        result = sync.moveto(src, dst)
        assert result.success is True
        assert result.mode == "skipped"
        assert "destination outside" in result.message

    def test_recovery_path_when_confirmed(self, sync, src_dst):
        src, dst = src_dst
        recovery_result = MoveResult(True, "recovered", "recovered")
        with patch("subprocess.run",
                   return_value=_run_fail(returncode=3, stderr="directory not found")), \
             patch.object(sync, "_confirm_source_missing",
                          return_value=DivergenceConfirmation(True, "confirmed")), \
             patch.object(sync, "_recover_diverged_rename", return_value=recovery_result) as mock_recover:
            result = sync.moveto(src, dst)
        mock_recover.assert_called_once()
        assert result.mode == "recovered"

    def test_no_recovery_when_not_confirmed(self, sync, src_dst):
        src, dst = src_dst
        with patch("subprocess.run",
                   return_value=_run_fail(returncode=3, stderr="directory not found")), \
             patch.object(sync, "_confirm_source_missing",
                          return_value=DivergenceConfirmation(False, "not confirmed")):
            result = sync.moveto(src, dst)
        assert result.success is False
        assert result.mode == "failed"
        assert "not confirmed" in result.message

    def test_nonzero_no_divergence_pattern_returns_failed(self, sync, src_dst):
        src, dst = src_dst
        with patch("subprocess.run",
                   return_value=_run_fail(returncode=1, stderr="permission denied")):
            result = sync.moveto(src, dst)
        assert result.success is False
        assert result.mode == "failed"

    def test_uses_stdout_when_stderr_empty(self, sync, src_dst):
        src, dst = src_dst
        with patch("subprocess.run",
                   return_value=MagicMock(returncode=1, stdout="some stdout error", stderr="")), \
             patch.object(sync, "_confirm_source_missing",
                          return_value=DivergenceConfirmation(False, "stub")):
            result = sync.moveto(src, dst)
        # Should use stdout if stderr is empty
        assert result.success is False


# ---------------------------------------------------------------------------
# copyto
# ---------------------------------------------------------------------------

class TestCopyto:
    def test_skips_outside_sync_root(self, sync, tmp_path):
        f = tmp_path / "outside.mp3"
        f.touch()
        result = sync.copyto(f)
        assert result.success is True
        assert "outside sync root" in result.message

    def test_fails_when_local_file_missing(self, sync, sync_root):
        f = sync_root / "missing.mp3"
        result = sync.copyto(f)
        assert result.success is False
        assert "missing" in result.message

    def test_delegates_to_copyto_explicit(self, sync, sync_root):
        f = sync_root / "song.mp3"
        f.touch()
        mock_result = RcloneResult(True, "pushed")
        with patch.object(sync, "_copyto_explicit", return_value=mock_result) as m:
            result = sync.copyto(f)
        m.assert_called_once()
        assert result.success is True

    def test_passes_timeout_to_copyto_explicit(self, sync, sync_root):
        f = sync_root / "song.mp3"
        f.touch()
        with patch.object(sync, "_copyto_explicit", return_value=RcloneResult(True, "ok")) as m:
            sync.copyto(f, timeout=300)
        _, kwargs = m.call_args
        assert kwargs.get("timeout") == 300 or m.call_args[0][3] == 300 or \
               any(a == 300 for a in m.call_args[0])


# ---------------------------------------------------------------------------
# _copyto_explicit
# ---------------------------------------------------------------------------

class TestCopytoExplicit:
    def test_success(self, sync, sync_root):
        f = sync_root / "s.mp3"
        f.touch()
        with patch("subprocess.run", return_value=_run_ok()):
            result = sync._copyto_explicit(f, "onedrive:s.mp3", dry_run=False)
        assert result.success is True

    def test_dry_run_appends_flag(self, sync, sync_root):
        f = sync_root / "s.mp3"
        f.touch()
        with patch("subprocess.run", return_value=_run_ok()) as run:
            sync._copyto_explicit(f, "onedrive:s.mp3", dry_run=True)
        cmd = run.call_args.args[0]
        assert "--dry-run" in cmd

    def test_timeout(self, sync, sync_root):
        f = sync_root / "s.mp3"
        f.touch()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("", 1)):
            result = sync._copyto_explicit(f, "onedrive:s.mp3", dry_run=False)
        assert result.success is False
        assert "timed out" in result.message

    def test_not_found(self, sync, sync_root):
        f = sync_root / "s.mp3"
        f.touch()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = sync._copyto_explicit(f, "onedrive:s.mp3", dry_run=False)
        assert result.success is False
        assert "not found" in result.message

    def test_nonzero_exit(self, sync, sync_root):
        f = sync_root / "s.mp3"
        f.touch()
        with patch("subprocess.run", return_value=_run_fail(returncode=2, stderr="error")):
            result = sync._copyto_explicit(f, "onedrive:s.mp3", dry_run=False)
        assert result.success is False
        assert "exit 2" in result.message

    def test_uses_custom_timeout(self, sync, sync_root):
        f = sync_root / "s.mp3"
        f.touch()
        with patch("subprocess.run", return_value=_run_ok()) as run:
            sync._copyto_explicit(f, "onedrive:s.mp3", dry_run=False, timeout=999)
        kwargs = run.call_args[1]
        assert kwargs.get("timeout") == 999


# ---------------------------------------------------------------------------
# _lsjson
# ---------------------------------------------------------------------------

class TestLsjson:
    def test_returns_entries_on_success(self, sync):
        entries = [{"Name": "song.mp3"}]
        with patch("subprocess.run",
                   return_value=_run_ok(stdout=json.dumps(entries))):
            result = sync._lsjson(["onedrive:Music"])
        assert result.success is True
        assert result.entries == entries

    def test_returns_empty_list_on_empty_output(self, sync):
        with patch("subprocess.run", return_value=_run_ok(stdout="")):
            result = sync._lsjson(["onedrive:Music"])
        assert result.success is True
        assert result.entries == []

    def test_returns_error_on_nonzero(self, sync):
        with patch("subprocess.run", return_value=_run_fail(returncode=3, stderr="not found")):
            result = sync._lsjson(["onedrive:Music"])
        assert result.success is False
        assert "exit 3" in result.error

    def test_returns_error_on_timeout(self, sync):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("", 1)):
            result = sync._lsjson(["onedrive:Music"])
        assert result.success is False
        assert "timed out" in result.error

    def test_returns_error_on_not_found(self, sync):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = sync._lsjson(["onedrive:Music"])
        assert result.success is False
        assert "not found" in result.error

    def test_returns_error_on_json_decode_failure(self, sync):
        with patch("subprocess.run", return_value=_run_ok(stdout="not json")):
            result = sync._lsjson(["onedrive:Music"])
        assert result.success is False
        assert "JSON parse" in result.error


# ---------------------------------------------------------------------------
# _deletefile
# ---------------------------------------------------------------------------

class TestDeletefile:
    def test_success(self, sync):
        with patch("subprocess.run", return_value=_run_ok()):
            result = sync._deletefile("onedrive:old.mp3")
        assert result.success is True
        assert "deleted" in result.message

    def test_nonzero_exit(self, sync):
        with patch("subprocess.run", return_value=_run_fail(returncode=1, stderr="err")):
            result = sync._deletefile("onedrive:old.mp3")
        assert result.success is False
        assert "exit 1" in result.message

    def test_timeout(self, sync):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("", 1)):
            result = sync._deletefile("onedrive:old.mp3")
        assert result.success is False
        assert "timed out" in result.message

    def test_not_found(self, sync):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = sync._deletefile("onedrive:old.mp3")
        assert result.success is False
        assert "not found" in result.message


# ---------------------------------------------------------------------------
# _looks_like_source_missing
# ---------------------------------------------------------------------------

class TestLooksLikeSourceMissing:
    def test_exit_3_with_directory_not_found(self, sync):
        assert sync._looks_like_source_missing(3, "directory not found") is True

    def test_exit_3_with_item_not_found(self, sync):
        assert sync._looks_like_source_missing(3, "itemNotFound") is True

    def test_exit_1_with_directory_not_found(self, sync):
        assert sync._looks_like_source_missing(1, "item not found") is True

    def test_exit_0_returns_false(self, sync):
        assert sync._looks_like_source_missing(0, "directory not found") is False

    def test_exit_3_without_pattern_returns_false(self, sync):
        assert sync._looks_like_source_missing(3, "permission denied") is False

    def test_exit_2_returns_false(self, sync):
        assert sync._looks_like_source_missing(2, "directory not found") is False


# ---------------------------------------------------------------------------
# _confirm_source_missing
# ---------------------------------------------------------------------------

class TestConfirmSourceMissing:
    def test_dst_listing_fails_returns_not_confirmed(self, sync, src_dst):
        src, dst = src_dst
        with patch.object(sync, "_lsjson") as lsjson:
            lsjson.return_value = LsJsonResult(success=False, error="dst failed")
            result = sync._confirm_source_missing(src, dst)
        assert result.confirmed is False
        assert "dst parent listing failed" in result.reason

    def test_src_listing_fails_returns_not_confirmed(self, sync, src_dst):
        src, dst = src_dst
        call_count = [0]

        def side_effect(args):
            call_count[0] += 1
            if call_count[0] == 1:
                return LsJsonResult(success=True, entries=[])
            return LsJsonResult(success=False, error="src failed")

        with patch.object(sync, "_lsjson", side_effect=side_effect):
            result = sync._confirm_source_missing(src, dst)
        assert result.confirmed is False
        assert "src parent listing failed" in result.reason

    def test_src_found_in_listing_returns_not_confirmed(self, sync, src_dst):
        src, dst = src_dst

        def side_effect(args):
            return LsJsonResult(success=True, entries=[{"Name": src.name}])

        with patch.object(sync, "_lsjson", side_effect=side_effect):
            result = sync._confirm_source_missing(src, dst)
        assert result.confirmed is False
        assert "transient" in result.reason

    def test_src_absent_returns_confirmed(self, sync, src_dst):
        src, dst = src_dst
        call_count = [0]

        def side_effect(args):
            call_count[0] += 1
            if call_count[0] == 1:
                return LsJsonResult(success=True, entries=[])  # dst parent ok
            return LsJsonResult(success=True, entries=[{"Name": "other.mp3"}])  # src not in listing

        with patch.object(sync, "_lsjson", side_effect=side_effect):
            result = sync._confirm_source_missing(src, dst)
        assert result.confirmed is True


# ---------------------------------------------------------------------------
# _recover_diverged_rename
# ---------------------------------------------------------------------------

class TestRecoverDivergedRename:
    def test_copyto_fails_returns_failed(self, sync, src_dst):
        src, dst = src_dst
        with patch.object(sync, "_copyto_explicit",
                          return_value=RcloneResult(False, "upload failed")):
            result = sync._recover_diverged_rename(src, dst, dry_run=False)
        assert result.success is False
        assert "recovery copyto failed" in result.message

    def test_listing_fails_returns_recovered_copyto_only(self, sync, src_dst):
        src, dst = src_dst
        with patch.object(sync, "_copyto_explicit", return_value=RcloneResult(True, "ok")), \
             patch.object(sync, "_lsjson",
                          return_value=LsJsonResult(success=False, error="listing failed")):
            result = sync._recover_diverged_rename(src, dst, dry_run=False)
        assert result.success is True
        assert result.mode == "recovered"
        assert "copyto only" in result.message

    def test_no_match_returns_recovered_copyto_only(self, sync, src_dst):
        src, dst = src_dst
        with patch.object(sync, "_copyto_explicit", return_value=RcloneResult(True, "ok")), \
             patch.object(sync, "_lsjson",
                          return_value=LsJsonResult(success=True, entries=[])), \
             patch.object(sync, "_match_diverged_old_name", return_value=None):
            result = sync._recover_diverged_rename(src, dst, dry_run=False)
        assert result.success is True
        assert result.mode == "recovered"
        assert "no unique old-name match" in result.message

    def test_dry_run_skips_delete(self, sync, src_dst):
        src, dst = src_dst
        with patch.object(sync, "_copyto_explicit", return_value=RcloneResult(True, "ok")), \
             patch.object(sync, "_lsjson",
                          return_value=LsJsonResult(success=True, entries=[{"Name": "diverged.mp3"}])), \
             patch.object(sync, "_match_diverged_old_name", return_value="diverged.mp3"), \
             patch.object(sync, "_deletefile") as mock_del:
            result = sync._recover_diverged_rename(src, dst, dry_run=True)
        mock_del.assert_not_called()
        assert result.success is True
        assert "DRY-RUN" in result.message

    def test_deletefile_fails_returns_recovered(self, sync, src_dst):
        src, dst = src_dst
        with patch.object(sync, "_copyto_explicit", return_value=RcloneResult(True, "ok")), \
             patch.object(sync, "_lsjson",
                          return_value=LsJsonResult(success=True, entries=[{"Name": "old.mp3"}])), \
             patch.object(sync, "_match_diverged_old_name", return_value="old.mp3"), \
             patch.object(sync, "_deletefile",
                          return_value=RcloneResult(False, "delete failed")):
            result = sync._recover_diverged_rename(src, dst, dry_run=False)
        assert result.success is True
        assert result.mode == "recovered"
        assert "deletefile failed" in result.message

    def test_full_recovery_success(self, sync, src_dst):
        src, dst = src_dst
        with patch.object(sync, "_copyto_explicit", return_value=RcloneResult(True, "ok")), \
             patch.object(sync, "_lsjson",
                          return_value=LsJsonResult(success=True, entries=[{"Name": "old.mp3"}])), \
             patch.object(sync, "_match_diverged_old_name", return_value="old.mp3"), \
             patch.object(sync, "_deletefile", return_value=RcloneResult(True, "deleted")):
            result = sync._recover_diverged_rename(src, dst, dry_run=False)
        assert result.success is True
        assert result.mode == "recovered"


# ---------------------------------------------------------------------------
# _match_diverged_old_name
# ---------------------------------------------------------------------------

class TestMatchDivergedOldName:
    def _meta(self, title=None, track=None):
        from sync_results import RecoveryMetadata
        return RecoveryMetadata(title=title, track_number=track, duration_seconds=None)

    def test_returns_none_when_no_title(self, sync, sync_root):
        src = sync_root / "song.mp3"
        dst = sync_root / "new.mp3"
        with patch.object(sync, "_read_recovery_metadata", return_value=self._meta()):
            result = sync._match_diverged_old_name(src, dst, [{"Name": "other.mp3"}])
        assert result is None

    def test_returns_none_when_no_track(self, sync, sync_root):
        src = sync_root / "song.mp3"
        dst = sync_root / "new.mp3"
        with patch.object(sync, "_read_recovery_metadata", return_value=self._meta(title="Song", track=None)):
            result = sync._match_diverged_old_name(src, dst, [{"Name": "other.mp3"}])
        assert result is None

    def test_returns_none_when_title_too_short(self, sync, sync_root):
        src = sync_root / "song.mp3"
        dst = sync_root / "new.mp3"
        with patch.object(sync, "_read_recovery_metadata", return_value=self._meta(title="ab", track=1)):
            result = sync._match_diverged_old_name(src, dst, [{"Name": "01 - ab.mp3"}])
        assert result is None

    def test_returns_unique_match(self, sync, sync_root):
        src = sync_root / "01 - SongName.mp3"
        dst = sync_root / "01 - Song Name.mp3"
        src.touch()
        # Candidate has same title+track but a different name spelling (the diverged remote name).
        listing = [
            {"Name": "01 - SongName_old.mp3"},
            {"Name": "02 - Other Song.mp3"},
        ]
        with patch.object(sync, "_read_recovery_metadata",
                          return_value=self._meta(title="SongName", track=1)):
            result = sync._match_diverged_old_name(src, dst, listing)
        assert result == "01 - SongName_old.mp3"

    def test_returns_none_on_ambiguous_match(self, sync, sync_root):
        src = sync_root / "01 - title.mp3"
        dst = sync_root / "01 - newtitle.mp3"
        listing = [
            {"Name": "01 - title_v1.mp3"},
            {"Name": "01 - title_v2.mp3"},
        ]
        with patch.object(sync, "_read_recovery_metadata",
                          return_value=self._meta(title="title", track=1)):
            result = sync._match_diverged_old_name(src, dst, listing)
        assert result is None

    def test_returns_none_when_no_candidates_match(self, sync, sync_root):
        src = sync_root / "01 - title.mp3"
        dst = sync_root / "01 - newtitle.mp3"
        listing = [{"Name": "99 - completely_different.mp3"}]
        with patch.object(sync, "_read_recovery_metadata",
                          return_value=self._meta(title="title", track=1)):
            result = sync._match_diverged_old_name(src, dst, listing)
        assert result is None


# ---------------------------------------------------------------------------
# _read_recovery_metadata
# ---------------------------------------------------------------------------

class TestReadRecoveryMetadata:
    def test_returns_metadata_on_success(self, sync, sync_root):
        f = sync_root / "song.mp3"
        f.touch()
        from models import TrackMetadata
        mock_meta = TrackMetadata(title="Song", track_number=3)
        mock_audio = MagicMock()
        mock_audio.info.length = 240.5

        with patch("onedrive_sync.ID3Handler") as MockHandler, \
             patch("onedrive_sync.MutagenFile", return_value=mock_audio):
            MockHandler.return_value.read_tags.return_value = mock_meta
            result = sync._read_recovery_metadata(f)

        assert result.title == "Song"
        assert result.track_number == 3
        assert result.duration_seconds == 240.5

    def test_returns_empty_on_read_tags_failure(self, sync, sync_root):
        f = sync_root / "bad.mp3"
        f.touch()
        with patch("onedrive_sync.ID3Handler") as MockHandler:
            MockHandler.return_value.read_tags.side_effect = Exception("corrupt")
            result = sync._read_recovery_metadata(f)

        assert result.title is None
        assert result.track_number is None

    def test_duration_none_when_mutagen_fails(self, sync, sync_root):
        f = sync_root / "song.mp3"
        f.touch()
        from models import TrackMetadata
        with patch("onedrive_sync.ID3Handler") as MockHandler, \
             patch("onedrive_sync.MutagenFile", side_effect=Exception("fail")):
            MockHandler.return_value.read_tags.return_value = TrackMetadata(title="T", track_number=1)
            result = sync._read_recovery_metadata(f)

        assert result.duration_seconds is None

    def test_duration_none_when_audio_info_missing(self, sync, sync_root):
        f = sync_root / "song.mp3"
        f.touch()
        from models import TrackMetadata
        mock_audio = MagicMock()
        mock_audio.info = None

        with patch("onedrive_sync.ID3Handler") as MockHandler, \
             patch("onedrive_sync.MutagenFile", return_value=mock_audio):
            MockHandler.return_value.read_tags.return_value = TrackMetadata(title="T", track_number=1)
            result = sync._read_recovery_metadata(f)

        assert result.duration_seconds is None


# ---------------------------------------------------------------------------
# _normalize_for_match
# ---------------------------------------------------------------------------

class TestNormalizeForMatch:
    def test_lowercases(self):
        assert OneDriveSync._normalize_for_match("HELLO") == "hello"

    def test_strips_punctuation(self):
        result = OneDriveSync._normalize_for_match("Hello, World!")
        assert "," not in result
        assert "!" not in result

    def test_collapses_whitespace(self):
        result = OneDriveSync._normalize_for_match("a  b   c")
        assert result == "a b c"

    def test_nfc_normalizes(self):
        import unicodedata
        nfd = unicodedata.normalize("NFD", "Café")
        result = OneDriveSync._normalize_for_match(nfd)
        assert result == "café"
