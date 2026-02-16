"""Tests for interactive.py utility functions and non-input logic."""

import sys
from pathlib import Path
from io import StringIO
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive import InteractivePrompts
from models import TrackMetadata, AudioFile, ProcessingStats, ACRCloudResult


@pytest.fixture
def prompts():
    """Create InteractivePrompts instance with no color."""
    return InteractivePrompts(no_color=True)


@pytest.fixture
def prompts_auto_yes():
    """Create InteractivePrompts instance with auto_yes enabled."""
    return InteractivePrompts(no_color=True, auto_yes=True)


@pytest.fixture
def prompts_quiet():
    """Create InteractivePrompts instance with quiet mode."""
    return InteractivePrompts(no_color=True, quiet=True)


class TestInitialization:
    """Tests for InteractivePrompts initialization."""

    def test_default_settings(self):
        """Should initialize with default settings."""
        prompts = InteractivePrompts()
        assert prompts.no_color is False
        assert prompts.auto_yes is False
        assert prompts.quiet is False

    def test_no_color_disables_all_colors(self):
        """Should set all color codes to empty strings when no_color is True."""
        prompts = InteractivePrompts(no_color=True)
        for color in prompts.COLORS.values():
            assert color == ""

    def test_colors_enabled_by_default(self):
        """Should have color codes when no_color is False."""
        prompts = InteractivePrompts(no_color=False)
        assert prompts.COLORS["reset"] == "\033[0m"
        assert prompts.COLORS["bold"] == "\033[1m"
        assert prompts.COLORS["green"] == "\033[92m"


class TestColorMethod:
    """Tests for _c color method."""

    def test_applies_color_when_enabled(self):
        """Should wrap text with color codes."""
        prompts = InteractivePrompts(no_color=False)
        result = prompts._c("green", "test")
        assert "\033[92m" in result
        assert "test" in result
        assert "\033[0m" in result

    def test_no_color_returns_plain_text(self, prompts):
        """Should return plain text when no_color is True."""
        result = prompts._c("green", "test")
        assert result == "test"

    def test_handles_unknown_color(self, prompts):
        """Should handle unknown color gracefully."""
        result = prompts._c("nonexistent", "test")
        assert "test" in result


class TestPrintMethod:
    """Tests for print method."""

    def test_prints_in_normal_mode(self, prompts, capsys):
        """Should print output in normal mode."""
        prompts.print("test message")
        captured = capsys.readouterr()
        assert "test message" in captured.out

    def test_suppresses_output_in_quiet_mode(self, prompts_quiet, capsys):
        """Should suppress output in quiet mode."""
        prompts_quiet.print("test message")
        captured = capsys.readouterr()
        assert captured.out == ""


class TestAutoYesBehavior:
    """Tests for auto_yes mode behavior."""

    def test_confirm_tag_changes_returns_apply(self, prompts_auto_yes):
        """Should return 'apply' in auto_yes mode without prompting."""
        from models import AudioFile, TrackMetadata
        files = [
            AudioFile(
                file_path="/fake/song.mp3",
                format="mp3",
                current_tags=TrackMetadata(),
                proposed_tags=TrackMetadata(title="Test"),
            )
        ]
        result = prompts_auto_yes.confirm_tag_changes(files)
        assert result == "apply"

    def test_confirm_folder_rename_returns_true(self, prompts_auto_yes):
        """Should return True in auto_yes mode."""
        result = prompts_auto_yes.confirm_folder_rename("Old", "New")
        assert result is True

    def test_confirm_file_renames_returns_true(self, prompts_auto_yes):
        """Should return True in auto_yes mode."""
        renames = [("/path/old.mp3", "new.mp3")]
        result = prompts_auto_yes.confirm_file_renames(renames)
        assert result is True

    def test_show_discogs_candidates_selects_first(self, prompts_auto_yes):
        """Should select first release in auto_yes mode."""
        from models import DiscogsRelease, DiscogsTrack
        releases = [
            DiscogsRelease(
                release_id=1,
                title="First",
                artists=["Artist"],
                year=2020,
                tracklist=[],
                total_discs=1,
            ),
            DiscogsRelease(
                release_id=2,
                title="Second",
                artists=["Artist"],
                year=2020,
                tracklist=[],
                total_discs=1,
            ),
        ]
        result = prompts_auto_yes.show_discogs_candidates(releases)
        assert result == 0


