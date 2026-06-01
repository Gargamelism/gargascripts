"""Extra coverage tests for interactive.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from interactive import InteractivePrompts
from models import (
    AudioFile,
    TrackMetadata,
    DiscogsRelease,
    DiscogsTrack,
    ProcessingStats,
    ACRCloudResult,
    ConfirmAction,
    CollisionMap,
    DiscTrack,
    CollisionResolutionAction,
    NoACRMatchAction,
    NoDiscogsMatchAction,
    TrackNotInReleaseAction,
)


@pytest.fixture
def p():
    return InteractivePrompts(no_color=True)


@pytest.fixture
def pq():
    return InteractivePrompts(no_color=True, quiet=True)


@pytest.fixture
def pay():
    return InteractivePrompts(no_color=True, auto_yes=True)


def _af(title="Song", track=1, with_proposed=True):
    current = TrackMetadata(title=title, artist="A", album="B", track_number=track)
    proposed = (
        TrackMetadata(title=f"New {title}", artist="A", album="B", track_number=track)
        if with_proposed
        else None
    )
    return AudioFile(
        file_path=f"/fake/{title}.mp3",
        format="mp3",
        current_tags=current,
        proposed_tags=proposed,
    )


# ---------------------------------------------------------------------------
# show_file_comparison — disc/track branches
# ---------------------------------------------------------------------------


class TestShowFileComparisonBranches:
    def test_shows_disc_info(self, p, capsys):
        af = AudioFile(
            file_path="/path/disc.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                disc_number=1, total_discs=2, track_number=3, total_tracks=10
            ),
            proposed_tags=TrackMetadata(
                disc_number=2, total_discs=2, track_number=3, total_tracks=10
            ),
        )
        p.show_file_comparison(af)
        out = capsys.readouterr().out
        assert "1/2" in out or "2/2" in out

    def test_truncates_long_values(self, p, capsys):
        long_title = "A" * 50
        af = AudioFile(
            file_path="/path/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(title=long_title),
            proposed_tags=TrackMetadata(title="Short"),
        )
        p.show_file_comparison(af)
        out = capsys.readouterr().out
        assert "..." in out

    def test_no_proposed_shows_unchanged(self, p, capsys):
        af = AudioFile(
            file_path="/path/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(title="Title"),
            proposed_tags=None,
        )
        p.show_file_comparison(af)
        out = capsys.readouterr().out
        assert "(unchanged)" in out


# ---------------------------------------------------------------------------
# show_discogs_candidates — interactive loop
# ---------------------------------------------------------------------------


class TestShowDiscogsCandidates:
    def _releases(self, n=2):
        return [
            DiscogsRelease(
                release_id=i,
                title=f"Release {i}",
                artists=["Artist"],
                year=2020,
                tracklist=[
                    DiscogsTrack(
                        position="A1", title="T", track_number=1, disc_number=1
                    )
                ],
                total_discs=1,
                genres=["Rock"],
            )
            for i in range(1, n + 1)
        ]

    def test_returns_index_on_valid_number(self, p):
        with patch("builtins.input", return_value="1"):
            result = p.show_discogs_candidates(self._releases())
        assert result == 0  # index 0 (1-based input → 0-based return)

    def test_returns_none_on_skip(self, p):
        with patch("builtins.input", return_value="s"):
            result = p.show_discogs_candidates(self._releases())
        assert result is None

    def test_returns_manual_url_on_u(self, p):
        with patch("builtins.input", return_value="u"):
            result = p.show_discogs_candidates(self._releases())
        assert result == "manual_url"

    def test_exits_on_q(self, p):
        with patch("builtins.input", return_value="q"), pytest.raises(SystemExit):
            p.show_discogs_candidates(self._releases())

    def test_re_prompts_on_invalid(self, p):
        with patch("builtins.input", side_effect=["bad", "0", "1"]):
            result = p.show_discogs_candidates(self._releases())
        assert result == 0

    def test_release_without_genres(self, p, capsys):
        releases = [
            DiscogsRelease(
                release_id=1,
                title="T",
                artists=["A"],
                year=2020,
                tracklist=[],
                total_discs=1,
                genres=[],
            )
        ]
        with patch("builtins.input", return_value="1"):
            p.show_discogs_candidates(releases)
        # Should not crash; genres line simply not printed


# ---------------------------------------------------------------------------
# confirm_tag_changes — REVIEW / EDIT / ALBUM_EDIT / quit
# ---------------------------------------------------------------------------


class TestConfirmTagChanges:
    def test_returns_skip_on_n(self, p):
        files = [_af()]
        with patch.object(p, "_prompt_choice", return_value=ConfirmAction.SKIP):
            result = p.confirm_tag_changes(files)
        assert result == ConfirmAction.SKIP

    def test_returns_apply_on_y(self, p):
        files = [_af()]
        with patch.object(p, "_prompt_choice", return_value=ConfirmAction.APPLY):
            result = p.confirm_tag_changes(files)
        assert result == ConfirmAction.APPLY

    def test_review_shows_comparisons_then_loops(self, p):
        files = [_af()]
        choices = iter([ConfirmAction.REVIEW, ConfirmAction.APPLY])
        with (
            patch.object(
                p, "_prompt_choice", side_effect=lambda *a, **kw: next(choices)
            ),
            patch.object(p, "show_file_comparison") as mock_show,
        ):
            result = p.confirm_tag_changes(files)
        mock_show.assert_called()
        assert result == ConfirmAction.APPLY

    def test_edit_calls_handle_edit_track(self, p):
        files = [_af()]
        choices = iter([ConfirmAction.EDIT, ConfirmAction.APPLY])
        with (
            patch.object(
                p, "_prompt_choice", side_effect=lambda *a, **kw: next(choices)
            ),
            patch.object(p, "_handle_edit_track") as mock_edit,
            patch.object(p, "show_file_comparison"),
        ):
            p.confirm_tag_changes(files)
        mock_edit.assert_called_once()

    def test_album_edit_calls_handle_edit_album(self, p):
        files = [_af()]
        choices = iter([ConfirmAction.ALBUM_EDIT, ConfirmAction.APPLY])
        with (
            patch.object(
                p, "_prompt_choice", side_effect=lambda *a, **kw: next(choices)
            ),
            patch.object(p, "_handle_edit_album") as mock_alb,
            patch.object(p, "show_file_comparison"),
        ):
            p.confirm_tag_changes(files)
        mock_alb.assert_called_once()

    def test_returns_quit(self, p):
        files = [_af()]
        with patch.object(p, "_prompt_choice", return_value=ConfirmAction.QUIT):
            result = p.confirm_tag_changes(files)
        assert result == ConfirmAction.QUIT


# ---------------------------------------------------------------------------
# _handle_edit_track
# ---------------------------------------------------------------------------


class TestHandleEditTrack:
    def test_cancel_returns_immediately(self, p):
        files = [_af()]
        with patch("builtins.input", return_value="c"):
            p._handle_edit_track(files)  # should not raise

    def test_invalid_then_cancel(self, p):
        files = [_af()]
        with patch("builtins.input", side_effect=["bad", "c"]):
            p._handle_edit_track(files)

    def test_selects_and_edits_track(self, p):
        files = [_af("SongA"), _af("SongB")]
        with (
            patch("builtins.input", return_value="1"),
            patch.object(p, "_edit_track_fields") as mock_edit,
        ):
            p._handle_edit_track(files)
        mock_edit.assert_called_once_with(files[0])

    def test_no_editable_files(self, p, capsys):
        files = [_af(with_proposed=False)]
        p._handle_edit_track(files)
        out = capsys.readouterr().out
        assert "No files" in out


# ---------------------------------------------------------------------------
# edit_collision_files
# ---------------------------------------------------------------------------


class TestEditCollisionFiles:
    def _files(self):
        return [_af("ColA"), _af("ColB")]

    def test_cancel_on_c(self, p):
        files = self._files()
        collision: CollisionMap = {DiscTrack(1, 1): files}
        with patch("builtins.input", return_value="c"):
            p.edit_collision_files(collision)

    def test_edits_selected_file(self, p):
        files = self._files()
        collision: CollisionMap = {DiscTrack(1, 1): files}
        with (
            patch("builtins.input", return_value="1"),
            patch.object(p, "_edit_track_fields") as mock_edit,
        ):
            p.edit_collision_files(collision)
        mock_edit.assert_called_once()

    def test_seeds_proposed_tags_if_none(self, p):
        af = _af(with_proposed=False)
        collision: CollisionMap = {DiscTrack(1, 1): [af]}
        with (
            patch("builtins.input", return_value="1"),
            patch.object(p, "_edit_track_fields"),
        ):
            p.edit_collision_files(collision)
        assert af.proposed_tags is not None

    def test_invalid_then_cancel(self, p):
        files = self._files()
        collision: CollisionMap = {DiscTrack(1, 1): files}
        with patch("builtins.input", side_effect=["999", "c"]):
            p.edit_collision_files(collision)


# ---------------------------------------------------------------------------
# _handle_edit_album
# ---------------------------------------------------------------------------


class TestHandleEditAlbum:
    def test_done_on_x(self, p):
        files = [_af()]
        with patch("builtins.input", return_value="x"):
            p._handle_edit_album(files)

    def test_no_editable_files(self, p, capsys):
        p._handle_edit_album([_af(with_proposed=False)])
        out = capsys.readouterr().out
        assert "No files" in out

    def test_edits_string_field(self, p):
        files = [_af()]
        # 'b' = Album field; then 'x' to quit
        with patch("builtins.input", side_effect=["b", "New Album", "x"]):
            p._handle_edit_album(files)
        assert files[0].proposed_tags.album == "New Album"

    def test_edits_int_field(self, p):
        files = [_af()]
        # 'y' = Year (int); then 'x'
        with patch("builtins.input", side_effect=["y", "2023", "x"]):
            p._handle_edit_album(files)
        assert files[0].proposed_tags.year == 2023

    def test_invalid_int_does_not_change(self, p):
        files = [_af()]
        original_year = files[0].proposed_tags.year
        with patch("builtins.input", side_effect=["y", "notanumber", "x"]):
            p._handle_edit_album(files)
        assert files[0].proposed_tags.year == original_year

    def test_invalid_choice_loops(self, p):
        files = [_af()]
        with patch("builtins.input", side_effect=["Z", "x"]):
            p._handle_edit_album(files)

    def test_empty_input_keeps_existing(self, p):
        files = [_af()]
        files[0].proposed_tags.album = "Existing"
        with patch("builtins.input", side_effect=["b", "", "x"]):
            p._handle_edit_album(files)
        assert files[0].proposed_tags.album == "Existing"

    def test_empty_clears_when_no_existing(self, p):
        files = [_af()]
        files[0].proposed_tags.year = None
        with patch("builtins.input", side_effect=["y", "", "x"]):
            p._handle_edit_album(files)
        assert files[0].proposed_tags.year is None


# ---------------------------------------------------------------------------
# _edit_track_fields
# ---------------------------------------------------------------------------


class TestEditTrackFields:
    def test_done_on_x(self, p):
        af = _af()
        with patch("builtins.input", return_value="x"):
            p._edit_track_fields(af)

    def test_no_proposed_tags_returns(self, p, capsys):
        af = _af(with_proposed=False)
        p._edit_track_fields(af)
        out = capsys.readouterr().out
        assert "no proposed tags" in out.lower() or "No proposed" in out

    def test_edits_title(self, p):
        af = _af()
        with patch("builtins.input", side_effect=["t", "Brand New Title", "x"]):
            p._edit_track_fields(af)
        assert af.proposed_tags.title == "Brand New Title"

    def test_edits_track_number_as_int(self, p):
        af = _af()
        with patch("builtins.input", side_effect=["n", "7", "x"]):
            p._edit_track_fields(af)
        assert af.proposed_tags.track_number == 7

    def test_invalid_int_does_not_change(self, p):
        af = _af()
        original = af.proposed_tags.track_number
        with patch("builtins.input", side_effect=["n", "abc", "x"]):
            p._edit_track_fields(af)
        assert af.proposed_tags.track_number == original

    def test_empty_input_clears_when_none_existing(self, p):
        af = _af()
        af.proposed_tags.genre = None
        with patch("builtins.input", side_effect=["g", "", "x"]):
            p._edit_track_fields(af)
        assert af.proposed_tags.genre is None

    def test_empty_input_keeps_existing(self, p):
        af = _af()
        af.proposed_tags.title = "Existing"
        with patch("builtins.input", side_effect=["t", "", "x"]):
            p._edit_track_fields(af)
        assert af.proposed_tags.title == "Existing"

    def test_invalid_choice_loops(self, p):
        af = _af()
        with patch("builtins.input", side_effect=["Z", "x"]):
            p._edit_track_fields(af)


# ---------------------------------------------------------------------------
# handle_no_acr_match
# ---------------------------------------------------------------------------


class TestHandleNoAcrMatch:
    def test_returns_manual(self, p):
        with patch.object(p, "_prompt_choice", return_value=NoACRMatchAction.MANUAL):
            result = p.handle_no_acr_match("/path/file.mp3")
        assert result == NoACRMatchAction.MANUAL

    def test_returns_skip(self, p):
        with patch("builtins.input", return_value="3"):
            result = p.handle_no_acr_match("/path/file.mp3")
        assert result == NoACRMatchAction.SKIP

    def test_returns_quit(self, p):
        with patch("builtins.input", return_value="q"):
            result = p.handle_no_acr_match("/path/file.mp3")
        assert result == NoACRMatchAction.QUIT


# ---------------------------------------------------------------------------
# handle_no_discogs_match
# ---------------------------------------------------------------------------


class TestHandleNoDiscogsMatch:
    def _acr(self):
        return ACRCloudResult(title="Song", artists=["Artist"], confidence=0.9)

    def test_returns_acr_only(self, p):
        with patch("builtins.input", return_value="1"):
            result = p.handle_no_discogs_match(self._acr())
        assert result == NoDiscogsMatchAction.ACR_ONLY

    def test_returns_retry(self, p):
        with patch("builtins.input", return_value="2"):
            result = p.handle_no_discogs_match(self._acr())
        assert result == NoDiscogsMatchAction.RETRY

    def test_returns_manual_url(self, p):
        with patch("builtins.input", return_value="3"):
            result = p.handle_no_discogs_match(self._acr())
        assert result == NoDiscogsMatchAction.MANUAL_URL

    def test_returns_manual(self, p):
        with patch("builtins.input", return_value="4"):
            result = p.handle_no_discogs_match(self._acr())
        assert result == NoDiscogsMatchAction.MANUAL

    def test_returns_skip(self, p):
        with patch("builtins.input", return_value="5"):
            result = p.handle_no_discogs_match(self._acr())
        assert result == NoDiscogsMatchAction.SKIP


# ---------------------------------------------------------------------------
# get_manual_metadata
# ---------------------------------------------------------------------------


class TestGetManualMetadata:
    def test_cancel_when_no_title_or_artist(self, p, capsys):
        with patch("builtins.input", return_value=""):
            result = p.get_manual_metadata()
        assert result is None

    def test_fills_all_fields(self, p):
        inputs = iter(["Title", "Artist", "Album", "2020", "3", "10", "1", "2", "Rock"])
        with (
            patch("builtins.input", side_effect=lambda _: next(inputs)),
            patch.object(p, "prompt_missing_fields", side_effect=lambda m, _: m),
        ):
            result = p.get_manual_metadata()
        assert result is not None
        assert result.title == "Title"

    def test_uses_defaults(self, p):
        defaults = TrackMetadata(
            title="Default Title",
            artist="Default Artist",
            album="Album",
            track_number=1,
        )
        # All Enter — should keep defaults
        with (
            patch("builtins.input", return_value=""),
            patch.object(p, "prompt_missing_fields", side_effect=lambda m, _: m),
        ):
            result = p.get_manual_metadata(defaults)
        assert result.title == "Default Title"


# ---------------------------------------------------------------------------
# prompt_missing_fields — fill / skip loop
# ---------------------------------------------------------------------------


class TestPromptMissingFieldsLoop:
    def test_returns_none_on_skip(self, p):
        meta = TrackMetadata(title=None, artist=None, album="A", track_number=1)
        with patch("builtins.input", side_effect=["2"]):  # "2" = skip
            result = p.prompt_missing_fields(meta, "test.mp3")
        assert result is None

    def test_fills_title(self, p):
        meta = TrackMetadata(title=None, artist="A", album="B", track_number=1)
        # Choice "1" (edit), then title = "NewTitle", then it loops and finds all ok
        with patch("builtins.input", side_effect=["1", "NewTitle"]):
            result = p.prompt_missing_fields(meta, "test.mp3")
        assert result is not None
        assert result.title == "NewTitle"

    def test_fills_artist(self, p):
        meta = TrackMetadata(title="T", artist=None, album="B", track_number=1)
        with patch("builtins.input", side_effect=["1", "NewArtist"]):
            result = p.prompt_missing_fields(meta, "test.mp3")
        assert result.artist == "NewArtist"

    def test_fills_album(self, p):
        meta = TrackMetadata(title="T", artist="A", album=None, track_number=1)
        with patch("builtins.input", side_effect=["1", "NewAlbum"]):
            result = p.prompt_missing_fields(meta, "test.mp3")
        assert result.album == "NewAlbum"

    def test_fills_track_number(self, p):
        meta = TrackMetadata(title="T", artist="A", album="B", track_number=None)
        with patch("builtins.input", side_effect=["1", "5"]):
            result = p.prompt_missing_fields(meta, "test.mp3")
        assert result.track_number == 5

    def test_invalid_track_number_loops(self, p):
        meta = TrackMetadata(title="T", artist="A", album="B", track_number=None)
        # First attempt: invalid number, second attempt: valid
        with patch("builtins.input", side_effect=["1", "bad", "1", "3"]):
            result = p.prompt_missing_fields(meta, "test.mp3")
        assert result.track_number == 3


# ---------------------------------------------------------------------------
# confirm_collision_resolution
# ---------------------------------------------------------------------------


class TestConfirmCollisionResolution:
    def _collision(self):
        af = _af()
        return {DiscTrack(1, 1): [af]}

    def test_auto_yes_returns_skip(self, pay):
        result = pay.confirm_collision_resolution(self._collision())
        assert result == CollisionResolutionAction.SKIP

    def test_returns_edit(self, p):
        with patch("builtins.input", return_value="e"):
            result = p.confirm_collision_resolution(self._collision())
        assert result == CollisionResolutionAction.EDIT

    def test_returns_apply(self, p):
        with patch("builtins.input", return_value="a"):
            result = p.confirm_collision_resolution(self._collision())
        assert result == CollisionResolutionAction.APPLY

    def test_default_is_skip(self, p):
        with patch("builtins.input", return_value=""):
            result = p.confirm_collision_resolution(self._collision())
        assert result == CollisionResolutionAction.SKIP


# ---------------------------------------------------------------------------
# confirm_force_override
# ---------------------------------------------------------------------------


class TestConfirmForceOverride:
    def test_auto_yes_returns_false(self, pay):
        af = _af()
        result = pay.confirm_force_override(
            af, "song.mp3", af.current_tags, af.proposed_tags
        )
        assert result is False

    def test_accept_returns_true(self, p):
        af = _af()
        with patch.object(p, "_prompt_choice", return_value="accept"):
            result = p.confirm_force_override(
                af, "song.mp3", af.current_tags, af.proposed_tags
            )
        assert result is True

    def test_decline_returns_false(self, p):
        af = _af()
        with patch.object(p, "_prompt_choice", return_value="decline"):
            result = p.confirm_force_override(
                af, "song.mp3", af.current_tags, af.proposed_tags
            )
        assert result is False

    def test_edit_calls_edit_track_fields(self, p):
        af = _af()
        choices = iter(["edit", "decline"])
        with (
            patch.object(
                p, "_prompt_choice", side_effect=lambda *a, **kw: next(choices)
            ),
            patch.object(p, "_edit_track_fields"),
        ):
            result = p.confirm_force_override(
                af, "song.mp3", af.current_tags, af.proposed_tags
            )
        assert result is False


# ---------------------------------------------------------------------------
# show_folder_status
# ---------------------------------------------------------------------------


class TestShowFolderStatus:
    def test_shows_folder_info(self, p, capsys):
        p.show_folder_status("/path/to/folder", 15, 8, 3)
        out = capsys.readouterr().out
        assert "15" in out
        assert "8" in out
        assert "3" in out

    def test_shows_folder_path(self, p, capsys):
        p.show_folder_status("/music/album", 5, 2, 1)
        out = capsys.readouterr().out
        assert "/music/album" in out


# ---------------------------------------------------------------------------
# handle_track_not_in_release
# ---------------------------------------------------------------------------


class TestHandleTrackNotInRelease:
    def test_returns_search(self, p):
        with patch("builtins.input", return_value="1"):
            result = p.handle_track_not_in_release("song.mp3", "Album")
        assert result == TrackNotInReleaseAction.SEARCH

    def test_returns_skip(self, p):
        with patch("builtins.input", return_value="2"):
            result = p.handle_track_not_in_release("song.mp3", "Album")
        assert result == TrackNotInReleaseAction.SKIP

    def test_returns_quit(self, p):
        with patch("builtins.input", return_value="q"):
            result = p.handle_track_not_in_release("song.mp3", "Album")
        assert result == TrackNotInReleaseAction.QUIT


# ---------------------------------------------------------------------------
# show_summary — overflow branches
# ---------------------------------------------------------------------------


class TestShowSummaryOverflow:
    def test_shows_overflow_malformed(self, p, capsys):
        stats = ProcessingStats()
        stats.malformed_files = [f"/path/file{i}.mp3" for i in range(15)]
        p.show_summary(stats)
        out = capsys.readouterr().out
        assert "more" in out

    def test_shows_overflow_errors(self, p, capsys):
        stats = ProcessingStats()
        stats.errors = [f"Error {i}" for i in range(15)]
        p.show_summary(stats)
        out = capsys.readouterr().out
        assert "more errors" in out


# ---------------------------------------------------------------------------
# show_file_rename
# ---------------------------------------------------------------------------


class TestShowFileRename:
    def test_shows_rename(self, p, capsys):
        p.show_file_rename("old.mp3", "new.mp3")
        out = capsys.readouterr().out
        assert "old.mp3" in out
        assert "new.mp3" in out
