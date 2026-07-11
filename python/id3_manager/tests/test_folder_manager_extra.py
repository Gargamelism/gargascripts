"""Extra coverage tests for folder_manager.py."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from folder_manager import FolderManager
from models import AudioFile, TrackMetadata
from sync_results import CommitResult


@pytest.fixture
def fm():
    return FolderManager(onedrive_sync=None)


@pytest.fixture
def fm_sync():
    mock_sync = MagicMock()
    mock_sync.log = MagicMock()
    return FolderManager(onedrive_sync=mock_sync)


def _af(disc=1, title="Song", path="/fake/song.mp3"):
    return AudioFile(
        file_path=path,
        format="mp3",
        current_tags=TrackMetadata(
            title=title,
            artist="A",
            album="B",
            track_number=1,
            disc_number=disc,
            total_discs=2,
        ),
    )


# ---------------------------------------------------------------------------
# queue_sync
# ---------------------------------------------------------------------------


class TestQueueSync:
    def test_no_op_when_no_sync(self, fm, tmp_path):
        fm.queue_sync(tmp_path)
        assert fm.pending_sync == []

    def test_adds_folder_when_sync_enabled(self, fm_sync, tmp_path):
        fm_sync.queue_sync(tmp_path)
        assert fm_sync.pending_sync == [tmp_path.resolve()]

    def test_dedupes_repeated_folder(self, fm_sync, tmp_path):
        fm_sync.queue_sync(tmp_path)
        fm_sync.queue_sync(tmp_path)
        assert fm_sync.pending_sync == [tmp_path.resolve()]

    def test_skips_child_already_covered_by_queued_parent(self, fm_sync, tmp_path):
        child = tmp_path / "album"
        child.mkdir()
        fm_sync.queue_sync(tmp_path)
        fm_sync.queue_sync(child)
        assert fm_sync.pending_sync == [tmp_path.resolve()]

    def test_queuing_parent_drops_already_queued_child(self, fm_sync, tmp_path):
        child = tmp_path / "album"
        child.mkdir()
        fm_sync.queue_sync(child)
        fm_sync.queue_sync(tmp_path)
        assert fm_sync.pending_sync == [tmp_path.resolve()]

    def test_sibling_folders_both_kept(self, fm_sync, tmp_path):
        sibling_a = tmp_path / "artist_a"
        sibling_b = tmp_path / "artist_b"
        sibling_a.mkdir()
        sibling_b.mkdir()
        fm_sync.queue_sync(sibling_a)
        fm_sync.queue_sync(sibling_b)
        assert fm_sync.pending_sync == [sibling_a.resolve(), sibling_b.resolve()]

    def test_rename_after_tag_write_leaves_only_parent_queued(self, fm_sync, tmp_path):
        """Regression: a tag write queues the album folder; the subsequent folder
        rename queues its stable parent, which must prune the now-stale entry."""
        album = tmp_path / "Old Name"
        album.mkdir()
        fm_sync.queue_sync(album)

        result = fm_sync.rename_folder(str(album), "New Name")

        assert result.success is True
        assert fm_sync.pending_sync == [tmp_path.resolve()]


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


class TestCommit:
    def test_success(self, fm, tmp_path):
        dst = tmp_path / "b.mp3"
        called = []
        result = fm.commit(dst, lambda: called.append(True))
        assert result.success is True
        assert called == [True]

    def test_failure_returns_error_message(self, fm, tmp_path):
        dst = tmp_path / "b.mp3"

        def fail():
            raise OSError("rename failed")

        result = fm.commit(dst, fail)
        assert result.success is False
        assert "rename failed" in result.message


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

    def test_queues_sync_on_success(self, fm_sync, tmp_path):
        folder = tmp_path / "Disc 1"
        folder.mkdir()
        result = fm_sync.normalize_disc_folder_name(str(folder), 1)
        assert result.success is True
        assert fm_sync.pending_sync == [tmp_path.resolve()]


# ---------------------------------------------------------------------------
# create_multi_disc_structure
# ---------------------------------------------------------------------------


class TestCreateMultiDiscStructure:
    def test_creates_folders(self, fm, tmp_path):
        success, result = fm.create_multi_disc_structure(
            str(tmp_path), 2020, "Album", 2
        )
        assert success is True
        assert (Path(result) / "CD1").exists()
        assert (Path(result) / "CD2").exists()

    def test_dry_run_does_not_create(self, fm, tmp_path):
        success, result = fm.create_multi_disc_structure(
            str(tmp_path), 2020, "Album", 2, dry_run=True
        )
        assert success is True
        assert "Would create" in result

    def test_handles_oserror(self, fm, tmp_path):
        with patch("folder_manager.Path.mkdir", side_effect=OSError("no space")):
            success, result = fm.create_multi_disc_structure(
                str(tmp_path), 2020, "Album", 2
            )
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

    def test_does_not_queue_sync_directly(self, fm_sync, tmp_path):
        """Queuing for a disc move happens once at the reorganize level, not per-file."""
        src = tmp_path / "song.mp3"
        src.touch()
        disc = tmp_path / "CD1"
        disc.mkdir()
        result = fm_sync.move_file_to_disc_folder(str(src), str(disc))
        assert result.success is True
        assert fm_sync.pending_sync == []


# ---------------------------------------------------------------------------
# reorganize_multi_disc_album
# ---------------------------------------------------------------------------


class TestReorganizeMultiDiscAlbum:
    def test_fails_when_not_multi_disc(self, fm, tmp_path):
        # Use a truly single-disc setup (disc_number=None, total_discs=None → max_disc=1):
        af = AudioFile(
            file_path=str(tmp_path / "song.mp3"),
            format="mp3",
            current_tags=TrackMetadata(title="T", disc_number=None, total_discs=None),
        )
        (tmp_path / "song.mp3").touch()
        success, msg = fm.reorganize_multi_disc_album(
            str(tmp_path), [af], 2020, "Album"
        )
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
        success, msg = fm.reorganize_multi_disc_album(
            str(tmp_path), files, 2020, "Album", dry_run=True
        )
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
        success, msg = fm.reorganize_multi_disc_album(
            str(tmp_path), files, 2020, "Album"
        )
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
            success, msg = fm.reorganize_multi_disc_album(
                str(tmp_path), files, 2020, "Album"
            )
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

    def test_queues_sync_on_success(self, fm_sync, tmp_path):
        f = tmp_path / "song.mp3"
        f.touch()
        result = fm_sync.rename_audio_file(str(f), "new.mp3")
        assert result.success is True
        assert fm_sync.pending_sync == [tmp_path.resolve()]
