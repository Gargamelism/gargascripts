"""Tests for skipped-file tracking and end-of-run review."""

import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive import InteractivePrompts
from models import (
    AudioFile,
    TrackMetadata,
    ProcessingStats,
    ConfirmAction,
    NoACRMatchAction,
)
from processor import ID3Processor
from processor import dispatch as _dispatch
from processor import finalize as _finalize


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def args():
    return Namespace(
        path="/test/path",
        recursive=False,
        include_root=False,
        start_at=None,
        dry_run=False,
        yes=False,
        force=False,
        skip_acr=True,
        skip_discogs=True,
        no_rename=True,
        no_file_rename=True,
        rename_only=False,
        env_file=".env",
        no_color=True,
        quiet=True,
        mirror_onedrive=False,
        onedrive_root=None,
        onedrive_remote="onedrive:",
        rclone_path=None,
    )


@pytest.fixture
def config():
    return {
        "acrcloud_host": "host",
        "acrcloud_access_key": "k",
        "acrcloud_access_secret": "s",
        "discogs_user_token": "tok",
    }


@pytest.fixture
def prompts():
    p = Mock(spec=InteractivePrompts)
    p.print = Mock()
    p.show_progress = Mock()
    p.show_file_comparison = Mock()
    p.show_summary = Mock()
    p.confirm_tag_changes = Mock(return_value=ConfirmAction.SKIP)
    p.review_skipped_files = Mock()
    return p


def _af(title="Song", track=1, path=None, with_proposed=False):
    current = TrackMetadata(title=title, artist="A", album="B", track_number=track)
    proposed = (
        TrackMetadata(title=f"New {title}", artist="A", album="B", track_number=track)
        if with_proposed
        else None
    )
    return AudioFile(
        file_path=path or f"/fake/{title}.mp3",
        format="mp3",
        current_tags=current,
        proposed_tags=proposed,
    )


# ---------------------------------------------------------------------------
# ProcessingStats.skipped_files
# ---------------------------------------------------------------------------


class TestProcessingStatsSkippedFiles:
    def test_defaults_to_empty_list(self):
        stats = ProcessingStats()
        assert stats.skipped_files == []

    def test_can_append_audio_files(self):
        stats = ProcessingStats()
        af = _af()
        stats.skipped_files.append(af)
        assert af in stats.skipped_files
        assert stats.files_skipped == 1  # property returns len(skipped_files)

    def test_independent_across_instances(self):
        a, b = ProcessingStats(), ProcessingStats()
        a.skipped_files.append(_af())
        assert b.skipped_files == []


# ---------------------------------------------------------------------------
# Skip tracking in dispatch (representative path: NoACRMatchAction.SKIP)
# ---------------------------------------------------------------------------


class TestDispatchSkipTracking:
    def _make_proc(self, config, args, prompts):
        proc = ID3Processor(config, args, prompts)
        acr = Mock()
        acr.recognize_with_retry.return_value = None
        proc.acr_client = acr
        proc.discogs_client = None
        prompts.handle_no_acr_match.return_value = NoACRMatchAction.SKIP
        return proc

    def test_skip_action_appends_to_skipped_files(self, config, args, prompts):
        proc = self._make_proc(config, args, prompts)
        af = _af(track=None)  # incomplete → needs_processing=True
        _dispatch.process_single_file_obj(proc, af)
        assert af in proc.stats.skipped_files

    def test_skip_action_increments_counter(self, config, args, prompts):
        proc = self._make_proc(config, args, prompts)
        _dispatch.process_single_file_obj(proc, _af(track=None))
        assert proc.stats.files_skipped == 1

    def test_confirm_skip_extends_skipped_files(self, config, args, prompts):
        """User skips the confirm-changes prompt → files added to skipped_files."""
        proc = ID3Processor(config, args, prompts)
        files = [
            _af(title="T1", with_proposed=True),
            _af(title="T2", path="/f/t2.mp3", with_proposed=True),
        ]
        prompts.confirm_tag_changes.return_value = ConfirmAction.SKIP

        with patch.object(_finalize, "apply_tag_changes"):
            _dispatch.process_files(proc, files)

        assert set(files).issubset(set(proc.stats.skipped_files))


# ---------------------------------------------------------------------------
# review_skipped_files UI (interactive/editing.py)
# ---------------------------------------------------------------------------


