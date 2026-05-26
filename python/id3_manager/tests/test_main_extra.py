"""Extra coverage tests for main.py — collision detection and other gaps."""

import sys
from pathlib import Path
from argparse import Namespace
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import ID3Processor, main
from models import (
    AudioFile, TrackMetadata, DiscTrack, DiscogsRelease, DiscogsTrack, AlbumFolder,
    ConfirmAction,
)
from sync_results import CommitResult, MoveResult


# ---------------------------------------------------------------------------
# Shared fixtures
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
        no_rename=False,
        no_file_rename=False,
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
        "acrcloud_host": "test.host",
        "acrcloud_access_key": "k",
        "acrcloud_access_secret": "s",
        "discogs_user_token": "tok",
    }


@pytest.fixture
def prompts():
    p = Mock()
    p.print = Mock()
    p.show_progress = Mock()
    p.show_folder_status = Mock()
    p.show_file_comparison = Mock()
    p.show_acr_result = Mock()
    p.show_summary = Mock()
    p.confirm_tag_changes = Mock(return_value=ConfirmAction.SKIP)
    p.confirm_folder_rename = Mock(return_value=False)
    p.confirm_file_renames = Mock(return_value=False)
    p.confirm_collision_resolution = Mock(return_value="skip")
    p.handle_no_acr_match = Mock(return_value="skip")
    p.handle_no_discogs_match = Mock(return_value="skip")
    p.handle_track_not_in_release = Mock(return_value="skip")
    p.prompt_missing_fields = Mock(side_effect=lambda m, f: m)
    p.get_manual_metadata = Mock(return_value=None)
    p.get_discogs_url_or_id = Mock(return_value=None)
    p.show_discogs_candidates = Mock(return_value=None)
    p.edit_collision_files = Mock()
    p.confirm_force_override = Mock(return_value=True)
    return p


def _proc(config, args, prompts):
    return ID3Processor(config, args, prompts)


def _af(title="Song", artist="A", album="B", track=1, disc=1, total_discs=None, path="/f/s.mp3"):
    return AudioFile(
        file_path=path,
        format="mp3",
        current_tags=TrackMetadata(
            title=title, artist=artist, album=album,
            track_number=track, disc_number=disc, total_discs=total_discs,
        ),
    )


def _proposed(af, track=None, disc=None, title=None):
    """Attach proposed_tags to an AudioFile."""
    af.proposed_tags = TrackMetadata(
        title=title or af.current_tags.title,
        artist=af.current_tags.artist,
        album=af.current_tags.album,
        track_number=track if track is not None else af.current_tags.track_number,
        disc_number=disc if disc is not None else af.current_tags.disc_number,
    )
    return af


# ---------------------------------------------------------------------------
# _detect_track_collisions
# ---------------------------------------------------------------------------

class TestDetectTrackCollisions:
    """Collision = two files propose the same (disc, track) number."""

    def test_no_collisions_unique_tracks(self, config, args, prompts):
        p = _proc(config, args, prompts)
        files = [_af(track=1), _af(track=2, path="/f/b.mp3"), _af(track=3, path="/f/c.mp3")]
        assert p._detect_track_collisions(files) == {}

    def test_detects_two_files_same_disc_track(self, config, args, prompts):
        p = _proc(config, args, prompts)
        a = _af(track=1, disc=1, path="/f/a.mp3")
        b = _af(track=1, disc=1, path="/f/b.mp3")
        collisions = p._detect_track_collisions([a, b])
        assert len(collisions) == 1
        key = DiscTrack(disc=1, track=1)
        assert key in collisions
        assert set(collisions[key]) == {a, b}

    def test_collision_uses_proposed_tags_over_current(self, config, args, prompts):
        p = _proc(config, args, prompts)
        # current_tags differ, but proposed_tags collide
        a = _af(track=5, disc=1, path="/f/a.mp3")
        b = _af(track=6, disc=1, path="/f/b.mp3")
        _proposed(a, track=3)
        _proposed(b, track=3)  # both propose track 3
        collisions = p._detect_track_collisions([a, b])
        assert DiscTrack(disc=1, track=3) in collisions

    def test_no_collision_different_discs(self, config, args, prompts):
        p = _proc(config, args, prompts)
        a = _af(track=1, disc=1, path="/f/a.mp3")
        b = _af(track=1, disc=2, path="/f/b.mp3")
        assert p._detect_track_collisions([a, b]) == {}

    def test_files_without_track_number_excluded(self, config, args, prompts):
        p = _proc(config, args, prompts)
        a = AudioFile(file_path="/f/a.mp3", format="mp3",
                      current_tags=TrackMetadata(track_number=None))
        b = AudioFile(file_path="/f/b.mp3", format="mp3",
                      current_tags=TrackMetadata(track_number=None))
        assert p._detect_track_collisions([a, b]) == {}

    def test_null_disc_treated_as_disc_1(self, config, args, prompts):
        p = _proc(config, args, prompts)
        a = AudioFile(file_path="/f/a.mp3", format="mp3",
                      current_tags=TrackMetadata(track_number=1, disc_number=None))
        b = AudioFile(file_path="/f/b.mp3", format="mp3",
                      current_tags=TrackMetadata(track_number=1, disc_number=1))
        collisions = p._detect_track_collisions([a, b])
        assert DiscTrack(disc=1, track=1) in collisions

    def test_three_way_collision(self, config, args, prompts):
        p = _proc(config, args, prompts)
        files = [_af(track=2, path=f"/f/{i}.mp3") for i in range(3)]
        collisions = p._detect_track_collisions(files)
        key = DiscTrack(disc=1, track=2)
        assert len(collisions[key]) == 3

    def test_partial_collision_only_colliding_group_returned(self, config, args, prompts):
        p = _proc(config, args, prompts)
        a = _af(track=1, path="/f/a.mp3")
        b = _af(track=1, path="/f/b.mp3")   # collides with a
        c = _af(track=2, path="/f/c.mp3")   # unique
        collisions = p._detect_track_collisions([a, b, c])
        assert len(collisions) == 1
        assert DiscTrack(disc=1, track=1) in collisions
        assert DiscTrack(disc=1, track=2) not in collisions


