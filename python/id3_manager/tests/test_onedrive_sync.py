"""Tests for onedrive_sync.OneDriveSync."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from onedrive_sync import OneDriveSync


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
        # "é" as NFD (e + combining acute) should become NFC before sending
        nfd_name = "Café"  # "Café" in NFD
        local = sync_root / nfd_name / "Song.mp3"
        local.parent.mkdir()
        local.touch()
        remote = sync._to_remote(local)
        assert remote == "onedrive:Café/Song.mp3"  # NFC composed form


class TestMoveto:
    def test_skips_when_outside_sync_root(self, sync, tmp_path):
        outside = tmp_path / "elsewhere" / "a.mp3"
        ok, msg = sync.moveto(outside, tmp_path / "elsewhere" / "b.mp3")
        assert ok is True
        assert "outside sync root" in msg

    def test_skips_when_src_equals_dst(self, sync, sync_root):
        p = sync_root / "a.mp3"
        p.touch()
        ok, msg = sync.moveto(p, p)
        assert ok is True
        assert "identical" in msg

    def test_runs_rclone_moveto_on_success(self, sync, sync_root):
        src = sync_root / "old.mp3"
        dst = sync_root / "new.mp3"
        src.touch()
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            ok, msg = sync.moveto(src, dst)
        assert ok is True
        assert run.call_count == 1
        cmd = run.call_args.args[0]
        assert cmd[0] == "/usr/bin/rclone"
        assert cmd[1] == "moveto"
        assert cmd[2] == "onedrive:old.mp3"
        assert cmd[3] == "onedrive:new.mp3"
        assert "--dry-run" not in cmd

    def test_appends_dry_run_flag(self, sync, sync_root):
        src = sync_root / "old.mp3"
        dst = sync_root / "new.mp3"
        src.touch()
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            sync.moveto(src, dst, dry_run=True)
        assert "--dry-run" in run.call_args.args[0]

    def test_returns_failure_on_nonzero_exit(self, sync, sync_root):
        src = sync_root / "old.mp3"
        dst = sync_root / "new.mp3"
        src.touch()
        with patch("subprocess.run") as run:
            run.return_value = MagicMock(returncode=3, stdout="", stderr="directory not found")
            ok, msg = sync.moveto(src, dst)
        assert ok is False
        assert "exit 3" in msg
        assert "directory not found" in msg

    def test_handles_timeout(self, sync, sync_root):
        src = sync_root / "old.mp3"
        dst = sync_root / "new.mp3"
        src.touch()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="", timeout=1)):
            ok, msg = sync.moveto(src, dst)
        assert ok is False
        assert "timed out" in msg

    def test_handles_missing_binary(self, sync, sync_root):
        src = sync_root / "old.mp3"
        dst = sync_root / "new.mp3"
        src.touch()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            ok, msg = sync.moveto(src, dst)
        assert ok is False
        assert "not found" in msg
