"""Tests for main.py processor logic."""

import sys
from pathlib import Path
from argparse import Namespace
from unittest.mock import Mock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import ID3Processor, build_parser
from models import AudioFile, TrackMetadata, TagStatus, DiscogsRelease, DiscogsTrack


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    return {
        "acrcloud_host": "test.host",
        "acrcloud_access_key": "test_key",
        "acrcloud_access_secret": "test_secret",
        "discogs_user_token": "test_token",
    }


@pytest.fixture
def mock_args():
    """Create mock arguments."""
    return Namespace(
        path="/test/path",
        recursive=False,
        include_root=False,
        start_at=None,
        dry_run=False,
        yes=False,
        force=False,
        skip_acr=False,
        skip_discogs=False,
        no_rename=False,
        no_file_rename=False,
        rename_only=False,
        env_file=".env",
        no_color=True,
        quiet=True,
    )


@pytest.fixture
def mock_prompts():
    """Create mock InteractivePrompts."""
    prompts = Mock()
    prompts.print = Mock()
    prompts.show_progress = Mock()
    prompts.show_folder_status = Mock()
    prompts.show_file_comparison = Mock()
    prompts.show_acr_result = Mock()
    prompts.show_summary = Mock()
    prompts.confirm_tag_changes = Mock(return_value="apply")
    prompts.confirm_folder_rename = Mock(return_value=True)
    prompts.confirm_file_renames = Mock(return_value=True)
    prompts.handle_no_acr_match = Mock(return_value="skip")
    prompts.handle_no_discogs_match = Mock(return_value="skip")
    prompts.handle_track_not_in_release = Mock(return_value="skip")
    prompts.prompt_missing_fields = Mock(side_effect=lambda m, f: m)
    prompts.get_manual_metadata = Mock(return_value=None)
    prompts.get_discogs_url_or_id = Mock(return_value=None)
    prompts.show_discogs_candidates = Mock(return_value=0)
    return prompts


class TestBuildParser:
    """Tests for CLI argument parser."""

    def test_has_required_path_argument(self):
        """Should require path argument."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_accepts_path_argument(self):
        """Should accept path argument."""
        parser = build_parser()
        args = parser.parse_args(["/test/path"])
        assert args.path == "/test/path"

    def test_default_values(self):
        """Should have correct default values."""
        parser = build_parser()
        args = parser.parse_args(["/test/path"])

        assert args.recursive is False
        assert args.include_root is False
        assert args.dry_run is False
        assert args.yes is False
        assert args.force is False
        assert args.skip_acr is False
        assert args.skip_discogs is False
        assert args.no_rename is False
        assert args.no_file_rename is False
        assert args.env_file == ".env"
        assert args.no_color is False
        assert args.quiet is False

    def test_recursive_flag(self):
        """Should parse recursive flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--recursive"])
        assert args.recursive is True

        args = parser.parse_args(["/path", "-r"])
        assert args.recursive is True

    def test_dry_run_flag(self):
        """Should parse dry-run flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--dry-run"])
        assert args.dry_run is True

    def test_yes_flag(self):
        """Should parse yes flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--yes"])
        assert args.yes is True

        args = parser.parse_args(["/path", "-y"])
        assert args.yes is True

    def test_force_flag(self):
        """Should parse force flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--force"])
        assert args.force is True

    def test_skip_acr_flag(self):
        """Should parse skip-acr flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--skip-acr"])
        assert args.skip_acr is True

    def test_skip_discogs_flag(self):
        """Should parse skip-discogs flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--skip-discogs"])
        assert args.skip_discogs is True

    def test_no_rename_flag(self):
        """Should parse no-rename flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--no-rename"])
        assert args.no_rename is True

    def test_no_file_rename_flag(self):
        """Should parse no-file-rename flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--no-file-rename"])
        assert args.no_file_rename is True

    def test_rename_only_flag(self):
        """Should parse rename-only flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--rename-only"])
        assert args.rename_only is True

    def test_rename_only_default_is_false(self):
        """Should default rename-only to False."""
        parser = build_parser()
        args = parser.parse_args(["/path"])
        assert args.rename_only is False

    def test_env_file_option(self):
        """Should parse custom env file path."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--env-file", "/custom/.env"])
        assert args.env_file == "/custom/.env"

    def test_quiet_flag(self):
        """Should parse quiet flag."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--quiet"])
        assert args.quiet is True

        args = parser.parse_args(["/path", "-q"])
        assert args.quiet is True


