"""Tests for onedrive_sync.OneDriveSync."""

import subprocess
import sys
import unicodedata
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from onedrive_sync import OneDriveSync, _default_log


@pytest.fixture
def sync_root(tmp_path):
    """A sync root directory on disk so resolve() works."""
    root = tmp_path / "onedrive"
    root.mkdir()
    return root


@pytest.fixture
def sync(sync_root):
    return OneDriveSync(
        local_root=sync_root,
        remote="onedrive:",
        rclone_path="/usr/bin/rclone",
    )


@pytest.fixture
def album_folder(sync_root):
    """A created album folder inside the sync root."""
    folder = sync_root / "Artist" / "Album"
    folder.mkdir(parents=True)
    return folder


class TestDefaultLog:
    def test_prints_message(self, capsys):
        _default_log("hello")
        assert "hello" in capsys.readouterr().out


class TestSyncRoot:
    def test_is_in_sync_root_true_for_child(self, sync, sync_root):
        child = sync_root / "Music" / "Album"
        child.mkdir(parents=True)
        assert sync.is_in_sync_root(child) is True

    def test_is_in_sync_root_false_for_outside(self, sync, tmp_path):
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        assert sync.is_in_sync_root(outside) is False

    def test_remote_has_trailing_colon(self, sync_root):
        s = OneDriveSync(local_root=sync_root, remote="onedrive")
        assert s.remote == "onedrive:"


class TestToRemote:
    def test_maps_to_remote_path(self, sync, sync_root):
        local = sync_root / "Music" / "Artist" / "Song.mp3"
        local.parent.mkdir(parents=True)
        local.touch()
        assert sync._to_remote(local) == "onedrive:Music/Artist/Song.mp3"

    def test_nfc_normalizes_remote_path(self, sync, sync_root):
        # Construct NFD explicitly so this test cannot be defeated by an
        # editor silently re-normalizing the source to NFC. NFD "Café" is
        # 5 codepoints (C, a, f, e, U+0301); NFC is 4 (C, a, f, U+00E9).
        nfd_name = unicodedata.normalize("NFD", "Café")
        nfc_name = unicodedata.normalize("NFC", "Café")
        assert nfd_name != nfc_name  # sanity: the two forms really do differ
        local = sync_root / nfd_name / "Song.mp3"
        local.parent.mkdir()
        local.touch()
        remote = sync._to_remote(local)
        assert remote == "onedrive:" + nfc_name + "/Song.mp3"


class TestSyncFolder:
    def test_skips_when_outside_sync_root(self, sync, tmp_path):
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        result = sync.sync_folder(outside)
        assert result.success is True
        assert "outside sync root" in result.message

    def test_runs_rclone_sync_on_success(self, sync, album_folder):
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = sync.sync_folder(album_folder)
        assert result.success is True
        assert run.call_count == 1
        cmd = run.call_args.args[0]
        assert cmd[0] == "/usr/bin/rclone"
        assert cmd[1] == "sync"
        assert cmd[2] == str(album_folder)
        assert cmd[3] == "onedrive:Artist/Album"
        assert "--track-renames" in cmd
        assert "--checksum" in cmd
        assert "--dry-run" not in cmd

    def test_appends_dry_run_flag(self, sync, album_folder):
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            sync.sync_folder(album_folder, dry_run=True)
        assert "--dry-run" in run.call_args.args[0]

    def test_returns_failure_on_nonzero_exit(self, sync, album_folder):
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(
                returncode=1, stdout="", stderr="permission denied"
            )
            result = sync.sync_folder(album_folder)
        assert result.success is False
        assert "exit 1" in result.message
        assert "permission denied" in result.message

    def test_uses_stdout_when_stderr_empty(self, sync, album_folder):
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(
                returncode=1, stdout="some stdout error", stderr=""
            )
            result = sync.sync_folder(album_folder)
        assert result.success is False
        assert "some stdout error" in result.message

    def test_handles_timeout(self, sync, album_folder):
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="", timeout=1),
        ):
            result = sync.sync_folder(album_folder)
        assert result.success is False
        assert "timed out" in result.message

    def test_handles_missing_binary(self, sync, album_folder):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = sync.sync_folder(album_folder)
        assert result.success is False
        assert "not found" in result.message

    def test_uses_custom_timeout(self, sync, album_folder):
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            sync.sync_folder(album_folder, timeout=999)
        assert run.call_args.kwargs.get("timeout") == 999