class TestGetDiscogsUrlOrId:
    """Tests for get_discogs_url_or_id method."""

    def test_parses_full_url(self, prompts):
        """Should extract release ID from full URL."""
        with patch('builtins.input', return_value="https://www.discogs.com/release/12345-Artist-Album"):
            result = prompts.get_discogs_url_or_id()
            assert result == 12345

    def test_parses_short_url(self, prompts):
        """Should extract release ID from short URL."""
        with patch('builtins.input', return_value="https://www.discogs.com/release/12345"):
            result = prompts.get_discogs_url_or_id()
            assert result == 12345

    def test_parses_just_id(self, prompts):
        """Should extract release ID when just number is provided."""
        with patch('builtins.input', return_value="12345"):
            result = prompts.get_discogs_url_or_id()
            assert result == 12345

    def test_returns_none_for_empty_input(self, prompts):
        """Should return None for empty input."""
        with patch('builtins.input', return_value=""):
            result = prompts.get_discogs_url_or_id()
            assert result is None

    def test_returns_none_for_invalid_input(self, prompts):
        """Should return None for invalid input."""
        with patch('builtins.input', return_value="not-a-valid-url-or-id"):
            result = prompts.get_discogs_url_or_id()
            assert result is None


class TestPromptMissingFields:
    """Tests for prompt_missing_fields method."""

    def test_returns_metadata_when_complete(self, prompts):
        """Should return metadata unchanged when all required fields present."""
        metadata = TrackMetadata(
            title="Song",
            artist="Artist",
            album="Album",
            track_number=1,
        )
        result = prompts.prompt_missing_fields(metadata, "test.mp3")
        assert result == metadata

    def test_auto_yes_skips_incomplete_metadata(self, prompts_auto_yes):
        """Should return None in auto_yes mode when required fields are missing."""
        metadata = TrackMetadata(title="Song")  # Missing artist, album, track_number
        result = prompts_auto_yes.prompt_missing_fields(metadata, "test.mp3")
        assert result is None  # Cannot proceed without required fields in auto mode


class TestShowProgress:
    """Tests for show_progress method."""

    def test_shows_progress_bar(self, prompts, capsys):
        """Should display progress bar."""
        prompts.show_progress(5, 10, "test.mp3")
        captured = capsys.readouterr()
        assert "50.0%" in captured.out
        assert "5/10" in captured.out

    def test_shows_100_percent_at_completion(self, prompts, capsys):
        """Should show 100% at completion."""
        prompts.show_progress(10, 10, "done")
        captured = capsys.readouterr()
        assert "100.0%" in captured.out

    def test_quiet_mode_suppresses_progress(self, prompts_quiet, capsys):
        """Should not show progress in quiet mode."""
        prompts_quiet.show_progress(5, 10, "test.mp3")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_handles_zero_total(self, prompts, capsys):
        """Should handle zero total gracefully."""
        prompts.show_progress(0, 0, "")
        captured = capsys.readouterr()
        # Should not crash, just show 0%
        assert "0.0%" in captured.out