class TestID3ProcessorInitialization:
    """Tests for ID3Processor initialization."""

    def test_creates_id3_handler(self, mock_config, mock_args, mock_prompts):
        """Should create ID3Handler."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        assert processor.id3_handler is not None

    def test_creates_folder_manager(self, mock_config, mock_args, mock_prompts):
        """Should create FolderManager."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        assert processor.folder_manager is not None

    def test_creates_acr_client_when_configured(self, mock_config, mock_args, mock_prompts):
        """Should create ACRCloudClient when credentials present."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        assert processor.acr_client is not None

    def test_no_acr_client_when_skip_acr(self, mock_config, mock_args, mock_prompts):
        """Should not create ACRCloudClient when --skip-acr."""
        mock_args.skip_acr = True
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        assert processor.acr_client is None

    def test_no_acr_client_when_no_host(self, mock_args, mock_prompts):
        """Should not create ACRCloudClient when host not configured."""
        config = {"discogs_user_token": "token"}
        processor = ID3Processor(config, mock_args, mock_prompts)
        assert processor.acr_client is None

    def test_creates_discogs_client_when_configured(self, mock_config, mock_args, mock_prompts):
        """Should create DiscogsClient when token present."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        assert processor.discogs_client is not None

    def test_no_discogs_client_when_skip_discogs(self, mock_config, mock_args, mock_prompts):
        """Should not create DiscogsClient when --skip-discogs."""
        mock_args.skip_discogs = True
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        assert processor.discogs_client is None

    def test_initializes_stats(self, mock_config, mock_args, mock_prompts):
        """Should initialize processing stats."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        assert processor.stats is not None
        assert processor.stats.total_files == 0


class TestMatchTrackFromCachedRelease:
    """Tests for _match_track_from_cached_release method."""

    def test_matches_track_by_acr_title(self, mock_config, mock_args, mock_prompts):
        """Should match track using ACRCloud title."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)

        # Setup mock release and track
        release = DiscogsRelease(
            release_id=123,
            title="Test Album",
            artists=["Test Artist"],
            year=2020,
            tracklist=[
                DiscogsTrack(position="1", title="Test Song", track_number=1, disc_number=1),
            ],
            total_discs=1,
        )

        # Mock discogs_client.match_track_to_release
        processor.discogs_client = Mock()
        processor.discogs_client.match_track_to_release = Mock(
            return_value=release.tracklist[0]
        )

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )

        acr_result = Mock(title="Test Song", artists=["Test Artist"])

        result = processor._match_track_from_cached_release(af, release, acr_result)

        assert result is True
        assert af.proposed_tags is not None
        assert af.proposed_tags.title == "Test Song"

    def test_returns_false_when_no_match(self, mock_config, mock_args, mock_prompts):
        """Should return False when track doesn't match."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)

        release = DiscogsRelease(
            release_id=123,
            title="Test Album",
            artists=["Test Artist"],
            year=2020,
            tracklist=[],
            total_discs=1,
        )

        processor.discogs_client = Mock()
        processor.discogs_client.match_track_to_release = Mock(return_value=None)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )

        acr_result = Mock(title="Unknown Song", artists=[])

        result = processor._match_track_from_cached_release(af, release, acr_result)

        assert result is False
        assert af.proposed_tags is None


class TestProcessSingleFileObj:
    """Tests for _process_single_file_obj method."""

    def test_skips_complete_files_without_force(self, mock_config, mock_args, mock_prompts):
        """Should skip files with complete tags when not forcing."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song",
                artist="Artist",
                album="Album",
                track_number=1,
            ),
        )

        result = processor._process_single_file_obj(af, None)

        # Should return None (no release selected) and not modify file
        assert result is None
        assert af.proposed_tags is None

    def test_processes_complete_files_with_force(self, mock_config, mock_args, mock_prompts):
        """Should process files with complete tags when forcing."""
        mock_args.force = True

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.acr_client = Mock()
        processor.acr_client.recognize_with_retry = Mock(return_value=None)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song",
                artist="Artist",
                album="Album",
                track_number=1,
            ),
        )

        # Should attempt processing (ACR lookup incremented)
        processor._process_single_file_obj(af, None)
        assert processor.stats.acr_lookups == 1


