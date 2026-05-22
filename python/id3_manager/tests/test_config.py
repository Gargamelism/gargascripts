"""Tests for config.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import eprint, load_config, validate_config, get_discogs_token_instructions, get_acrcloud_instructions


class TestEprint:
    def test_writes_to_stderr(self, capsys):
        eprint("hello stderr")
        err = capsys.readouterr().err
        assert "hello stderr" in err

    def test_does_not_write_to_stdout(self, capsys):
        eprint("only stderr")
        out, err = capsys.readouterr()
        assert out == ""
        assert "only stderr" in err

    def test_forwards_kwargs(self, capsys):
        eprint("a", "b", sep="-")
        err = capsys.readouterr().err
        assert "a-b" in err


class TestLoadConfig:
    def test_returns_all_keys(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("")
        with patch("config.load_dotenv"), \
             patch.dict("os.environ", {
                 "ACRCLOUD_HOST": "h",
                 "ACRCLOUD_ACCESS_KEY": "k",
                 "ACRCLOUD_ACCESS_SECRET": "s",
                 "DISCOGS_USER_TOKEN": "t",
             }, clear=True):
            cfg = load_config(str(env))
        assert cfg["acrcloud_host"] == "h"
        assert cfg["acrcloud_access_key"] == "k"
        assert cfg["acrcloud_access_secret"] == "s"
        assert cfg["discogs_user_token"] == "t"

    def test_missing_env_vars_are_none(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("")
        with patch("config.load_dotenv"), \
             patch.dict("os.environ", {}, clear=True):
            cfg = load_config(str(env))
        assert cfg["acrcloud_host"] is None
        assert cfg["discogs_user_token"] is None

    def test_warns_when_env_file_missing(self, tmp_path, capsys):
        missing = tmp_path / "nonexistent.env"
        with patch.dict("os.environ", {}, clear=True):
            load_config(str(missing))
        err = capsys.readouterr().err
        assert "Warning" in err or "not found" in err or "falling back" in err

    def test_loads_dotenv_when_file_exists(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("DISCOGS_USER_TOKEN=mytoken\n")
        with patch("config.load_dotenv") as mock_ld, \
             patch.dict("os.environ", {"DISCOGS_USER_TOKEN": "mytoken"}, clear=True):
            cfg = load_config(str(env))
        mock_ld.assert_called_once()

    def test_defaults_to_dot_env(self, tmp_path):
        # When env_file=None, it should default to ".env"
        with patch("config.Path") as mock_path, \
             patch("config.load_dotenv"), \
             patch.dict("os.environ", {}, clear=True):
            mock_instance = mock_path.return_value
            mock_instance.exists.return_value = False
            load_config()
        mock_path.assert_called_with(".env")


class TestValidateConfig:
    def _full_config(self):
        return {
            "acrcloud_host": "host",
            "acrcloud_access_key": "key",
            "acrcloud_access_secret": "secret",
            "discogs_user_token": "token",
        }

    def test_no_missing_when_all_present(self):
        missing = validate_config(self._full_config())
        assert missing == []

    def test_reports_missing_acr_keys(self):
        cfg = self._full_config()
        cfg["acrcloud_host"] = None
        cfg["acrcloud_access_key"] = None
        missing = validate_config(cfg)
        assert "ACRCLOUD_HOST" in missing
        assert "ACRCLOUD_ACCESS_KEY" in missing
        assert "ACRCLOUD_ACCESS_SECRET" not in missing

    def test_skip_acr_ignores_acr_keys(self):
        cfg = {
            "acrcloud_host": None,
            "acrcloud_access_key": None,
            "acrcloud_access_secret": None,
            "discogs_user_token": "token",
        }
        missing = validate_config(cfg, skip_acr=True)
        assert missing == []

    def test_reports_missing_discogs_token(self):
        cfg = self._full_config()
        cfg["discogs_user_token"] = None
        missing = validate_config(cfg)
        assert "DISCOGS_USER_TOKEN" in missing

    def test_skip_discogs_ignores_token(self):
        cfg = self._full_config()
        cfg["discogs_user_token"] = None
        missing = validate_config(cfg, skip_discogs=True)
        assert "DISCOGS_USER_TOKEN" not in missing

    def test_all_missing(self):
        cfg = {k: None for k in [
            "acrcloud_host", "acrcloud_access_key",
            "acrcloud_access_secret", "discogs_user_token",
        ]}
        missing = validate_config(cfg)
        assert len(missing) == 4

    def test_empty_string_counts_as_missing(self):
        cfg = self._full_config()
        cfg["acrcloud_host"] = ""
        missing = validate_config(cfg)
        assert "ACRCLOUD_HOST" in missing


class TestInstructions:
    def test_discogs_instructions_non_empty(self):
        text = get_discogs_token_instructions()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_acrcloud_instructions_non_empty(self):
        text = get_acrcloud_instructions()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_discogs_instructions_mention_discogs(self):
        text = get_discogs_token_instructions()
        assert "discogs" in text.lower() or "DISCOGS" in text

    def test_acrcloud_instructions_mention_acrcloud(self):
        text = get_acrcloud_instructions()
        assert "acrcloud" in text.lower() or "ACRCloud" in text
