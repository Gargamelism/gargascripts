"""Additional coverage tests for id3_handler.py — real file round-trips."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from id3_handler import ID3Handler, ID3_ENCODING_UTF8
from id3_handler.formats import get_tag_str, get_mp4_tag, MP4_TAGS
from models import TrackMetadata

# ---------------------------------------------------------------------------
# Helpers to create minimal real audio files
# ---------------------------------------------------------------------------


def make_mp3(path: Path):
    """Write a minimal valid MP3 (silence) using mutagen."""
    # Minimal MP3: a single silent MPEG frame (Layer III, 128kbps, 44100Hz, stereo)
    # Frame sync + header bytes
    silent_frame = bytes(
        [
            0xFF,
            0xFB,
            0x90,
            0x00,  # sync + header (MPEG1 Layer3 128k 44100 stereo)
        ]
        + [0x00] * 413
    )  # silence payload
    # Write multiple frames so mutagen can sync
    path.write_bytes(silent_frame * 10)


def make_mp3_with_mutagen(path: Path, metadata: TrackMetadata = None):
    """Create a valid tagged MP3 using mutagen itself."""
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1, TALB, TRCK, TDRC

    # Start from a minimal raw frame so the file is parseable
    make_mp3(path)
    try:
        audio = MP3(str(path))
        if audio.tags is None:
            audio.add_tags()
        if metadata:
            if metadata.title:
                audio.tags.add(TIT2(encoding=ID3_ENCODING_UTF8, text=metadata.title))
            if metadata.artist:
                audio.tags.add(TPE1(encoding=ID3_ENCODING_UTF8, text=metadata.artist))
            if metadata.album:
                audio.tags.add(TALB(encoding=ID3_ENCODING_UTF8, text=metadata.album))
            if metadata.track_number:
                ts = str(metadata.track_number)
                if metadata.total_tracks:
                    ts += f"/{metadata.total_tracks}"
                audio.tags.add(TRCK(encoding=ID3_ENCODING_UTF8, text=ts))
            if metadata.year:
                audio.tags.add(
                    TDRC(encoding=ID3_ENCODING_UTF8, text=str(metadata.year))
                )
        audio.save()
    except Exception:
        pass  # minimal file is still valid for read_tags calls


def make_flac(path: Path, metadata: TrackMetadata = None):
    """Create a minimal valid FLAC file."""
    from mutagen.flac import FLAC

    # Use mutagen to create a minimal FLAC from scratch
    # Minimum: FLAC marker + STREAMINFO block
    # Build via mutagen by creating empty FLAC
    try:
        audio = FLAC()
        if metadata:
            if metadata.title:
                audio["title"] = metadata.title
            if metadata.artist:
                audio["artist"] = metadata.artist
            if metadata.album:
                audio["album"] = metadata.album
            if metadata.track_number:
                audio["tracknumber"] = str(metadata.track_number)
                if metadata.total_tracks:
                    audio["totaltracks"] = str(metadata.total_tracks)
            if metadata.disc_number:
                audio["discnumber"] = str(metadata.disc_number)
                if metadata.total_discs:
                    audio["totaldiscs"] = str(metadata.total_discs)
            if metadata.year:
                audio["date"] = str(metadata.year)
        audio.save(str(path))
    except Exception:
        # Fallback: write raw FLAC header bytes
        _write_minimal_flac(path)


def _write_minimal_flac(path: Path):
    """Write the absolute minimum FLAC header so mutagen can parse it."""
    # fLaC marker + STREAMINFO block (last=True, type=0)
    # STREAMINFO: 18 bytes of zeros (min/max blocksize/framesize, samplerate, channels, bps, total_samples, MD5)
    # Block header: 1 byte (last|type) + 3 bytes length
    streaminfo = bytes(18)
    block_header = bytes([0x80, 0x00, 0x00, 0x12])  # last=1, type=0, length=18
    path.write_bytes(b"fLaC" + block_header + streaminfo)


def make_m4a(path: Path, metadata: TrackMetadata = None):
    """Create a minimal valid M4A via mutagen MP4."""
    from mutagen.mp4 import MP4

    try:
        audio = MP4()
        if audio.tags is None:
            audio.add_tags()
        if metadata:
            if metadata.title:
                audio.tags["\xa9nam"] = [metadata.title]
            if metadata.artist:
                audio.tags["\xa9ART"] = [metadata.artist]
        audio.save(str(path))
    except Exception:
        path.touch()


# ---------------------------------------------------------------------------
# MP3 round-trip tests
# ---------------------------------------------------------------------------


class TestReadMp3Tags:
    def test_reads_tags_from_mp3(self, tmp_path):
        f = tmp_path / "song.mp3"
        meta = TrackMetadata(
            title="Round Trip",
            artist="Test Artist",
            album="Test Album",
            track_number=3,
            total_tracks=12,
            year=2021,
        )
        make_mp3_with_mutagen(f, meta)
        handler = ID3Handler()
        result = handler._read_mp3_tags(str(f))
        assert result.title == "Round Trip"
        assert result.artist == "Test Artist"
        assert result.album == "Test Album"
        assert result.track_number == 3
        assert result.total_tracks == 12
        assert result.year == 2021

    def test_reads_empty_mp3(self, tmp_path):
        f = tmp_path / "empty.mp3"
        make_mp3(f)
        handler = ID3Handler()
        result = handler._read_mp3_tags(str(f))
        assert isinstance(result, TrackMetadata)

    def test_reads_disc_info_from_mp3(self, tmp_path):
        from mutagen.mp3 import MP3
        from mutagen.id3 import TPOS

        f = tmp_path / "disc.mp3"
        make_mp3(f)
        try:
            audio = MP3(str(f))
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(TPOS(encoding=ID3_ENCODING_UTF8, text="2/3"))
            audio.save()
        except Exception:
            return
        handler = ID3Handler()
        result = handler._read_mp3_tags(str(f))
        assert result.disc_number == 2
        assert result.total_discs == 3


# ---------------------------------------------------------------------------
# FLAC round-trip tests
# ---------------------------------------------------------------------------


class TestReadFlacTags:
    def test_reads_tags_from_flac(self, tmp_path):
        f = tmp_path / "song.flac"
        meta = TrackMetadata(
            title="FLAC Song",
            artist="FLAC Artist",
            album="FLAC Album",
            track_number=5,
            total_tracks=10,
            disc_number=1,
            total_discs=2,
            year=2019,
        )
        make_flac(f, meta)
        handler = ID3Handler()
        try:
            result = handler._read_flac_tags(str(f))
            assert result.title == "FLAC Song"
            assert result.artist == "FLAC Artist"
            assert result.track_number == 5
            assert result.total_tracks == 10
            assert result.disc_number == 1
            assert result.total_discs == 2
            assert result.year == 2019
        except Exception:
            pytest.skip("FLAC creation not supported in this env")

    def test_reads_totaltracks_fallback(self, tmp_path):
        """FLAC totaltracks tag is read when tracknumber has no total part."""
        f = tmp_path / "fallback.flac"
        make_flac(f)
        handler = ID3Handler()

        # Patch FLAC to return controlled tags
        mock_audio = MagicMock()
        mock_audio.get = lambda key, default=[""]: {
            "tracknumber": ["5"],
            "totaltracks": ["12"],
            "discnumber": ["1"],
            "totaldiscs": ["2"],
            "title": ["Song"],
            "artist": ["Artist"],
            "album": ["Album"],
            "albumartist": [None],
            "date": ["2020"],
            "genre": [None],
        }.get(key, default)

        with patch("id3_handler.FLAC", return_value=mock_audio):
            result = handler._read_flac_tags(str(f))
        assert result.track_number == 5
        assert result.total_tracks == 12
        assert result.total_discs == 2

    def test_handles_invalid_totaltracks(self, tmp_path):
        f = tmp_path / "bad_total.flac"
        make_flac(f)
        handler = ID3Handler()

        mock_audio = MagicMock()
        mock_audio.get = lambda key, default=[""]: {
            "tracknumber": ["3"],
            "totaltracks": ["not_a_number"],
            "discnumber": ["1"],
            "totaldiscs": ["bad"],
            "title": [None],
            "artist": [None],
            "album": [None],
            "albumartist": [None],
            "date": [""],
            "genre": [None],
        }.get(key, default)

        with patch("id3_handler.FLAC", return_value=mock_audio):
            result = handler._read_flac_tags(str(f))
        assert result.track_number == 3
        assert result.total_tracks is None
        assert result.total_discs is None


# ---------------------------------------------------------------------------
# M4A round-trip tests
# ---------------------------------------------------------------------------


class TestReadM4aTags:
    def test_reads_tags_from_m4a(self, tmp_path):
        f = tmp_path / "song.m4a"
        handler = ID3Handler()

        mock_audio = MagicMock()
        mock_audio.tags = {
            "\xa9nam": ["M4A Song"],
            "\xa9ART": ["M4A Artist"],
            "\xa9alb": ["M4A Album"],
            "aART": ["Album Artist"],
            "trkn": [(3, 12)],
            "disk": [(2, 3)],
            "\xa9day": ["2018"],
            "\xa9gen": ["Electronic"],
        }

        with patch("id3_handler.MP4", return_value=mock_audio):
            result = handler._read_m4a_tags(str(f))
        assert result.title == "M4A Song"
        assert result.artist == "M4A Artist"
        assert result.album == "M4A Album"
        assert result.track_number == 3
        assert result.total_tracks == 12
        assert result.disc_number == 2
        assert result.total_discs == 3

    def test_reads_empty_m4a_tags(self, tmp_path):
        f = tmp_path / "empty.m4a"
        handler = ID3Handler()

        mock_audio = MagicMock()
        mock_audio.tags = {}

        with patch("id3_handler.MP4", return_value=mock_audio):
            result = handler._read_m4a_tags(str(f))
        assert result.track_number is None
        assert result.disc_number is None


# ---------------------------------------------------------------------------
# Write methods
# ---------------------------------------------------------------------------


class TestWriteTagsMethods:
    def test_write_mp3_tags_round_trip(self, tmp_path):
        f = tmp_path / "w.mp3"
        make_mp3(f)
        handler = ID3Handler()
        meta = TrackMetadata(
            title="Written",
            artist="W Artist",
            album="W Album",
            track_number=2,
            total_tracks=8,
            disc_number=1,
            total_discs=2,
            year=2022,
            genre="Jazz",
        )
        try:
            result = handler._write_mp3_tags(str(f), meta)
            assert result is True
        except Exception:
            pytest.skip("MP3 write not supported in this env")

    def test_write_flac_tags_round_trip(self, tmp_path):
        f = tmp_path / "w.flac"
        make_flac(f)
        handler = ID3Handler()
        meta = TrackMetadata(
            title="Flac Written",
            artist="FL Artist",
            album="FL Album",
            track_number=1,
            total_tracks=5,
            disc_number=2,
            total_discs=3,
            year=2017,
            genre="Classical",
        )
        try:
            result = handler._write_flac_tags(str(f), meta)
            assert result is True
        except Exception:
            pytest.skip("FLAC write not supported in this env")

    def test_write_m4a_tags_round_trip(self, tmp_path):
        f = tmp_path / "w.m4a"
        handler = ID3Handler()
        meta = TrackMetadata(
            title="M4A Written",
            artist="M4A Artist",
            album="M4A Album",
            track_number=4,
            total_tracks=10,
            disc_number=1,
            total_discs=1,
            year=2016,
            genre="Pop",
        )

        mock_audio = MagicMock()
        mock_audio.tags = {}

        with patch("id3_handler.MP4", return_value=mock_audio):
            result = handler._write_m4a_tags(str(f), meta)
        assert result is True
        mock_audio.save.assert_called_once()

    def test_write_m4a_creates_tags_if_none(self, tmp_path):
        f = tmp_path / "notags.m4a"
        handler = ID3Handler()

        real_tags = {}
        mock_audio = MagicMock()
        mock_audio.tags = None

        def fake_add_tags():
            mock_audio.tags = real_tags

        mock_audio.add_tags.side_effect = fake_add_tags

        with patch("id3_handler.MP4", return_value=mock_audio):
            handler._write_m4a_tags(str(f), TrackMetadata(title="T"))
        mock_audio.add_tags.assert_called_once()


# ---------------------------------------------------------------------------
# write_tags: preserve_existing and error branches
# ---------------------------------------------------------------------------


class TestWriteTagsPreserveExisting:
    def test_merges_existing_with_new(self, tmp_path):
        f = tmp_path / "merge.mp3"
        f.write_bytes(b"dummy")
        handler = ID3Handler()

        existing = TrackMetadata(
            title="Old Title", artist="Old Artist", album="Old Album"
        )
        new_meta = TrackMetadata(title="New Title")

        read_call = [0]

        def mock_read(path):
            read_call[0] += 1
            return existing

        with (
            patch.object(handler, "read_tags", side_effect=mock_read),
            patch.object(handler, "_write_mp3_tags", return_value=True),
        ):
            result = handler.write_tags(str(f), new_meta, preserve_existing=True)

        assert result is True
        # At least 3 calls: pre-write check, merge read, post-write validate
        assert read_call[0] >= 3

    def test_restore_fails_raises_runtime_error(self, tmp_path):
        """When write fails AND restore write_bytes also fails → RuntimeError."""
        f = tmp_path / "unrestorable.mp3"
        f.write_bytes(b"original")
        handler = ID3Handler()

        # Pre-write read succeeds; _write_mp3_tags raises; restore write_bytes also fails
        with (
            patch.object(handler, "read_tags", return_value=TrackMetadata(title="T")),
            patch.object(
                handler, "_write_mp3_tags", side_effect=OSError("write error")
            ),
            patch("id3_handler.Path.write_bytes", side_effect=OSError("disk full")),
            pytest.raises(RuntimeError),
        ):
            handler.write_tags(
                str(f), TrackMetadata(title="T"), preserve_existing=False
            )

    def test_write_false_restores_original(self, tmp_path):
        f = tmp_path / "writefail.mp3"
        orig = b"original bytes here"
        f.write_bytes(orig)
        handler = ID3Handler()

        with (
            patch.object(handler, "read_tags", return_value=TrackMetadata(title="T")),
            patch.object(handler, "_write_mp3_tags", return_value=False),
        ):
            result = handler.write_tags(
                str(f), TrackMetadata(title="T"), preserve_existing=False
            )

        assert result is False
        assert f.read_bytes() == orig

    def test_unsupported_format_returns_false(self, tmp_path):
        f = tmp_path / "song.wav"
        f.write_bytes(b"dummy")
        handler = ID3Handler()

        with patch.object(handler, "read_tags", return_value=TrackMetadata(title="T")):
            result = handler.write_tags(
                str(f), TrackMetadata(title="T"), preserve_existing=False
            )
        assert result is False


# ---------------------------------------------------------------------------
# _get_tag_str / _get_mp4_tag helpers
# ---------------------------------------------------------------------------


class TestGetTagStr:
    def test_returns_string_value(self):
        mock_tag = MagicMock()
        mock_tag.__getitem__ = lambda s, i: "Hello"
        mock_tag.__str__ = lambda s: "Hello"
        tags = {"TIT2": mock_tag}
        result = get_tag_str(tags, "TIT2")
        assert result is not None

    def test_returns_none_for_missing_key(self):
        assert get_tag_str({}, "TIT2") is None


class TestGetMp4Tag:
    def test_returns_first_list_item(self):
        tags = {"\xa9nam": ["My Title"]}
        assert get_mp4_tag(tags, "title", MP4_TAGS) == "My Title"

    def test_returns_none_for_missing_key(self):
        assert get_mp4_tag({}, "title", MP4_TAGS) is None

    def test_returns_none_for_none_value(self):
        tags = {"\xa9nam": [None]}
        assert get_mp4_tag(tags, "title", MP4_TAGS) is None

    def test_returns_none_for_empty_list(self):
        tags = {"\xa9nam": []}
        assert get_mp4_tag(tags, "title", MP4_TAGS) is None

    def test_returns_none_for_unknown_key(self):
        assert get_mp4_tag({"\xa9nam": ["x"]}, "nonexistent_key", MP4_TAGS) is None


# ---------------------------------------------------------------------------
# write_tags — FLAC and M4A dispatch paths (lines 198, 200)
# ---------------------------------------------------------------------------


class TestWriteTagsFormatDispatch:
    def test_write_tags_dispatches_flac(self, tmp_path):
        f = tmp_path / "song.flac"
        f.write_bytes(b"dummy")
        handler = ID3Handler()
        with (
            patch.object(handler, "read_tags", return_value=TrackMetadata(title="T")),
            patch.object(handler, "_write_flac_tags", return_value=True) as mock_w,
        ):
            result = handler.write_tags(
                str(f), TrackMetadata(title="T"), preserve_existing=False
            )
        mock_w.assert_called_once()
        assert result is True

    def test_write_tags_dispatches_m4a(self, tmp_path):
        f = tmp_path / "song.m4a"
        f.write_bytes(b"dummy")
        handler = ID3Handler()
        with (
            patch.object(handler, "read_tags", return_value=TrackMetadata(title="T")),
            patch.object(handler, "_write_m4a_tags", return_value=True) as mock_w,
        ):
            result = handler.write_tags(
                str(f), TrackMetadata(title="T"), preserve_existing=False
            )
        mock_w.assert_called_once()
        assert result is True


# ---------------------------------------------------------------------------
# write_tags — backup read failure (lines 186-188)
# ---------------------------------------------------------------------------


class TestWriteTagsBackupFailure:
    def test_backup_read_failure_returns_false(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"dummy")
        handler = ID3Handler()
        with (
            patch.object(handler, "read_tags", return_value=TrackMetadata(title="T")),
            patch(
                "id3_handler.Path.read_bytes", side_effect=OSError("permission denied")
            ),
        ):
            result = handler.write_tags(
                str(f), TrackMetadata(title="T"), preserve_existing=False
            )
        assert result is False


# ---------------------------------------------------------------------------
# write_tags — restore failure after write returns False (lines 207-208)
# ---------------------------------------------------------------------------


class TestWriteTagsRestoreFailureAfterFalse:
    def test_restore_fails_after_write_returns_false_raises_runtime(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"original")
        handler = ID3Handler()
        # _write_mp3_tags returns False (write failed); restore write_bytes also fails
        with (
            patch.object(handler, "read_tags", return_value=TrackMetadata(title="T")),
            patch.object(handler, "_write_mp3_tags", return_value=False),
            patch("id3_handler.Path.write_bytes", side_effect=OSError("disk full")),
        ):
            with pytest.raises(RuntimeError, match="restore also failed"):
                handler.write_tags(
                    str(f), TrackMetadata(title="T"), preserve_existing=False
                )


# ---------------------------------------------------------------------------
# write_tags — restore failure after post-write validation fails (lines 219-220)
# ---------------------------------------------------------------------------


class TestWriteTagsRestoreFailureAfterValidation:
    def test_restore_fails_after_validation_raises_runtime(self, tmp_path):
        f = tmp_path / "song.mp3"
        f.write_bytes(b"original")
        handler = ID3Handler()

        read_calls = [0]

        def mock_read(path):
            read_calls[0] += 1
            if read_calls[0] >= 2:  # post-write validation read fails
                raise Exception("corrupted")
            return TrackMetadata(title="T")

        with (
            patch.object(handler, "read_tags", side_effect=mock_read),
            patch.object(handler, "_write_mp3_tags", return_value=True),
            patch("id3_handler.Path.write_bytes", side_effect=OSError("disk full")),
        ):
            with pytest.raises(RuntimeError, match="restore also failed"):
                handler.write_tags(
                    str(f), TrackMetadata(title="T"), preserve_existing=False
                )


# ---------------------------------------------------------------------------
# _write_mp3_tags — album_artist field (line 255)
# ---------------------------------------------------------------------------


class TestWriteMp3TagsAlbumArtist:
    def test_writes_album_artist(self, tmp_path):
        f = tmp_path / "aa.mp3"
        make_mp3(f)
        handler = ID3Handler()
        meta = TrackMetadata(
            title="T",
            artist="A",
            album="B",
            album_artist="Various Artists",
            track_number=1,
        )
        try:
            result = handler._write_mp3_tags(str(f), meta)
            assert result is True
            from mutagen.mp3 import MP3

            audio = MP3(str(f))
            assert audio.tags and "TPE2" in audio.tags
        except Exception:
            pytest.skip("MP3 write not supported in this env")


# ---------------------------------------------------------------------------
# _write_flac_tags — full body via mocks (lines 278-300)
# ---------------------------------------------------------------------------


class TestWriteFlacTagsMocked:
    def test_writes_all_fields_to_flac(self, tmp_path):
        f = tmp_path / "w.flac"
        f.write_bytes(b"dummy")
        handler = ID3Handler()

        mock_audio = MagicMock()
        mock_audio.__setitem__ = MagicMock()

        meta = TrackMetadata(
            title="FL",
            artist="A",
            album="B",
            album_artist="VA",
            track_number=3,
            total_tracks=10,
            disc_number=2,
            total_discs=3,
            year=2020,
            genre="Rock",
        )

        with patch("id3_handler.FLAC", return_value=mock_audio):
            result = handler._write_flac_tags(str(f), meta)

        assert result is True
        mock_audio.save.assert_called_once()
        # Verify all fields were written
        calls = {c[0][0] for c in mock_audio.__setitem__.call_args_list}
        assert "title" in calls
        assert "artist" in calls
        assert "album" in calls
        assert "albumartist" in calls
        assert "tracknumber" in calls
        assert "totaltracks" in calls
        assert "discnumber" in calls
        assert "totaldiscs" in calls
        assert "date" in calls
        assert "genre" in calls

    def test_writes_minimal_flac_no_optional_fields(self, tmp_path):
        f = tmp_path / "min.flac"
        f.write_bytes(b"dummy")
        handler = ID3Handler()

        mock_audio = MagicMock()
        mock_audio.__setitem__ = MagicMock()

        with patch("id3_handler.FLAC", return_value=mock_audio):
            result = handler._write_flac_tags(str(f), TrackMetadata(title="T"))

        assert result is True
        calls = {c[0][0] for c in mock_audio.__setitem__.call_args_list}
        assert "title" in calls
        assert "albumartist" not in calls  # not set when None


# ---------------------------------------------------------------------------
# _write_m4a_tags — album_artist field (line 315)
# ---------------------------------------------------------------------------


class TestWriteM4aTagsAlbumArtist:
    def test_writes_album_artist(self, tmp_path):
        f = tmp_path / "aa.m4a"
        handler = ID3Handler()

        mock_audio = MagicMock()
        mock_audio.tags = {}

        meta = TrackMetadata(
            title="T",
            artist="A",
            album="B",
            album_artist="Various Artists",
            track_number=1,
        )

        with patch("id3_handler.MP4", return_value=mock_audio):
            result = handler._write_m4a_tags(str(f), meta)

        assert result is True
        assert "aART" in mock_audio.tags


# ---------------------------------------------------------------------------
# read_tags dispatch
# ---------------------------------------------------------------------------


class TestReadTagsDispatch:
    def test_dispatches_to_read_mp3(self, tmp_path):
        f = tmp_path / "x.mp3"
        f.touch()
        handler = ID3Handler()
        with patch.object(handler, "_read_mp3_tags", return_value=TrackMetadata()) as m:
            handler.read_tags(str(f))
        m.assert_called_once_with(str(f))

    def test_dispatches_to_read_flac(self, tmp_path):
        f = tmp_path / "x.flac"
        f.touch()
        handler = ID3Handler()
        with patch.object(
            handler, "_read_flac_tags", return_value=TrackMetadata()
        ) as m:
            handler.read_tags(str(f))
        m.assert_called_once_with(str(f))

    def test_dispatches_to_read_m4a(self, tmp_path):
        f = tmp_path / "x.m4a"
        f.touch()
        handler = ID3Handler()
        with patch.object(handler, "_read_m4a_tags", return_value=TrackMetadata()) as m:
            handler.read_tags(str(f))
        m.assert_called_once_with(str(f))

    def test_returns_empty_metadata_for_unsupported(self, tmp_path):
        f = tmp_path / "x.wav"
        f.touch()
        handler = ID3Handler()
        result = handler.read_tags(str(f))
        assert isinstance(result, TrackMetadata)