class TestApplyTagChanges:
    """Tests for _apply_tag_changes method."""

    def test_dry_run_does_not_write_tags(self, mock_config, mock_args, mock_prompts):
        """Should not write tags in dry-run mode."""
        mock_args.dry_run = True

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.id3_handler = Mock()
        processor.id3_handler.write_tags = Mock(return_value=True)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
            proposed_tags=TrackMetadata(title="New Title"),
        )

        processor._apply_tag_changes([af])

        # Should not call write_tags
        processor.id3_handler.write_tags.assert_not_called()

    def test_writes_tags_when_not_dry_run(self, mock_config, mock_args, mock_prompts):
        """Should write tags when not in dry-run mode."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.id3_handler = Mock()
        processor.id3_handler.write_tags = Mock(return_value=True)
        processor.folder_manager = Mock()
        processor.folder_manager.should_rename_file = Mock(return_value=False)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
            proposed_tags=TrackMetadata(title="New Title"),
        )

        processor._apply_tag_changes([af])

        processor.id3_handler.write_tags.assert_called_once()
        assert processor.stats.tags_updated == 1

    def test_records_error_on_write_failure(self, mock_config, mock_args, mock_prompts):
        """Should record error when tag writing fails."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.id3_handler = Mock()
        processor.id3_handler.write_tags = Mock(return_value=False)
        processor.folder_manager = Mock()
        processor.folder_manager.should_rename_file = Mock(return_value=False)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
            proposed_tags=TrackMetadata(title="New Title"),
        )

        processor._apply_tag_changes([af])

        assert len(processor.stats.errors) == 1
        assert "Failed to write tags" in processor.stats.errors[0]