class TestShowSummary:
    """Tests for show_summary method."""

    def test_displays_all_stats(self, prompts, capsys):
        """Should display all processing statistics."""
        stats = ProcessingStats()
        stats.total_files = 10
        stats.tags_updated = 5
        stats.files_skipped = 2
        stats.acr_lookups = 8
        stats.discogs_lookups = 6
        stats.folders_renamed = 1

        prompts.show_summary(stats)
        captured = capsys.readouterr()

        assert "10" in captured.out  # total_files
        assert "5" in captured.out   # tags_updated
        assert "2" in captured.out   # files_skipped

    def test_displays_malformed_files(self, prompts, capsys):
        """Should display malformed files list."""
        stats = ProcessingStats()
        stats.malformed_files = ["/path/bad1.mp3", "/path/bad2.mp3"]

        prompts.show_summary(stats)
        captured = capsys.readouterr()

        assert "Malformed files" in captured.out
        assert "bad1.mp3" in captured.out
        assert "bad2.mp3" in captured.out

    def test_displays_errors(self, prompts, capsys):
        """Should display error messages."""
        stats = ProcessingStats()
        stats.errors = ["Error 1", "Error 2"]

        prompts.show_summary(stats)
        captured = capsys.readouterr()

        assert "Errors" in captured.out
        assert "Error 1" in captured.out


class TestShowAcrResult:
    """Tests for show_acr_result method."""

    def test_displays_acr_result(self, prompts, capsys):
        """Should display ACRCloud result."""
        result = ACRCloudResult(
            title="Test Song",
            artists=["Test Artist", "Feat Artist"],
            album="Test Album",
            confidence=0.95,
        )
        prompts.show_acr_result(result)
        captured = capsys.readouterr()

        assert "Test Song" in captured.out
        assert "Test Artist" in captured.out
        assert "Test Album" in captured.out
        assert "95%" in captured.out


class TestShowFileComparison:
    """Tests for show_file_comparison method."""

    def test_displays_current_and_proposed(self, prompts, capsys):
        """Should display current and proposed tags side by side."""
        af = AudioFile(
            file_path="/path/to/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(title="Old Title", artist="Old Artist"),
            proposed_tags=TrackMetadata(title="New Title", artist="New Artist"),
        )
        prompts.show_file_comparison(af)
        captured = capsys.readouterr()

        assert "song.mp3" in captured.out
        assert "Old Title" in captured.out or "(empty)" in captured.out
        assert "New Title" in captured.out


class TestConfirmFileRenames:
    """Tests for confirm_file_renames method."""

    def test_returns_true_for_empty_list(self, prompts):
        """Should return True for empty rename list."""
        result = prompts.confirm_file_renames([])
        assert result is True


class TestPromptChoice:
    """Tests for _prompt_choice helper method."""

    def test_accepts_y(self, prompts):
        """Should return mapped value for 'y' input."""
        with patch('builtins.input', return_value="y"):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "yes": True, "n": False, "no": False},
                default=False,
            )
            assert result is True

    def test_accepts_yes(self, prompts):
        """Should return mapped value for 'yes' input."""
        with patch('builtins.input', return_value="yes"):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "yes": True, "n": False, "no": False},
                default=False,
            )
            assert result is True

    def test_case_insensitive(self, prompts):
        """Should handle uppercase input."""
        with patch('builtins.input', return_value="Y"):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "yes": True, "n": False, "no": False},
                default=False,
            )
            assert result is True

    def test_accepts_n(self, prompts):
        """Should return mapped value for 'n' input."""
        with patch('builtins.input', return_value="n"):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "yes": True, "n": False, "no": False},
                default=False,
            )
            assert result is False

    def test_accepts_no(self, prompts):
        """Should return mapped value for 'no' input."""
        with patch('builtins.input', return_value="no"):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "yes": True, "n": False, "no": False},
                default=False,
            )
            assert result is False

    def test_empty_input_returns_default(self, prompts):
        """Should return default value for empty input when default is set."""
        with patch('builtins.input', return_value=""):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "yes": True, "n": False, "no": False},
                default=False,
            )
            assert result is False

    def test_empty_input_loops_when_no_default(self, prompts):
        """Should re-prompt when empty input and no default."""
        with patch('builtins.input', side_effect=["", "1"]):
            result = prompts._prompt_choice(
                "Select option:",
                {"1": "manual", "2": "skip"},
            )
            assert result == "manual"

    def test_invalid_input_loops_then_accepts(self, prompts, capsys):
        """Should show error and re-prompt on invalid input."""
        with patch('builtins.input', side_effect=["maybe", "y"]):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "yes": True, "n": False, "no": False},
                default=False,
            )
            assert result is True
            captured = capsys.readouterr()
            assert "Invalid choice" in captured.out

    def test_numbered_choices(self, prompts):
        """Should work with numbered menu options."""
        with patch('builtins.input', return_value="2"):
            result = prompts._prompt_choice(
                "Select option:",
                {"1": "manual", "2": "existing", "3": "skip", "q": "quit"},
            )
            assert result == "existing"

    def test_strips_whitespace(self, prompts):
        """Should strip whitespace from input."""
        with patch('builtins.input', return_value="  y  "):
            result = prompts._prompt_choice(
                "Confirm? [y/N]:",
                {"y": True, "n": False},
                default=False,
            )
            assert result is True


