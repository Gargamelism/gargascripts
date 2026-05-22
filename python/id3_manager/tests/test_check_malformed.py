"""Tests for check_malformed.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import check_malformed
from check_malformed import main


class TestUsageError:
    def test_exits_1_with_no_args(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["check_malformed.py"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_usage_message_contains_script_name(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["myscript.py"])
        with pytest.raises(SystemExit):
            main()
        out = capsys.readouterr().out
        assert "myscript.py" in out


class TestCleanRun:
    def test_prints_no_malformed_when_all_ok(self, monkeypatch, capsys, tmp_path):
        mp3 = tmp_path / "song.mp3"
        mp3.touch()

        monkeypatch.setattr(sys, "argv", ["check_malformed.py", str(tmp_path)])

        with patch("check_malformed.ID3Handler.is_supported", return_value=True), \
             patch("check_malformed.ID3Handler.read_tags", return_value=MagicMock()):
            main()

        out = capsys.readouterr().out
        assert "No malformed files found." in out

    def test_skips_non_supported_files(self, monkeypatch, capsys, tmp_path):
        txt = tmp_path / "readme.txt"
        txt.touch()

        monkeypatch.setattr(sys, "argv", ["check_malformed.py", str(tmp_path)])

        with patch("check_malformed.ID3Handler.is_supported", return_value=False):
            main()

        out = capsys.readouterr().out
        assert "No malformed files found." in out


class TestMalformedFiles:
    def test_reports_error_files(self, monkeypatch, capsys, tmp_path):
        mp3 = tmp_path / "bad.mp3"
        mp3.touch()

        monkeypatch.setattr(sys, "argv", ["check_malformed.py", str(tmp_path)])

        with patch("check_malformed.ID3Handler.is_supported", return_value=True), \
             patch("check_malformed.ID3Handler.read_tags",
                   side_effect=Exception("can't sync to MPEG frame")):
            main()

        out = capsys.readouterr().out
        assert "Found 1 malformed file(s):" in out
        assert "bad.mp3" in out
        assert "can't sync to MPEG frame" in out

    def test_reports_relative_path(self, monkeypatch, capsys, tmp_path):
        sub = tmp_path / "albums" / "test"
        sub.mkdir(parents=True)
        mp3 = sub / "broken.mp3"
        mp3.touch()

        monkeypatch.setattr(sys, "argv", ["check_malformed.py", str(tmp_path)])

        with patch("check_malformed.ID3Handler.is_supported", return_value=True), \
             patch("check_malformed.ID3Handler.read_tags",
                   side_effect=Exception("bad file")):
            main()

        out = capsys.readouterr().out
        # Should be relative not absolute
        assert str(tmp_path) not in out
        assert "albums" in out

    def test_reports_multiple_errors(self, monkeypatch, capsys, tmp_path):
        for name in ["a.mp3", "b.mp3", "c.mp3"]:
            (tmp_path / name).touch()

        monkeypatch.setattr(sys, "argv", ["check_malformed.py", str(tmp_path)])

        with patch("check_malformed.ID3Handler.is_supported", return_value=True), \
             patch("check_malformed.ID3Handler.read_tags",
                   side_effect=Exception("broken")):
            main()

        out = capsys.readouterr().out
        assert "Found 3 malformed file(s):" in out