class TestHandleFileRenames:
    """Tests for _handle_file_renames method."""

    def test_skips_when_disabled(self, mock_config, mock_args, mock_prompts):
        """Should not rename files when no_file_rename is True."""
        mock_args.no_file_rename = True

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.folder_manager = Mock()
        processor.folder_manager.should_rename_file = Mock(return_value=True)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song",
                artist="Artist",
                album="Album",
                track_number=1,
            ),
        )

        # This method is called from _apply_tag_changes, so we test indirectly
        mock_args.dry_run = True
        processor._apply_tag_changes([af])

        # should_rename_file should not be called because no_file_rename is True
        processor.folder_manager.should_rename_file.assert_not_called()

    def test_skips_files_that_dont_need_rename(self, mock_config, mock_args, mock_prompts):
        """Should skip files that already have correct names."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.id3_handler = Mock()
        processor.id3_handler.write_tags = Mock(return_value=True)
        processor.folder_manager = Mock()
        processor.folder_manager.should_rename_file = Mock(return_value=False)

        af = AudioFile(
            file_path="/test/Artist - Album - 01 - Song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
            proposed_tags=TrackMetadata(
                title="Song",
                artist="Artist",
                album="Album",
                track_number=1,
            ),
        )

        processor._apply_tag_changes([af])

        # confirm_file_renames should not be called if no files need renaming
        mock_prompts.confirm_file_renames.assert_not_called()


class TestDiscoverAudioFiles:
    """Tests for _discover_audio_files method."""

    def test_sorts_by_track_number(self, mock_config, mock_args, mock_prompts, tmp_path):
        """Should sort files by disc number then track number."""
        # Create temp audio files
        (tmp_path / "track3.mp3").touch()
        (tmp_path / "track1.mp3").touch()
        (tmp_path / "track2.mp3").touch()

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.id3_handler = Mock()

        # Return different track numbers for each file
        def mock_read_tags(path):
            name = Path(path).stem
            num = int(name[-1])  # Get number from filename
            return TrackMetadata(track_number=num)

        processor.id3_handler.read_tags = mock_read_tags

        with patch.object(processor.id3_handler, 'is_supported', return_value=True):
            with patch('main.ID3Handler.is_supported', return_value=True):
                with patch('main.ID3Handler.get_format', return_value="mp3"):
                    files = processor._discover_audio_files(str(tmp_path))

        # Should be sorted by track number
        assert len(files) == 3
        track_nums = [f.current_tags.track_number for f in files]
        assert track_nums == [1, 2, 3]


class TestSearchAndMatchDiscogs:
    """Tests for _search_and_match_discogs method."""

    def test_retry_with_modified_query_when_no_matchable_releases(
        self, mock_config, mock_args, mock_prompts
    ):
        """Should retry search with modified query when releases found but none match track."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)

        # Create releases - first search returns releases but none match the track
        release_no_match = DiscogsRelease(
            release_id=123,
            title="Some Album",
            artists=["Test Artist"],
            year=2020,
            tracklist=[
                DiscogsTrack(position="1", title="Different Song", track_number=1, disc_number=1),
            ],
            total_discs=1,
        )

        # Second search (after retry) returns release that matches
        release_with_match = DiscogsRelease(
            release_id=456,
            title="Correct Album",
            artists=["Test Artist"],
            year=2020,
            tracklist=[
                DiscogsTrack(position="1", title="Test Song", track_number=1, disc_number=1),
            ],
            total_discs=1,
        )

        # Setup mock discogs client
        processor.discogs_client = Mock()
        # First call returns release with no matching track, second call returns matching release
        processor.discogs_client.find_best_release = Mock(
            side_effect=[[release_no_match], [release_with_match]]
        )

        # First call returns None (no match), second call returns the matching track
        matching_track = release_with_match.tracklist[0]
        processor.discogs_client.match_track_to_release = Mock(
            side_effect=[None, matching_track]
        )

        # Setup prompts to return "retry" when no match found
        mock_prompts.handle_no_discogs_match = Mock(return_value="retry")
        mock_prompts.get_modified_search_query = Mock(return_value=("Test Artist", "Test Song"))
        mock_prompts.show_discogs_candidates = Mock(return_value=0)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )

        acr_result = Mock(
            title="Test Song",
            artists=["Test Artist"],
            album="Some Album",
        )

        result = processor._search_and_match_discogs(af, acr_result)

        # Should have called get_modified_search_query
        mock_prompts.get_modified_search_query.assert_called_once_with("Test Artist", "Test Song")

        # Should have searched twice (initial + retry)
        assert processor.discogs_client.find_best_release.call_count == 2

        # Should have shown candidates after successful retry
        mock_prompts.show_discogs_candidates.assert_called_once()

        # Should return the selected release
        assert result == release_with_match

    def test_retry_loops_back_to_menu_when_still_no_matchable_releases(
        self, mock_config, mock_args, mock_prompts
    ):
        """Should show menu again if retry with modified query still finds no matchable releases."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)

        release = DiscogsRelease(
            release_id=123,
            title="Some Album",
            artists=["Test Artist"],
            year=2020,
            tracklist=[
                DiscogsTrack(position="1", title="Different Song", track_number=1, disc_number=1),
            ],
            total_discs=1,
        )

        processor.discogs_client = Mock()
        # Both searches return releases but none match the track
        processor.discogs_client.find_best_release = Mock(return_value=[release])
        processor.discogs_client.match_track_to_release = Mock(return_value=None)

        # First call returns "retry", second call returns "skip" to exit the loop
        mock_prompts.handle_no_discogs_match = Mock(side_effect=["retry", "skip"])
        mock_prompts.get_modified_search_query = Mock(return_value=("Test Artist", "Test Song"))

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )

        acr_result = Mock(
            title="Test Song",
            artists=["Test Artist"],
            album="Some Album",
        )

        result = processor._search_and_match_discogs(af, acr_result)

        # Should have retried
        mock_prompts.get_modified_search_query.assert_called_once()

        # Should have printed message about no matches
        mock_prompts.print.assert_called_with("  No matching releases found.")

        # Should have shown menu twice (initial + after failed retry)
        assert mock_prompts.handle_no_discogs_match.call_count == 2

        # Should have incremented files_skipped when user chose skip
        assert processor.stats.files_skipped == 1

        # Should return None since user skipped
        assert result is None

    def test_retry_then_manual_url_after_no_matches(
        self, mock_config, mock_args, mock_prompts
    ):
        """Should allow manual URL entry after retry finds no matchable releases."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)

        release_no_match = DiscogsRelease(
            release_id=123,
            title="Some Album",
            artists=["Test Artist"],
            year=2020,
            tracklist=[
                DiscogsTrack(position="1", title="Different Song", track_number=1, disc_number=1),
            ],
            total_discs=1,
        )

        # Release fetched via manual URL
        manual_release = DiscogsRelease(
            release_id=789,
            title="Manual Album",
            artists=["Test Artist"],
            year=2020,
            tracklist=[
                DiscogsTrack(position="1", title="Test Song", track_number=1, disc_number=1),
            ],
            total_discs=1,
        )

        processor.discogs_client = Mock()
        # Initial search returns release but no matching track
        processor.discogs_client.find_best_release = Mock(return_value=[release_no_match])
        # First call returns None (no match), after manual URL entry returns the track
        processor.discogs_client.match_track_to_release = Mock(
            side_effect=[None, None, manual_release.tracklist[0]]
        )
        processor.discogs_client.get_release = Mock(return_value=manual_release)

        # First: retry (fails), Second: manual_url
        mock_prompts.handle_no_discogs_match = Mock(side_effect=["retry", "manual_url"])
        mock_prompts.get_modified_search_query = Mock(return_value=("Test Artist", "Test Song"))
        mock_prompts.get_discogs_url_or_id = Mock(return_value=789)
        mock_prompts.show_discogs_candidates = Mock(return_value=0)

        af = AudioFile(
            file_path="/test/song.mp3",
            format="mp3",
            current_tags=TrackMetadata(),
        )

        acr_result = Mock(
            title="Test Song",
            artists=["Test Artist"],
            album="Some Album",
        )

        result = processor._search_and_match_discogs(af, acr_result)

        # Should have tried retry first
        mock_prompts.get_modified_search_query.assert_called_once()

        # Should have shown menu twice (initial + after failed retry)
        assert mock_prompts.handle_no_discogs_match.call_count == 2

        # Should have fetched the manual release
        processor.discogs_client.get_release.assert_called_once_with(789)

        # Should return the manually fetched release
        assert result == manual_release