# ---------------------------------------------------------------------------
# _process_files — collision resolution flow
# ---------------------------------------------------------------------------

class TestProcessFilesCollisionFlow:
    def _release_with_track(self, n=2):
        tracks = [DiscogsTrack(position=str(i), title=f"T{i}", track_number=i, disc_number=1)
                  for i in range(1, n + 1)]
        return DiscogsRelease(release_id=1, title="A", artists=["A"],
                              year=2020, tracklist=tracks, total_discs=1)

    def test_collision_skip_clears_proposed_tags(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)
        p.folder_manager.should_rename_file = Mock(return_value=False)

        a = _af(track=1, path="/f/a.mp3")
        b = _af(track=1, path="/f/b.mp3")
        _proposed(a, track=1, title="Song A")
        _proposed(b, track=1, title="Song B")

        prompts.confirm_collision_resolution.return_value = "skip"
        prompts.confirm_tag_changes.return_value = ConfirmAction.SKIP

        p._process_files([a, b])

        # Both files should have proposed_tags cleared due to collision skip
        assert a.proposed_tags is None
        assert b.proposed_tags is None
        assert p.stats.files_skipped == 2

    def test_collision_apply_keeps_proposed_tags(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)
        p.folder_manager.should_rename_file = Mock(return_value=False)

        a = _af(track=1, path="/f/a.mp3")
        b = _af(track=1, path="/f/b.mp3")
        _proposed(a, track=1, title="Song A")
        _proposed(b, track=1, title="Song B")

        prompts.confirm_collision_resolution.return_value = "apply"
        prompts.confirm_tag_changes.return_value = ConfirmAction.APPLY

        p.id3_handler = Mock()
        p.id3_handler.write_tags = Mock(return_value=True)
        p.folder_manager.onedrive_sync = None

        p._process_files([a, b])

        assert p.id3_handler.write_tags.call_count == 2

    def test_collision_edit_re_checks_collisions(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)
        p.folder_manager.should_rename_file = Mock(return_value=False)

        a = _af(track=1, path="/f/a.mp3")
        b = _af(track=1, path="/f/b.mp3")
        _proposed(a, track=1, title="Song A")
        _proposed(b, track=1, title="Song B")

        call_count = [0]

        def side_effect(collisions):
            call_count[0] += 1
            if call_count[0] == 1:
                return "edit"
            # After edit, fix the collision
            a.proposed_tags = None
            b.proposed_tags = None
            return "skip"

        prompts.confirm_collision_resolution.side_effect = side_effect
        prompts.confirm_tag_changes.return_value = ConfirmAction.SKIP

        p._process_files([a, b])

        assert prompts.edit_collision_files.call_count == 1

    def test_collision_quit_exits(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)

        a = _af(track=1, path="/f/a.mp3")
        b = _af(track=1, path="/f/b.mp3")
        _proposed(a, track=1)
        _proposed(b, track=1)

        prompts.confirm_collision_resolution.return_value = "quit"

        with pytest.raises(SystemExit):
            p._process_files([a, b])


# ---------------------------------------------------------------------------
# _process_files — confirm_tag_changes paths
# ---------------------------------------------------------------------------

class TestProcessFilesConfirmation:
    def test_apply_calls_write_tags(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)
        p.folder_manager.should_rename_file = Mock(return_value=False)
        p.folder_manager.onedrive_sync = None
        p.id3_handler = Mock()
        p.id3_handler.write_tags = Mock(return_value=True)

        a = _af(track=1, path="/f/a.mp3")
        _proposed(a, title="New Title")

        prompts.confirm_tag_changes.return_value = ConfirmAction.APPLY
        p._process_files([a])

        p.id3_handler.write_tags.assert_called_once()

    def test_quit_exits(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)

        a = _af(track=1, path="/f/a.mp3")
        _proposed(a, title="New")

        prompts.confirm_tag_changes.return_value = ConfirmAction.QUIT
        with pytest.raises(SystemExit):
            p._process_files([a])

    def test_skip_increments_skipped(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)
        p.folder_manager.should_rename_file = Mock(return_value=False)

        a = _af(track=1, path="/f/a.mp3")
        _proposed(a, title="New")

        prompts.confirm_tag_changes.return_value = ConfirmAction.SKIP
        p._process_files([a])

        assert p.stats.files_skipped == 1