class TestConfirmFileRenamesInput:
    """Tests for confirm_file_renames with various inputs."""

    def test_accepts_yes(self, prompts):
        """Should accept 'yes' as confirmation."""
        renames = [("/path/old.mp3", "new.mp3")]
        with patch('builtins.input', return_value="yes"):
            result = prompts.confirm_file_renames(renames)
            assert result is True

    def test_accepts_y(self, prompts):
        """Should accept 'y' as confirmation."""
        renames = [("/path/old.mp3", "new.mp3")]
        with patch('builtins.input', return_value="y"):
            result = prompts.confirm_file_renames(renames)
            assert result is True

    def test_rejects_n(self, prompts):
        """Should reject with 'n'."""
        renames = [("/path/old.mp3", "new.mp3")]
        with patch('builtins.input', return_value="n"):
            result = prompts.confirm_file_renames(renames)
            assert result is False

    def test_default_is_no(self, prompts):
        """Should default to no on empty input."""
        renames = [("/path/old.mp3", "new.mp3")]
        with patch('builtins.input', return_value=""):
            result = prompts.confirm_file_renames(renames)
            assert result is False


class TestConfirmFolderRenameInput:
    """Tests for confirm_folder_rename with various inputs."""

    def test_accepts_yes(self, prompts):
        """Should accept 'yes' as confirmation."""
        with patch('builtins.input', return_value="yes"):
            result = prompts.confirm_folder_rename("Old", "New")
            assert result is True

    def test_accepts_y(self, prompts):
        """Should accept 'y' as confirmation."""
        with patch('builtins.input', return_value="y"):
            result = prompts.confirm_folder_rename("Old", "New")
            assert result is True

    def test_rejects_no(self, prompts):
        """Should reject with 'no'."""
        with patch('builtins.input', return_value="no"):
            result = prompts.confirm_folder_rename("Old", "New")
            assert result is False

    def test_default_is_no(self, prompts):
        """Should default to no on empty input."""
        with patch('builtins.input', return_value=""):
            result = prompts.confirm_folder_rename("Old", "New")
            assert result is False


class TestGetModifiedSearchQuery:
    """Tests for get_modified_search_query method."""

    def test_returns_defaults_when_empty(self, prompts):
        """Should return default values when user enters empty input."""
        with patch('builtins.input', return_value=""):
            artist, track = prompts.get_modified_search_query("Default Artist", "Default Track")
            assert artist == "Default Artist"
            assert track == "Default Track"

    def test_returns_user_input(self, prompts):
        """Should return user-provided values."""
        inputs = iter(["New Artist", "New Track"])
        with patch('builtins.input', side_effect=lambda _: next(inputs)):
            artist, track = prompts.get_modified_search_query("Default", "Default")
            assert artist == "New Artist"
            assert track == "New Track"