class TestFilterFoldersFromStart:
    """Tests for _filter_folders_from_start method."""

    def test_returns_all_folders_when_start_at_is_none(self, mock_config, mock_args, mock_prompts):
        """Should return all folders when start_at is None."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        folders = ["/path/a", "/path/b", "/path/c"]

        result = processor._filter_folders_from_start(folders, None)

        assert result == folders

    def test_returns_folders_from_start_point(self, mock_config, mock_args, mock_prompts, tmp_path):
        """Should skip folders before start_at and return the rest."""
        # Create real folders so Path.resolve() works
        folder_a = tmp_path / "2020 - Album A"
        folder_b = tmp_path / "2021 - Album B"
        folder_c = tmp_path / "2022 - Album C"
        folder_a.mkdir()
        folder_b.mkdir()
        folder_c.mkdir()

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        folders = [str(folder_a), str(folder_b), str(folder_c)]
        start_at = folder_b

        result = processor._filter_folders_from_start(folders, start_at)

        assert len(result) == 2
        assert result[0] == str(folder_b)
        assert result[1] == str(folder_c)

    def test_returns_empty_list_when_start_at_not_found(self, mock_config, mock_args, mock_prompts, tmp_path):
        """Should return empty list when start_at folder is not in the list."""
        folder_a = tmp_path / "a"
        folder_b = tmp_path / "b"
        folder_nonexistent = tmp_path / "nonexistent"
        folder_a.mkdir()
        folder_b.mkdir()

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        folders = [str(folder_a), str(folder_b)]
        start_at = folder_nonexistent

        result = processor._filter_folders_from_start(folders, start_at)

        assert result == []
        mock_prompts.print.assert_called_once()
        assert "not found" in mock_prompts.print.call_args[0][0].lower()

    def test_returns_all_when_start_at_is_first_folder(self, mock_config, mock_args, mock_prompts, tmp_path):
        """Should return all folders when start_at is the first folder."""
        folder_a = tmp_path / "a"
        folder_b = tmp_path / "b"
        folder_c = tmp_path / "c"
        folder_a.mkdir()
        folder_b.mkdir()
        folder_c.mkdir()

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        folders = [str(folder_a), str(folder_b), str(folder_c)]
        start_at = folder_a

        result = processor._filter_folders_from_start(folders, start_at)

        assert result == folders
        # Should not print "skipping" message when starting at first folder
        mock_prompts.print.assert_not_called()

    def test_returns_only_last_when_start_at_is_last_folder(self, mock_config, mock_args, mock_prompts, tmp_path):
        """Should return only last folder when start_at is the last one."""
        folder_a = tmp_path / "a"
        folder_b = tmp_path / "b"
        folder_c = tmp_path / "c"
        folder_a.mkdir()
        folder_b.mkdir()
        folder_c.mkdir()

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        folders = [str(folder_a), str(folder_b), str(folder_c)]
        start_at = folder_c

        result = processor._filter_folders_from_start(folders, start_at)

        assert result == [str(folder_c)]
        mock_prompts.print.assert_called_once()
        assert "2 folder" in mock_prompts.print.call_args[0][0].lower()

    def test_prints_skip_count_when_skipping(self, mock_config, mock_args, mock_prompts, tmp_path):
        """Should print how many folders are being skipped."""
        folder_a = tmp_path / "a"
        folder_b = tmp_path / "b"
        folder_c = tmp_path / "c"
        folder_d = tmp_path / "d"
        folder_a.mkdir()
        folder_b.mkdir()
        folder_c.mkdir()
        folder_d.mkdir()

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        folders = [str(folder_a), str(folder_b), str(folder_c), str(folder_d)]
        start_at = folder_c

        processor._filter_folders_from_start(folders, start_at)

        mock_prompts.print.assert_called_once()
        call_arg = mock_prompts.print.call_args[0][0]
        assert "2 folder" in call_arg.lower()
        assert "skipping" in call_arg.lower()


class TestBuildParserStartAt:
    """Tests for --start-at CLI argument."""

    def test_start_at_option(self):
        """Should parse --start-at option."""
        parser = build_parser()
        args = parser.parse_args(["/path", "--start-at", "/path/to/folder"])
        assert args.start_at == "/path/to/folder"

    def test_start_at_default_is_none(self):
        """Should default --start-at to None."""
        parser = build_parser()
        args = parser.parse_args(["/path"])
        assert args.start_at is None


class TestRenameOnly:
    """Tests for --rename-only mode."""

    def test_rename_only_skips_tag_processing(
        self, mock_config, mock_args, mock_prompts, tmp_path
    ):
        """Should skip ACRCloud/Discogs and only rename files."""
        mock_args.rename_only = True
        mock_args.skip_acr = True
        mock_args.skip_discogs = True

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.folder_manager = Mock()
        processor.folder_manager.detect_multi_disc_structure = Mock(return_value=[])
        processor.folder_manager.should_rename_file = Mock(return_value=True)
        processor.folder_manager.generate_filename = Mock(return_value="Artist - Album - 01 - Song.mp3")
        processor.folder_manager.rename_audio_file = Mock(return_value=(True, "/new/path.mp3"))
        processor.folder_manager.is_folder_properly_named = Mock(return_value=True)

        af = AudioFile(
            file_path="/test/wrong_name.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song",
                artist="Artist",
                album="Album",
                track_number=1,
            ),
        )

        with patch.object(processor, '_discover_audio_files', return_value=[af]):
            with patch('models.file_needs_rename', return_value=True):
                processor._process_folder("/test")

        # Should NOT have created ACR or Discogs clients
        assert processor.acr_client is None
        assert processor.discogs_client is None

        # Should have called rename
        processor.folder_manager.rename_audio_file.assert_called_once()

    def test_rename_only_single_file_skips_tags(
        self, mock_config, mock_args, mock_prompts
    ):
        """Should skip tag processing for single file in rename-only mode."""
        mock_args.rename_only = True
        mock_args.skip_acr = True
        mock_args.skip_discogs = True

        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.id3_handler = Mock()
        processor.id3_handler.read_tags = Mock(return_value=TrackMetadata(
            title="Song", artist="Artist", album="Album", track_number=1,
        ))
        processor.folder_manager = Mock()
        processor.folder_manager.should_rename_file = Mock(return_value=True)
        processor.folder_manager.generate_filename = Mock(return_value="Artist - Album - 01 - Song.mp3")
        processor.folder_manager.rename_audio_file = Mock(return_value=(True, "/new/path.mp3"))

        with patch('main.ID3Handler.is_supported', return_value=True):
            with patch('main.ID3Handler.get_format', return_value="mp3"):
                with patch('models.file_needs_rename', return_value=True):
                    processor._process_single_file("/test/wrong_name.mp3")

        # Should have called rename
        processor.folder_manager.rename_audio_file.assert_called_once()

        # Should NOT have attempted any ACR/Discogs lookups
        assert processor.stats.acr_lookups == 0
        assert processor.stats.discogs_lookups == 0


class TestFilesOnlyNeedingRename:
    """Tests for files that have complete tags but need renaming."""

    def test_files_with_complete_tags_needing_rename_are_renamed(
        self, mock_config, mock_args, mock_prompts
    ):
        """Should rename files that have complete tags but wrong filenames."""
        processor = ID3Processor(mock_config, mock_args, mock_prompts)
        processor.folder_manager = Mock()
        processor.folder_manager.should_rename_file = Mock(return_value=True)
        processor.folder_manager.generate_filename = Mock(return_value="Artist - Album - 01 - Song.mp3")
        processor.folder_manager.rename_audio_file = Mock(return_value=(True, "/new/path.mp3"))

        # File has complete tags but wrong filename
        af = AudioFile(
            file_path="/test/wrong_name.mp3",
            format="mp3",
            current_tags=TrackMetadata(
                title="Song",
                artist="Artist",
                album="Album",
                track_number=1,
            ),
        )
        # No proposed_tags - file doesn't need tag updates
        assert af.proposed_tags is None
        assert not af.needs_processing  # Tags are complete

        # Patch the file_needs_rename function to return True for this file
        with patch('models.file_needs_rename', return_value=True):
            processor._process_files([af])

        # Should have called rename
        processor.folder_manager.rename_audio_file.assert_called_once()