# ---------------------------------------------------------------------------
# _process_single_file
# ---------------------------------------------------------------------------

class TestProcessSingleFile:
    def test_unsupported_format_prints_and_returns(self, config, args, prompts):
        p = _proc(config, args, prompts)
        with patch("main.ID3Handler.is_supported", return_value=False):
            p._process_single_file("/f/file.xyz")
        prompts.print.assert_not_called()  # eprint used, not prompts.print

    def test_has_changes_apply_writes_tags(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.id3_handler = Mock()
        p.id3_handler.read_tags = Mock(return_value=TrackMetadata())
        p.id3_handler.write_tags = Mock(return_value=True)
        p.folder_manager = Mock()
        p.folder_manager.should_rename_file = Mock(return_value=False)
        p.folder_manager.onedrive_sync = None

        af_holder = [None]

        def fake_process(af, folder_release=None):
            af.proposed_tags = TrackMetadata(title="New", artist="A", album="B", track_number=1)
            af_holder[0] = af
            return folder_release

        with patch("main.ID3Handler.is_supported", return_value=True), \
             patch("main.ID3Handler.get_format", return_value="mp3"), \
             patch.object(p, "_process_single_file_obj", side_effect=fake_process):

            prompts.confirm_tag_changes.return_value = ConfirmAction.APPLY
            p._process_single_file("/f/song.mp3")

        p.id3_handler.write_tags.assert_called_once()

    def test_has_changes_quit_exits(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.id3_handler = Mock()
        p.id3_handler.read_tags = Mock(return_value=TrackMetadata())

        def fake_process(af, folder_release=None):
            af.proposed_tags = TrackMetadata(title="New", artist="A", album="B", track_number=1)
            return folder_release

        with patch("main.ID3Handler.is_supported", return_value=True), \
             patch("main.ID3Handler.get_format", return_value="mp3"), \
             patch.object(p, "_process_single_file_obj", side_effect=fake_process):
            prompts.confirm_tag_changes.return_value = ConfirmAction.QUIT
            with pytest.raises(SystemExit):
                p._process_single_file("/f/song.mp3")

    def test_no_changes_but_needs_rename(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.id3_handler = Mock()
        p.id3_handler.read_tags = Mock(return_value=TrackMetadata(
            title="T", artist="A", album="B", track_number=1
        ))
        p.folder_manager = Mock()
        p.folder_manager.should_rename_file = Mock(return_value=True)
        p.folder_manager.generate_filename = Mock(return_value="new.mp3")
        p.folder_manager.rename_audio_file = Mock(return_value=CommitResult(True, "ok"))

        with patch("main.ID3Handler.is_supported", return_value=True), \
             patch("main.ID3Handler.get_format", return_value="mp3"), \
             patch.object(p, "_process_single_file_obj", return_value=None), \
             patch("models.file_needs_rename", return_value=True):
            prompts.confirm_file_renames.return_value = True
            p._process_single_file("/f/song.mp3")

        p.folder_manager.rename_audio_file.assert_called_once()


# ---------------------------------------------------------------------------
# process() dispatch
# ---------------------------------------------------------------------------

class TestProcess:
    def test_single_file_dispatches(self, config, args, prompts, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        args.path = str(f)
        p = _proc(config, args, prompts)

        with patch.object(p, "_process_single_file") as mock_sf:
            p.process(str(f))

        mock_sf.assert_called_once_with(str(f))

    def test_directory_dispatches_to_folder(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        with patch.object(p, "_process_folder") as mock_folder:
            p.process(str(tmp_path))

        mock_folder.assert_called_once_with(str(tmp_path))

    def test_recursive_directory_dispatches(self, config, args, prompts, tmp_path):
        args.recursive = True
        p = _proc(config, args, prompts)
        with patch.object(p, "_process_recursive") as mock_rec:
            p.process(str(tmp_path))

        mock_rec.assert_called_once_with(str(tmp_path))

    def test_nonexistent_path_exits(self, config, args, prompts):
        p = _proc(config, args, prompts)
        with pytest.raises(SystemExit):
            p.process("/nonexistent/path/xyz")


# ---------------------------------------------------------------------------
# _process_folder — multi-disc path
# ---------------------------------------------------------------------------

class TestProcessFolderMultiDisc:
    def test_multi_disc_processes_each_disc(self, config, args, prompts, tmp_path):
        disc1 = tmp_path / "CD1"
        disc2 = tmp_path / "CD2"
        disc1.mkdir()
        disc2.mkdir()

        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.detect_multi_disc_structure = Mock(return_value=[
            AlbumFolder(folder_path=str(disc1), detected_disc_number=1, parent_folder=str(tmp_path)),
            AlbumFolder(folder_path=str(disc2), detected_disc_number=2, parent_folder=str(tmp_path)),
        ])
        p.folder_manager.normalize_disc_folder_name = Mock(
            side_effect=lambda path, disc, dry_run=False: CommitResult(True, path)
        )
        p.folder_manager.is_folder_properly_named = Mock(return_value=True)

        def fake_discover(folder_path):
            return [_af(disc=1 if "CD1" in folder_path else 2, path=folder_path + "/s.mp3")]

        with patch.object(p, "_discover_audio_files", side_effect=fake_discover), \
             patch.object(p, "_process_disc") as mock_disc:
            p._process_folder(str(tmp_path))

        assert mock_disc.call_count == 2

    def test_empty_folder_prints_message(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.detect_multi_disc_structure = Mock(return_value=[
            AlbumFolder(folder_path=str(tmp_path), detected_disc_number=None,
                        parent_folder=str(tmp_path.parent))
        ])

        with patch.object(p, "_discover_audio_files", return_value=[]):
            p._process_folder(str(tmp_path))

        prompts.print.assert_called()
        msg = prompts.print.call_args[0][0]
        assert "No audio files" in msg


# ---------------------------------------------------------------------------
# _process_disc
# ---------------------------------------------------------------------------

class TestProcessDisc:
    def test_sets_disc_number_for_files_missing_it(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()

        disc_folder = AlbumFolder(
            folder_path="/disc", detected_disc_number=2, parent_folder="/album"
        )
        af = AudioFile(
            file_path="/disc/s.mp3", format="mp3",
            current_tags=TrackMetadata(title="T", artist="A", album="B"),
        )

        with patch.object(p, "_process_files"):
            p._process_disc(disc_folder, [af])

        assert af.proposed_tags is not None
        assert af.proposed_tags.disc_number == 2


# ---------------------------------------------------------------------------
# _process_single_file_obj — no-ACR paths
# ---------------------------------------------------------------------------

class TestProcessSingleFileObjNoACR:
    def test_returns_folder_release_when_no_acr_result(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=None)
        p.discogs_client = None

        prompts.handle_no_acr_match.return_value = "skip"

        af = _af(track=None)  # incomplete tags so needs_processing=True
        cached = object()  # sentinel for folder_release
        result = p._process_single_file_obj(af, cached)

        assert result is cached
        assert p.stats.files_skipped == 1

    def test_handle_no_acr_manual_sets_proposed(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=None)
        p.discogs_client = None

        manual = TrackMetadata(title="M", artist="A", album="B", track_number=1)
        prompts.handle_no_acr_match.return_value = "manual"
        prompts.get_manual_metadata.return_value = manual

        af = _af(track=None)  # incomplete tags so needs_processing=True
        p._process_single_file_obj(af)

        assert af.proposed_tags is manual

    def test_handle_no_acr_existing_with_artist(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=None)
        p.discogs_client = None

        prompts.handle_no_acr_match.return_value = "existing"

        # No track_number → needs_processing=True; has artist so skips get_modified_search_query
        af = AudioFile(
            file_path="/f/s.mp3", format="mp3",
            current_tags=TrackMetadata(title="Song", artist="Artist", album="Album"),
        )
        p._process_single_file_obj(af)
        # Should not skip (artist was present)
        assert p.stats.files_skipped == 0

    def test_handle_no_acr_existing_no_artist_prompts(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=None)
        p.discogs_client = None

        prompts.handle_no_acr_match.return_value = "existing"
        prompts.get_modified_search_query = Mock(return_value=("", ""))  # no artist → skip

        af = AudioFile(
            file_path="/f/s.mp3", format="mp3",
            current_tags=TrackMetadata(title="Song", artist=None, album="Album"),
        )
        p._process_single_file_obj(af)
        assert p.stats.files_skipped == 1

    def test_handle_no_acr_quit_exits(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=None)

        prompts.handle_no_acr_match.return_value = "quit"

        with pytest.raises(SystemExit):
            p._process_single_file_obj(_af(track=None))  # incomplete tags

    def test_acr_only_mode_sets_basic_tags(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.discogs_client = None

        acr = Mock(title="Song", artists=["Artist"], album="Album", confidence=0.9)
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=acr)

        af = _af(track=None)  # incomplete tags so needs_processing=True
        p._process_single_file_obj(af)

        assert af.proposed_tags is not None
        assert af.proposed_tags.title == "Song"


# ---------------------------------------------------------------------------
# _process_single_file_obj — discogs cached release paths
# ---------------------------------------------------------------------------

class TestProcessSingleFileObjCachedRelease:
    def _make_acr(self, title="Song", artist="Artist", album="Album"):
        return Mock(title=title, artists=[artist], album=album, confidence=0.9)

    def _make_release(self, title="Album"):
        track = DiscogsTrack(position="1", title="Song", track_number=1, disc_number=1)
        return DiscogsRelease(
            release_id=1, title=title, artists=["Artist"],
            year=2020, tracklist=[track], total_discs=1,
        )

    def test_uses_cached_release_when_track_matches(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()  # fixture sets skip_discogs=True so must override
        release = self._make_release()
        acr = self._make_acr()
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=acr)

        with patch.object(p, "_match_track_from_cached_release", return_value=True) as mock_m:
            result = p._process_single_file_obj(_af(track=None), folder_release=release)

        mock_m.assert_called_once()
        assert result is release

    def test_no_match_in_cached_release_handle_not_in_release(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        release = self._make_release()
        acr = self._make_acr()
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=acr)

        prompts.handle_track_not_in_release.return_value = "skip"

        with patch.object(p, "_match_track_from_cached_release", return_value=False):
            result = p._process_single_file_obj(_af(track=None), folder_release=release)

        assert p.stats.files_skipped == 1
        assert result is release

    def test_no_match_in_cached_release_search_new(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        release = self._make_release()
        new_release = self._make_release("New Album")
        acr = self._make_acr()
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=acr)

        prompts.handle_track_not_in_release.return_value = "search"

        with patch.object(p, "_match_track_from_cached_release", return_value=False), \
             patch.object(p, "_search_and_match_discogs", return_value=new_release):
            result = p._process_single_file_obj(_af(track=None), folder_release=release)

        assert result is new_release

    def test_no_match_in_cached_release_quit_exits(self, config, args, prompts):
        args.skip_acr = False
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        release = self._make_release()
        acr = self._make_acr()
        p.acr_client = Mock()
        p.acr_client.recognize_with_retry = Mock(return_value=acr)

        prompts.handle_track_not_in_release.return_value = "quit"

        with patch.object(p, "_match_track_from_cached_release", return_value=False):
            with pytest.raises(SystemExit):
                p._process_single_file_obj(_af(track=None), folder_release=release)


# ---------------------------------------------------------------------------
# _search_and_match_discogs — early exits
# ---------------------------------------------------------------------------

class TestSearchAndMatchDiscogsEarlyExit:
    def test_no_artist_returns_none(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        acr = Mock(title="Song", artists=[], album="Album")
        result = p._search_and_match_discogs(_af(), acr)
        assert result is None

    def test_no_releases_skip_increments_skipped(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[])
        prompts.handle_no_discogs_match.return_value = "skip"
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        result = p._search_and_match_discogs(_af(), acr)
        assert result is None
        assert p.stats.files_skipped == 1

    def test_no_releases_acr_only_sets_proposed(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[])
        prompts.handle_no_discogs_match.return_value = "acr_only"
        prompts.prompt_missing_fields.side_effect = lambda m, f: m

        af = _af(track=1)
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        p._search_and_match_discogs(af, acr)

        assert af.proposed_tags is not None
        assert af.proposed_tags.title == "Song"

    def test_manual_url_release_not_found_skips(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[])
        p.discogs_client.get_release = Mock(return_value=None)
        prompts.handle_no_discogs_match.return_value = "manual_url"
        prompts.get_discogs_url_or_id.return_value = 999
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        result = p._search_and_match_discogs(_af(), acr)
        assert result is None
        assert p.stats.files_skipped == 1

    def test_no_releases_quit_exits(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[])
        prompts.handle_no_discogs_match.return_value = "quit"
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        with pytest.raises(SystemExit):
            p._search_and_match_discogs(_af(), acr)

    def test_no_releases_manual_sets_proposed(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[])
        manual = TrackMetadata(title="M", artist="A", album="B", track_number=1)
        prompts.handle_no_discogs_match.return_value = "manual"
        prompts.get_manual_metadata.return_value = manual
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        af = _af()
        p._search_and_match_discogs(af, acr)
        assert af.proposed_tags is manual


# ---------------------------------------------------------------------------
# _search_and_match_discogs — manual_url in release selection
# ---------------------------------------------------------------------------

class TestSearchAndMatchDiscogsManualUrl:
    def _make_release(self, title="Album"):
        track = DiscogsTrack(position="1", title="Song", track_number=1, disc_number=1)
        return DiscogsRelease(
            release_id=1, title=title, artists=["Artist"],
            year=2020, tracklist=[track], total_discs=1,
        )

    def test_manual_url_in_candidate_selection(self, config, args, prompts):
        p = _proc(config, args, prompts)
        release = self._make_release()
        track = release.tracklist[0]

        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[release])
        p.discogs_client.match_track_to_release = Mock(return_value=track)
        p.discogs_client.get_release = Mock(return_value=release)
        prompts.show_discogs_candidates.return_value = "manual_url"
        prompts.get_discogs_url_or_id.return_value = 1
        prompts.prompt_missing_fields.side_effect = lambda m, f: m

        af = _af()
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        result = p._search_and_match_discogs(af, acr)
        assert result is release

    def test_manual_url_no_id_skips(self, config, args, prompts):
        p = _proc(config, args, prompts)
        release = self._make_release()
        track = release.tracklist[0]

        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[release])
        p.discogs_client.match_track_to_release = Mock(return_value=track)
        prompts.show_discogs_candidates.return_value = "manual_url"
        prompts.get_discogs_url_or_id.return_value = None

        af = _af()
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        result = p._search_and_match_discogs(af, acr)
        assert result is None
        assert p.stats.files_skipped == 1

    def test_candidate_selection_none_skips(self, config, args, prompts):
        p = _proc(config, args, prompts)
        release = self._make_release()
        track = release.tracklist[0]

        p.discogs_client = Mock()
        p.discogs_client.find_best_release = Mock(return_value=[release])
        p.discogs_client.match_track_to_release = Mock(return_value=track)
        prompts.show_discogs_candidates.return_value = None

        af = _af()
        acr = Mock(title="Song", artists=["Artist"], album="Album")
        result = p._search_and_match_discogs(af, acr)
        assert result is None
        assert p.stats.files_skipped == 1


# ---------------------------------------------------------------------------
# _match_track_from_cached_release — force path
# ---------------------------------------------------------------------------

class TestMatchTrackFromCachedReleaseForce:
    def test_force_override_declined_returns_true_no_proposed_change(self, config, args, prompts):
        args.force = True
        p = _proc(config, args, prompts)

        complete_tags = TrackMetadata(
            title="T", artist="A", album="B", track_number=5,
        )
        af = AudioFile(file_path="/f/s.mp3", format="mp3", current_tags=complete_tags)

        track = DiscogsTrack(position="1", title="T", track_number=1, disc_number=1)
        release = DiscogsRelease(
            release_id=1, title="B", artists=["A"],
            year=2020, tracklist=[track], total_discs=1,
        )

        p.discogs_client = Mock()
        p.discogs_client.match_track_to_release = Mock(return_value=track)
        prompts.confirm_force_override.return_value = False
        prompts.prompt_missing_fields.side_effect = lambda m, f: m

        result = p._match_track_from_cached_release(af, release, Mock(title="T", artists=["A"]))
        assert result is True
        assert af.proposed_tags is None  # not set when override declined


# ---------------------------------------------------------------------------
# _apply_tag_changes — RuntimeError path
# ---------------------------------------------------------------------------

class TestApplyTagChangesRuntimeError:
    def test_runtime_error_stops_processing_records_error(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.id3_handler = Mock()
        p.id3_handler.write_tags = Mock(side_effect=RuntimeError("write backup failed"))
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=None)

        a = _af(path="/f/a.mp3")
        b = _af(path="/f/b.mp3")
        a.proposed_tags = TrackMetadata(title="New A")
        b.proposed_tags = TrackMetadata(title="New B")

        p._apply_tag_changes([a, b])

        assert len(p.stats.errors) == 1
        # Second file should NOT have been attempted
        assert p.id3_handler.write_tags.call_count == 1


# ---------------------------------------------------------------------------
# _push_tag_writes_to_onedrive
# ---------------------------------------------------------------------------

class TestPushTagWritesToOneDrive:
    def test_skips_when_no_onedrive_sync(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.onedrive_sync = None
        p._push_tag_writes_to_onedrive([_af()])  # should not raise

    def test_records_error_on_push_failure(self, config, args, prompts):
        p = _proc(config, args, prompts)
        sync = Mock()
        sync.copyto = Mock(return_value=MoveResult(False, "network error", "failed"))
        p.folder_manager = Mock()
        p.folder_manager.onedrive_sync = sync

        p._push_tag_writes_to_onedrive([_af()])

        assert len(p.stats.errors) == 1
        assert "network error" in p.stats.errors[0]

    def test_prints_pushed_on_success(self, config, args, prompts):
        p = _proc(config, args, prompts)
        sync = Mock()
        sync.copyto = Mock(return_value=MoveResult(True, "uploaded", "copyto"))
        p.folder_manager = Mock()
        p.folder_manager.onedrive_sync = sync

        p._push_tag_writes_to_onedrive([_af()])

        prompts.print.assert_called()
        msg = prompts.print.call_args[0][0]
        assert "Pushed" in msg


# ---------------------------------------------------------------------------
# _backfill_disc_info
# ---------------------------------------------------------------------------

class TestBackfillDiscInfo:
    def test_fills_disc_info_from_path(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=(2, 3))

        af = _af(disc=None, total_discs=None)
        p._backfill_disc_info([af])

        assert af.proposed_tags is not None
        assert af.proposed_tags.disc_number == 2
        assert af.proposed_tags.total_discs == 3

    def test_skips_files_with_complete_disc_info(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.infer_disc_info_from_path = Mock(return_value=(2, 3))

        af = _af(disc=1, total_discs=2)
        p._backfill_disc_info([af])

        p.folder_manager.infer_disc_info_from_path.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_file_renames
# ---------------------------------------------------------------------------

class TestHandleFileRenames:
    def test_generate_filename_none_skips(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.should_rename_file = Mock(return_value=True)
        p.folder_manager.generate_filename = Mock(return_value=None)

        p._handle_file_renames([_af()])

        prompts.confirm_file_renames.assert_not_called()

    def test_confirm_false_skips_rename(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.should_rename_file = Mock(return_value=True)
        p.folder_manager.generate_filename = Mock(return_value="new.mp3")
        prompts.confirm_file_renames.return_value = False

        p._handle_file_renames([_af()])

        p.folder_manager.rename_audio_file.assert_not_called()

    def test_dry_run_prints_without_renaming(self, config, args, prompts):
        args.dry_run = True
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.should_rename_file = Mock(return_value=True)
        p.folder_manager.generate_filename = Mock(return_value="new.mp3")
        prompts.confirm_file_renames.return_value = True

        p._handle_file_renames([_af()])

        p.folder_manager.rename_audio_file.assert_not_called()
        prompts.print.assert_called()
        assert "DRY RUN" in prompts.print.call_args[0][0]

    def test_failed_rename_records_error(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.should_rename_file = Mock(return_value=True)
        p.folder_manager.generate_filename = Mock(return_value="new.mp3")
        p.folder_manager.rename_audio_file = Mock(
            return_value=CommitResult(False, "permission denied")
        )
        prompts.confirm_file_renames.return_value = True

        p._handle_file_renames([_af()])

        assert len(p.stats.errors) == 1
        assert "permission denied" in p.stats.errors[0]

    def test_already_correct_name_message(self, config, args, prompts):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.should_rename_file = Mock(return_value=True)
        p.folder_manager.generate_filename = Mock(return_value="new.mp3")
        p.folder_manager.rename_audio_file = Mock(
            return_value=CommitResult(True, "File already has correct name")
        )
        prompts.confirm_file_renames.return_value = True

        p._handle_file_renames([_af()])

        assert "already correct" in prompts.print.call_args[0][0]


# ---------------------------------------------------------------------------
# _handle_folder_rename
# ---------------------------------------------------------------------------

class TestHandleFolderRename:
    def test_skips_when_already_properly_named(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.is_folder_properly_named = Mock(return_value=True)

        p._handle_folder_rename(str(tmp_path), [])

        prompts.confirm_folder_rename.assert_not_called()

    def test_skips_when_no_year_or_album(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.is_folder_properly_named = Mock(return_value=False)
        p.folder_manager.get_album_info_from_files = Mock(return_value=(None, None))

        p._handle_folder_rename(str(tmp_path), [])

        prompts.confirm_folder_rename.assert_not_called()

    def test_single_disc_rename_confirmed(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.is_folder_properly_named = Mock(return_value=False)
        p.folder_manager.get_album_info_from_files = Mock(return_value=(2020, "Album"))
        p.folder_manager.detect_multi_disc_from_metadata = Mock(return_value=1)
        p.folder_manager.generate_folder_name = Mock(return_value="2020 - Album")
        p.folder_manager.rename_folder = Mock(return_value=CommitResult(True, "ok"))

        prompts.confirm_folder_rename.return_value = True
        p._handle_folder_rename(str(tmp_path), [])

        p.folder_manager.rename_folder.assert_called_once()
        assert p.stats.folders_renamed == 1

    def test_single_disc_rename_dry_run(self, config, args, prompts, tmp_path):
        args.dry_run = True
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.is_folder_properly_named = Mock(return_value=False)
        p.folder_manager.get_album_info_from_files = Mock(return_value=(2020, "Album"))
        p.folder_manager.detect_multi_disc_from_metadata = Mock(return_value=1)
        p.folder_manager.generate_folder_name = Mock(return_value="2020 - Album")

        prompts.confirm_folder_rename.return_value = True
        p._handle_folder_rename(str(tmp_path / "Old Album"), [])

        p.folder_manager.rename_folder = Mock()  # should not be called
        prompts.print.assert_called()
        assert "DRY RUN" in prompts.print.call_args[0][0]

    def test_multi_disc_rename_confirmed(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.is_folder_properly_named = Mock(return_value=False)
        p.folder_manager.get_album_info_from_files = Mock(return_value=(2020, "Album"))
        p.folder_manager.detect_multi_disc_from_metadata = Mock(return_value=2)
        p.folder_manager.generate_folder_name = Mock(return_value="2020 - Album")
        p.folder_manager.reorganize_multi_disc_album = Mock(return_value=(True, "2020 - Album"))

        prompts.confirm_folder_rename.return_value = True
        p._handle_folder_rename(str(tmp_path), [])

        p.folder_manager.reorganize_multi_disc_album.assert_called_once()
        assert p.stats.folders_renamed == 1

    def test_folder_rename_failure_records_error(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        p.folder_manager = Mock()
        p.folder_manager.is_folder_properly_named = Mock(return_value=False)
        p.folder_manager.get_album_info_from_files = Mock(return_value=(2020, "Album"))
        p.folder_manager.detect_multi_disc_from_metadata = Mock(return_value=1)
        p.folder_manager.generate_folder_name = Mock(return_value="2020 - Album")
        p.folder_manager.rename_folder = Mock(return_value=CommitResult(False, "locked"))

        prompts.confirm_folder_rename.return_value = True
        p._handle_folder_rename(str(tmp_path / "Old"), [])

        assert len(p.stats.errors) == 1
        assert "locked" in p.stats.errors[0]


# ---------------------------------------------------------------------------
# _discover_audio_files — malformed file handling
# ---------------------------------------------------------------------------

class TestDiscoverAudioFilesMalformed:
    def test_malformed_file_tracked_and_skipped(self, config, args, prompts, tmp_path):
        p = _proc(config, args, prompts)
        f = tmp_path / "bad.mp3"
        f.touch()

        p.id3_handler = Mock()
        p.id3_handler.read_tags = Mock(side_effect=Exception("corrupt"))

        with patch("main.ID3Handler.is_supported", return_value=True), \
             patch("main.ID3Handler.get_format", return_value="mp3"):
            files = p._discover_audio_files(str(tmp_path))

        assert files == []
        assert str(f) in p.stats.malformed_files


# ---------------------------------------------------------------------------
# _process_recursive
# ---------------------------------------------------------------------------

class TestProcessRecursive:
    def test_finds_and_processes_subfolders(self, config, args, prompts, tmp_path):
        sub = tmp_path / "album"
        sub.mkdir()
        (sub / "song.mp3").touch()

        args.recursive = True

        p = _proc(config, args, prompts)
        processed = []

        with patch.object(p, "_process_folder", side_effect=processed.append), \
             patch("main.ID3Handler.SUPPORTED_EXTENSIONS", [".mp3"]):
            p._process_recursive(str(tmp_path))

        assert str(sub) in processed

    def test_skips_root_unless_include_root(self, config, args, prompts, tmp_path):
        (tmp_path / "song.mp3").touch()
        args.recursive = True
        args.include_root = False

        p = _proc(config, args, prompts)
        processed = []

        with patch.object(p, "_process_folder", side_effect=processed.append), \
             patch("main.ID3Handler.SUPPORTED_EXTENSIONS", [".mp3"]):
            p._process_recursive(str(tmp_path))

        assert str(tmp_path) not in processed


# ---------------------------------------------------------------------------
# _filter_folders_from_start — parent fallback
# ---------------------------------------------------------------------------

class TestFilterFoldersFromStartParentFallback:
    def test_start_at_parent_of_subfolder(self, config, args, prompts, tmp_path):
        """When start_at is a parent directory of folders in the list, start from first match."""
        sub_a = tmp_path / "group_a" / "album1"
        sub_b = tmp_path / "group_a" / "album2"
        sub_a.mkdir(parents=True)
        sub_b.mkdir(parents=True)

        p = _proc(config, args, prompts)
        folders = [str(sub_a), str(sub_b)]
        start_at = tmp_path / "group_a"

        result = p._filter_folders_from_start(folders, start_at)

        assert result == folders


# ---------------------------------------------------------------------------
# main() function
# ---------------------------------------------------------------------------

class TestMainFunction:
    def test_missing_config_exits(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("sys.argv", ["main.py", str(f), "--skip-discogs"]), \
             patch("main.load_config", return_value={}), \
             patch("main.validate_config", return_value=["ACRCLOUD_ACCESS_KEY"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_nonexistent_path_exits(self, tmp_path):
        with patch("sys.argv", ["main.py", str(tmp_path / "nonexistent.mp3")]):
            with pytest.raises(SystemExit):
                main()

    def test_start_at_without_recursive_warns(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        start = tmp_path
        with patch("sys.argv", ["main.py", str(f), "--start-at", str(start)]), \
             patch("main.load_config", return_value={}), \
             patch("main.validate_config", return_value=[]), \
             patch("main.InteractivePrompts"), \
             patch("main.ID3Processor") as MockProc:
            MockProc.return_value.process = Mock()
            main()  # should not raise — warning only

    def test_start_at_nonexistent_exits(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("sys.argv", ["main.py", str(f), "--recursive",
                                 "--start-at", str(tmp_path / "nope")]):
            with pytest.raises(SystemExit):
                main()

    def test_mirror_onedrive_without_root_exits(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("sys.argv", ["main.py", str(f), "--mirror-onedrive"]):
            with pytest.raises(SystemExit):
                main()

    def test_mirror_onedrive_nonexistent_root_exits(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("sys.argv", ["main.py", str(f), "--mirror-onedrive",
                                 "--onedrive-root", str(tmp_path / "nope")]):
            with pytest.raises(SystemExit):
                main()

    def test_keyboard_interrupt_exits(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        with patch("sys.argv", ["main.py", str(f), "--skip-acr", "--skip-discogs"]), \
             patch("main.load_config", return_value={}), \
             patch("main.validate_config", return_value=[]), \
             patch("main.InteractivePrompts"), \
             patch("main.ID3Processor") as MockProc:
            MockProc.return_value.process = Mock(side_effect=KeyboardInterrupt)
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_rename_only_sets_skip_flags(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        captured_args = []
        with patch("sys.argv", ["main.py", str(f), "--rename-only"]), \
             patch("main.load_config", return_value={}), \
             patch("main.validate_config", return_value=[]), \
             patch("main.InteractivePrompts"), \
             patch("main.ID3Processor") as MockProc:
            MockProc.return_value.process = Mock()

            def capture_init(config, a, prompts):
                captured_args.append(a)
                return Mock(process=Mock())

            MockProc.side_effect = capture_init
            main()

        assert captured_args[0].skip_acr is True
        assert captured_args[0].skip_discogs is True

    def test_mirror_onedrive_creates_onedrive_sync(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        onedrive_root = tmp_path  # exists and is a directory
        captured_args = []
        with patch("sys.argv", ["main.py", str(f), "--mirror-onedrive",
                                 "--onedrive-root", str(onedrive_root),
                                 "--skip-acr", "--skip-discogs"]), \
             patch("main.load_config", return_value={}), \
             patch("main.validate_config", return_value=[]), \
             patch("main.InteractivePrompts"), \
             patch("main.ID3Processor") as MockProc:
            MockProc.return_value.process = Mock()

            def capture_init(config, a, prompts):
                captured_args.append(a)
                return Mock(process=Mock())

            MockProc.side_effect = capture_init
            main()

        assert captured_args[0].mirror_onedrive is True
        assert captured_args[0].onedrive_root == str(onedrive_root)