class TestReviewSkippedFilesUI:
    """Tests for the interactive.editing.review_skipped_files function."""

    @pytest.fixture
    def ui(self):
        return InteractivePrompts(no_color=True)

    def test_done_immediately_on_d(self, ui, capsys):
        files = [_af()]
        with patch("builtins.input", return_value="d"):
            ui.review_skipped_files(files)
        out = capsys.readouterr().out
        assert "Song" in out

    def test_invalid_input_then_done(self, ui):
        files = [_af()]
        with patch("builtins.input", side_effect=["999", "d"]):
            ui.review_skipped_files(files)

    def test_selects_file_and_calls_edit(self, ui):
        files = [_af()]
        with (
            patch("builtins.input", side_effect=["1", "d"]),
            patch.object(ui, "_edit_track_fields") as mock_edit,
        ):
            ui.review_skipped_files(files)
        mock_edit.assert_called_once_with(files[0])

    def test_seeds_proposed_tags_when_none(self, ui):
        af = _af(with_proposed=False)
        assert af.proposed_tags is None
        with (
            patch("builtins.input", side_effect=["1", "d"]),
            patch.object(ui, "_edit_track_fields"),
        ):
            ui.review_skipped_files([af])
        assert af.proposed_tags is not None
        assert af.proposed_tags.title == af.current_tags.title

    def test_does_not_overwrite_existing_proposed_tags(self, ui):
        af = _af(with_proposed=True)
        original_proposed = af.proposed_tags
        with (
            patch("builtins.input", side_effect=["1", "d"]),
            patch.object(ui, "_edit_track_fields"),
        ):
            ui.review_skipped_files([af])
        assert af.proposed_tags is original_proposed

    def test_lists_all_skipped_files(self, ui, capsys):
        files = [
            _af("Alpha"),
            _af("Beta", path="/f/b.mp3"),
            _af("Gamma", path="/f/g.mp3"),
        ]
        with patch("builtins.input", return_value="d"):
            ui.review_skipped_files(files)
        out = capsys.readouterr().out
        assert "Alpha" in out
        assert "Beta" in out
        assert "Gamma" in out

    def test_loops_back_after_edit(self, ui, capsys):
        files = [_af("T1"), _af("T2", path="/f/t2.mp3")]
        with (
            patch("builtins.input", side_effect=["1", "2", "d"]),
            patch.object(ui, "_edit_track_fields"),
        ):
            ui.review_skipped_files(files)
        # header printed on each loop — appears at least twice
        out = capsys.readouterr().out
        assert out.count("Skipped files") >= 2


# ---------------------------------------------------------------------------
# _review_skipped_files processor method
# ---------------------------------------------------------------------------


class TestReviewSkippedFilesProcessor:
    def _proc(self, config, args, prompts):
        return ID3Processor(config, args, prompts)

    def test_skips_review_when_no_skipped_files(self, config, args, prompts):
        proc = self._proc(config, args, prompts)
        proc._review_skipped_files()
        prompts.review_skipped_files.assert_not_called()

    def test_calls_review_with_skipped_files(self, config, args, prompts):
        proc = self._proc(config, args, prompts)
        af = _af()
        proc.stats.skipped_files.append(af)
        proc._review_skipped_files()
        prompts.review_skipped_files.assert_called_once_with([af])

    def test_no_apply_when_no_changes_after_review(self, config, args, prompts):
        proc = self._proc(config, args, prompts)
        proc.stats.skipped_files.append(_af())  # no proposed_tags → no actual changes
        with patch.object(_finalize, "apply_tag_changes") as mock_apply:
            proc._review_skipped_files()
        mock_apply.assert_not_called()

    def test_applies_tags_when_file_edited_and_confirmed(self, config, args, prompts):
        proc = self._proc(config, args, prompts)
        af = _af(with_proposed=True)  # proposed != current → has_actual_changes
        proc.stats.skipped_files.append(af)
        prompts.confirm_tag_changes.return_value = ConfirmAction.APPLY

        with patch.object(_finalize, "apply_tag_changes") as mock_apply:
            proc._review_skipped_files()

        mock_apply.assert_called_once_with(proc, [af])
        prompts.show_file_comparison.assert_called_once_with(af)

    def test_no_apply_when_user_skips_confirm(self, config, args, prompts):
        proc = self._proc(config, args, prompts)
        af = _af(with_proposed=True)
        proc.stats.skipped_files.append(af)
        prompts.confirm_tag_changes.return_value = ConfirmAction.SKIP

        with patch.object(_finalize, "apply_tag_changes") as mock_apply:
            proc._review_skipped_files()

        mock_apply.assert_not_called()

    def test_exits_on_quit(self, config, args, prompts):
        proc = self._proc(config, args, prompts)
        af = _af(with_proposed=True)
        proc.stats.skipped_files.append(af)
        prompts.confirm_tag_changes.return_value = ConfirmAction.QUIT

        with (
            patch.object(_finalize, "apply_tag_changes"),
            pytest.raises(SystemExit),
        ):
            proc._review_skipped_files()
