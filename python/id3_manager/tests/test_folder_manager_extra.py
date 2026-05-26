"""Extra coverage tests for folder_manager.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from folder_manager import FolderManager
from models import AudioFile, TrackMetadata
from sync_results import CommitResult, MoveResult


@pytest.fixture
def fm():
    return FolderManager(onedrive_sync=None)


@pytest.fixture
def fm_sync():
    mock_sync = MagicMock()
    mock_sync.moveto.return_value = MoveResult(True, "ok", "moveto")
    mock_sync.log = MagicMock()
    return FolderManager(onedrive_sync=mock_sync)


def _af(disc=1, title="Song", path="/fake/song.mp3"):
    return AudioFile(
        file_path=path,
        format="mp3",
        current_tags=TrackMetadata(
            title=title, artist="A", album="B",
            track_number=1, disc_number=disc, total_discs=2
        ),
    )


# ---------------------------------------------------------------------------
# _mirror_rename
# ---------------------------------------------------------------------------

class TestMirrorRename:
    def test_no_op_when_no_sync(self, fm, tmp_path):
        src = tmp_path / "a.mp3"
        dst = tmp_path / "b.mp3"
        result = fm._mirror_rename(src, dst, dry_run=False)
        assert result.success is True
        assert result.mode == "skipped"

    def test_delegates_to_onedrive_sync(self, fm_sync, tmp_path):
        src = tmp_path / "a.mp3"
        dst = tmp_path / "b.mp3"
        fm_sync._mirror_rename(src, dst, dry_run=False)
        fm_sync.onedrive_sync.moveto.assert_called_once()


# ---------------------------------------------------------------------------
# _commit_with_rollback
# ---------------------------------------------------------------------------

class TestCommitWithRollback:
    def test_success(self, fm, tmp_path):
        src = tmp_path / "a.mp3"
        dst = tmp_path / "b.mp3"
        called = []
        result = fm._commit_with_rollback(
            src, dst, lambda: called.append(True),
            mirror_result=MoveResult(True, "", "moveto"),
        )
        assert result.success is True
        assert called == [True]

    def test_local_failure_triggers_rollback(self, fm_sync, tmp_path):
        src = tmp_path / "a.mp3"
        dst = tmp_path / "b.mp3"
        fm_sync.onedrive_sync.moveto.return_value = MoveResult(True, "rolled back", "moveto")

        def fail():
            raise OSError("rename failed")

        result = fm_sync._commit_with_rollback(
            src, dst, fail,
            mirror_result=MoveResult(True, "", "moveto"),
        )
        assert result.success is False
        # Rollback moveto called: dst->src
        fm_sync.onedrive_sync.moveto.assert_called()

    def test_local_failure_no_rollback_when_recovered(self, fm_sync, tmp_path):
        src = tmp_path / "a.mp3"
        dst = tmp_path / "b.mp3"

        def fail():
            raise OSError("rename failed")

        result = fm_sync._commit_with_rollback(
            src, dst, fail,
            mirror_result=MoveResult(True, "", "recovered"),
        )
        assert result.success is False
        assert "recovered" in result.message

    def test_rollback_failure_propagates_error(self, fm_sync, tmp_path):
        src = tmp_path / "a.mp3"
        dst = tmp_path / "b.mp3"
        fm_sync.onedrive_sync.moveto.return_value = MoveResult(False, "rollback failed", "failed")

        def fail():
            raise OSError("local error")

        result = fm_sync._commit_with_rollback(
            src, dst, fail,
            mirror_result=MoveResult(True, "", "moveto"),
        )
        assert result.success is False
        assert "rollback failed" in result.message


# ---------------------------------------------------------------------------
# detect_multi_disc_structure
# ---------------------------------------------------------------------------

class TestDetectMultiDiscStructure:
    def test_returns_single_when_not_a_dir(self, fm, tmp_path):
        f = tmp_path / "notadir.mp3"
        f.touch()
        result = fm.detect_multi_disc_structure(str(f))
        assert len(result) == 1

    def test_returns_multi_disc_when_cd_folders(self, fm, tmp_path):
        (tmp_path / "CD1").mkdir()
        (tmp_path / "CD2").mkdir()
        result = fm.detect_multi_disc_structure(str(tmp_path))
        assert len(result) == 2
        assert result[0].detected_disc_number == 1
        assert result[1].detected_disc_number == 2

    def test_returns_single_when_only_one_disc_folder(self, fm, tmp_path):
        (tmp_path / "CD1").mkdir()
        result = fm.detect_multi_disc_structure(str(tmp_path))
        assert len(result) == 1

    def test_ignores_non_disc_subfolders(self, fm, tmp_path):
        (tmp_path / "CD1").mkdir()
        (tmp_path / "CD2").mkdir()
        (tmp_path / "Artwork").mkdir()
        result = fm.detect_multi_disc_structure(str(tmp_path))
        assert len(result) == 2


# ---------------------------------------------------------------------------
# infer_disc_info_from_path
# ---------------------------------------------------------------------------

class TestInferDiscInfoFromPath:
    def test_returns_disc_info_in_cd_folder(self, fm, tmp_path):
        cd1 = tmp_path / "CD1"
        cd2 = tmp_path / "CD2"
        cd1.mkdir()
        cd2.mkdir()
        f = cd1 / "song.mp3"
        f.touch()
        result = fm.infer_disc_info_from_path(str(f))
        assert result == (1, 2)

    def test_returns_none_when_not_in_disc_folder(self, fm, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        result = fm.infer_disc_info_from_path(str(f))
        assert result is None

    def test_returns_none_when_no_sibling_disc_folders(self, fm, tmp_path):
        cd1 = tmp_path / "CD1"
        cd1.mkdir()
        f = cd1 / "song.mp3"
        f.touch()
        result = fm.infer_disc_info_from_path(str(f))
        assert result is None


# ---------------------------------------------------------------------------
# normalize_disc_folder_name
# ---------------------------------------------------------------------------

class TestNormalizeDiscFolderName:
    def test_already_correct_name(self, fm, tmp_path):
        folder = tmp_path / "CD1"
        folder.mkdir()
        result = fm.normalize_disc_folder_name(str(folder), 1)
        assert result.success is True

    def test_renames_disc_folder(self, fm, tmp_path):
        folder = tmp_path / "Disc 1"
        folder.mkdir()
        result = fm.normalize_disc_folder_name(str(folder), 1)
        assert result.success is True
        assert (tmp_path / "CD1").exists()

    def test_dry_run_does_not_rename(self, fm, tmp_path):
        folder = tmp_path / "Disc 1"
        folder.mkdir()
        result = fm.normalize_disc_folder_name(str(folder), 1, dry_run=True)
        assert result.success is True
        assert folder.exists()

    def test_fails_when_target_exists(self, fm, tmp_path):
        folder = tmp_path / "Disc 1"
        folder.mkdir()
        existing = tmp_path / "CD1"
        existing.mkdir()
        result = fm.normalize_disc_folder_name(str(folder), 1)
        assert result.success is False
        assert "already exists" in result.message

    def test_fails_when_remote_fails(self, fm_sync, tmp_path):
        folder = tmp_path / "Disc 1"
        folder.mkdir()
        fm_sync.onedrive_sync.moveto.return_value = MoveResult(False, "err", "failed")
        result = fm_sync.normalize_disc_folder_name(str(folder), 1)
        assert result.success is False


# ---------------------------------------------------------------------------
# create_multi_disc_structure
# ---------------------------------------------------------------------------

class TestCreateMultiDiscStructure:
    def test_creates_folders(self, fm, tmp_path):
        success, result = fm.create_multi_disc_structure(str(tmp_path), 2020, "Album", 2)
        assert success is True
        assert (Path(result) / "CD1").exists()
        assert (Path(result) / "CD2").exists()

    def test_dry_run_does_not_create(self, fm, tmp_path):
        success, result = fm.create_multi_disc_structure(str(tmp_path), 2020, "Album", 2, dry_run=True)
        assert success is True
        assert "Would create" in result

    def test_handles_oserror(self, fm, tmp_path):
        with patch("folder_manager.Path.mkdir", side_effect=OSError("no space")):
            success, result = fm.create_multi_disc_structure(str(tmp_path), 2020, "Album", 2)
        assert success is False
        assert "no space" in result


# ---------------------------------------------------------------------------
# move_file_to_disc_folder
# ---------------------------------------------------------------------------

class TestMoveFileToDiscFolder:
    def test_moves_file(self, fm, tmp_path):
        src = tmp_path / "song.mp3"
        src.touch()
        disc = tmp_path / "CD1"
        disc.mkdir()
        result = fm.move_file_to_disc_folder(str(src), str(disc))
        assert result.success is True
        assert (disc / "song.mp3").exists()

    def test_fails_when_source_missing(self, fm, tmp_path):
        disc = tmp_path / "CD1"
        disc.mkdir()
        result = fm.move_file_to_disc_folder(str(tmp_path / "missing.mp3"), str(disc))
        assert result.success is False
        assert "not found" in result.message

    def test_fails_when_target_exists(self, fm, tmp_path):
        src = tmp_path / "song.mp3"
        src.touch()
        disc = tmp_path / "CD1"
        disc.mkdir()
        (disc / "song.mp3").touch()
        result = fm.move_file_to_disc_folder(str(src), str(disc))
        assert result.success is False
        assert "already exists" in result.message

    def test_dry_run_does_not_move(self, fm, tmp_path):
        src = tmp_path / "song.mp3"
        src.touch()
        disc = tmp_path / "CD1"
        disc.mkdir()
        result = fm.move_file_to_disc_folder(str(src), str(disc), dry_run=True)
        assert result.success is True
        assert src.exists()

    def test_fails_when_remote_fails(self, fm_sync, tmp_path):
        src = tmp_path / "song.mp3"
        src.touch()
        disc = tmp_path / "CD1"
        disc.mkdir()
        fm_sync.onedrive_sync.moveto.return_value = MoveResult(False, "err", "failed")
        result = fm_sync.move_file_to_disc_folder(str(src), str(disc))
        assert result.success is False


# ---------------------------------------------------------------------------
# reorganize_multi_disc_album
# ---------------------------------------------------------------------------

class TestReorganizeMultiDiscAlbum:
    def test_fails_when_not_multi_disc(self, fm, tmp_path):
        files = [_af(disc=1)]
        # disc=1, total_discs=2 but only 1 unique disc → max disc = 2, should still be multi
        # Actually detect_multi_disc_from_metadata returns max of disc_number/total_discs
        # With disc_number=1 and total_discs=2 → max_disc = 2 → should work
        # Use a truly single-disc setup:
        af = AudioFile(
            file_path=str(tmp_path / "song.mp3"),
            format="mp3",
            current_tags=TrackMetadata(title="T", disc_number=None, total_discs=None),
        )
        (tmp_path / "song.mp3").touch()
        success, msg = fm.reorganize_multi_disc_album(str(tmp_path), [af], 2020, "Album")
        assert success is False
        assert "Not a multi-disc" in msg

    def test_dry_run(self, fm, tmp_path):
        files = [
            AudioFile(
                file_path=str(tmp_path / "t1.mp3"),
                format="mp3",
                current_tags=TrackMetadata(title="T1", disc_number=1, total_discs=2),
            ),
            AudioFile(
                file_path=str(tmp_path / "t2.mp3"),
                format="mp3",
                current_tags=TrackMetadata(title="T2", disc_number=2, total_discs=2),
            ),
        ]
        for f in files:
            Path(f.file_path).touch()
        success, msg = fm.reorganize_multi_disc_album(str(tmp_path), files, 2020, "Album", dry_run=True)
        assert success is True
        assert "Would reorganize" in msg

    def test_success_moves_files(self, fm, tmp_path):
        files = [
            AudioFile(
                file_path=str(tmp_path / "t1.mp3"),
                format="mp3",
                current_tags=TrackMetadata(title="T1", disc_number=1, total_discs=2),
            ),
            AudioFile(
                file_path=str(tmp_path / "t2.mp3"),
                format="mp3",
                current_tags=TrackMetadata(title="T2", disc_number=2, total_discs=2),
            ),
        ]
        for f in files:
            Path(f.file_path).touch()
        success, msg = fm.reorganize_multi_disc_album(str(tmp_path), files, 2020, "Album")
        assert success is True

    def test_partial_failure_reported(self, fm, tmp_path):
        files = [
            AudioFile(
                file_path=str(tmp_path / "t1.mp3"),
                format="mp3",
                current_tags=TrackMetadata(title="T1", disc_number=1, total_discs=2),
            ),
        ]
        Path(tmp_path / "t1.mp3").touch()
        fail = CommitResult(success=False, message="target already exists")
        with patch.object(fm, "move_file_to_disc_folder", return_value=fail):
            success, msg = fm.reorganize_multi_disc_album(str(tmp_path), files, 2020, "Album")
        assert success is False
        assert "Partial success" in msg or "Errors" in msg


# ---------------------------------------------------------------------------
# rename_audio_file
# ---------------------------------------------------------------------------

class TestRenameAudioFile:
    def test_already_correct_name(self, fm, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        result = fm.rename_audio_file(str(f), "song.mp3")
        assert result.success is True
        assert "already" in result.message

    def test_fails_when_target_exists(self, fm, tmp_path):
        src = tmp_path / "song.mp3"
        src.touch()
        dst = tmp_path / "new.mp3"
        dst.touch()
        result = fm.rename_audio_file(str(src), "new.mp3")
        assert result.success is False

    def test_dry_run(self, fm, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        result = fm.rename_audio_file(str(f), "new.mp3", dry_run=True)
        assert result.success is True
        assert f.exists()

    def test_renames_file(self, fm, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        result = fm.rename_audio_file(str(f), "new.mp3")
        assert result.success is True
        assert (tmp_path / "new.mp3").exists()

    def test_fails_when_remote_fails(self, fm_sync, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        fm_sync.onedrive_sync.moveto.return_value = MoveResult(False, "err", "failed")
        result = fm_sync.rename_audio_file(str(f), "new.mp3")
        assert result.success is False
