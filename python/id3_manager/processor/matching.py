"""Discogs track matching and search flows."""

import sys
from pathlib import Path

from models import AudioFile, TrackMetadata, NoDiscogsMatchAction


def match_track_from_cached_release(proc, af: AudioFile, release, acr_result) -> bool:
    track = proc.discogs_client.match_track_to_release(release, acr_result.title)

    if (not track or not track.track_number) and af.current_tags.title:
        track = proc.discogs_client.match_track_to_release(
            release, af.current_tags.title
        )

    if track and track.track_number:
        af.discogs_release = release
        af.discogs_track = track

        proposed = TrackMetadata(
            title=track.title,
            artist=release.artists[0] if release.artists else None,
            album=release.title,
            album_artist=release.artists[0] if release.artists else None,
            track_number=track.track_number,
            total_tracks=len(release.tracklist),
            disc_number=track.disc_number or af.inferred_disc_number,
            total_discs=release.total_discs if release.total_discs > 1 else None,
            year=release.year,
            genre=release.genres[0] if release.genres else None,
        )

        proposed = proc.prompts.prompt_missing_fields(proposed, Path(af.file_path).name)

        if proposed:
            if proc.args.force and af.current_tags.is_complete():
                cur = af.current_tags
                if proposed.track_number != cur.track_number:
                    if not proc.prompts.confirm_force_override(
                        af, Path(af.file_path).name, cur, proposed
                    ):
                        return True
            af.proposed_tags = proposed
            return True

    return False


def search_and_match_discogs(proc, af: AudioFile, acr_result):
    artist = acr_result.artists[0] if acr_result.artists else None
    if not artist:
        return None

    releases = proc.discogs_client.find_best_release(
        artist=artist, album=acr_result.album, track=acr_result.title
    )
    proc.stats.discogs_lookups += 1

    if not releases:
        action = proc.prompts.handle_no_discogs_match(acr_result)

        match action:
            case NoDiscogsMatchAction.ACR_ONLY:
                proposed = TrackMetadata(
                    title=acr_result.title,
                    artist=artist,
                    album=acr_result.album,
                )
                proposed = proposed.merge_with(af.current_tags)
                proposed = proc.prompts.prompt_missing_fields(
                    proposed, Path(af.file_path).name
                )
                if proposed is None:
                    proc.stats.skipped_files.append(af)
                    return None
                af.proposed_tags = proposed
                return None
            case NoDiscogsMatchAction.RETRY:
                new_artist, new_track = proc.prompts.get_modified_search_query(
                    artist, acr_result.title
                )
                releases = proc.discogs_client.find_best_release(
                    artist=new_artist, track=new_track
                )
                proc.stats.discogs_lookups += 1
            case NoDiscogsMatchAction.MANUAL_URL:
                parsed = proc.prompts.get_discogs_url_or_id()
                if parsed:
                    is_master, entity_id = parsed
                    release = proc.discogs_client.get_entity(entity_id, is_master)
                    proc.stats.discogs_lookups += 1
                    if release:
                        releases = [release]
                        proc.prompts.print(
                            f"  Fetched: {release.title} ({release.year})"
                        )
                        proc.prompts.print(f"  {release.discogs_url}")
                    else:
                        proc.prompts.print("  Could not fetch release.")
                        proc.stats.skipped_files.append(af)
                        return None
                else:
                    proc.stats.skipped_files.append(af)
                    return None
            case NoDiscogsMatchAction.MANUAL:
                manual_tags = proc.prompts.get_manual_metadata()
                if manual_tags:
                    af.proposed_tags = manual_tags
                return None
            case NoDiscogsMatchAction.SKIP:
                proc.stats.skipped_files.append(af)
                return None
            case NoDiscogsMatchAction.QUIT:
                sys.exit(0)

    if not releases:
        return None

    matchable_releases = []
    for release in releases:
        track = proc.discogs_client.match_track_to_release(release, acr_result.title)
        if track and track.track_number:
            matchable_releases.append((release, track))

    while not matchable_releases:
        action = proc.prompts.handle_no_discogs_match(acr_result)

        match action:
            case NoDiscogsMatchAction.ACR_ONLY:
                proposed = TrackMetadata(
                    title=acr_result.title,
                    artist=artist,
                    album=acr_result.album,
                )
                proposed = proposed.merge_with(af.current_tags)
                proposed = proc.prompts.prompt_missing_fields(
                    proposed, Path(af.file_path).name
                )
                if proposed is None:
                    proc.stats.skipped_files.append(af)
                    return None
                af.proposed_tags = proposed
                return None
            case NoDiscogsMatchAction.MANUAL_URL:
                parsed = proc.prompts.get_discogs_url_or_id()
                if parsed:
                    is_master, entity_id = parsed
                    release = proc.discogs_client.get_entity(entity_id, is_master)
                    proc.stats.discogs_lookups += 1
                    if release:
                        track = proc.discogs_client.match_track_to_release(
                            release, acr_result.title
                        )
                        matchable_releases = [(release, track)]
                    else:
                        proc.prompts.print("  Could not fetch release.")
                else:
                    continue
            case NoDiscogsMatchAction.RETRY:
                new_artist, new_track = proc.prompts.get_modified_search_query(
                    artist, acr_result.title
                )
                releases = proc.discogs_client.find_best_release(
                    artist=new_artist, track=new_track
                )
                proc.stats.discogs_lookups += 1
                matchable_releases = []
                for release in releases:
                    track = proc.discogs_client.match_track_to_release(
                        release, acr_result.title
                    )
                    if track and track.track_number:
                        matchable_releases.append((release, track))
                if not matchable_releases:
                    proc.prompts.print("  No matching releases found.")
            case NoDiscogsMatchAction.MANUAL:
                manual_tags = proc.prompts.get_manual_metadata(af.current_tags)
                if manual_tags:
                    af.proposed_tags = manual_tags
                else:
                    proc.stats.skipped_files.append(af)
                return None
            case NoDiscogsMatchAction.SKIP:
                proc.stats.skipped_files.append(af)
                return None
            case NoDiscogsMatchAction.QUIT:
                sys.exit(0)
            case _:
                return None

    display_releases = [r for r, _ in matchable_releases]
    selected = proc.prompts.show_discogs_candidates(display_releases)

    if selected is None:
        proc.stats.skipped_files.append(af)
        return None

    if selected == "manual_url":
        parsed = proc.prompts.get_discogs_url_or_id()
        if parsed:
            is_master, entity_id = parsed
            release = proc.discogs_client.get_entity(entity_id, is_master)
            proc.stats.discogs_lookups += 1
            if release:
                proc.prompts.print(f"  Fetched: {release.title} ({release.year})")
                proc.prompts.print(f"  {release.discogs_url}")
                track = proc.discogs_client.match_track_to_release(
                    release, acr_result.title
                )
            else:
                proc.prompts.print("  Could not fetch release.")
                proc.stats.skipped_files.append(af)
                return None
        else:
            proc.stats.skipped_files.append(af)
            return None
    else:
        release, track = matchable_releases[selected]

    af.discogs_release = release
    af.discogs_track = track

    proposed = TrackMetadata(
        title=track.title if track else acr_result.title,
        artist=release.artists[0] if release.artists else artist,
        album=release.title,
        album_artist=release.artists[0] if release.artists else None,
        track_number=track.track_number if track else None,
        total_tracks=len(release.tracklist),
        disc_number=(track.disc_number if track else None) or af.inferred_disc_number,
        total_discs=release.total_discs if release.total_discs > 1 else None,
        year=release.year,
        genre=release.genres[0] if release.genres else None,
    )

    filename = Path(af.file_path).name
    proposed = proc.prompts.prompt_missing_fields(proposed, filename)

    if proposed is None:
        proc.stats.skipped_files.append(af)
        return None

    if proc.args.force and af.current_tags.is_complete():
        cur = af.current_tags
        if proposed.track_number != cur.track_number:
            if not proc.prompts.confirm_force_override(
                af, Path(af.file_path).name, cur, proposed
            ):
                return release

    af.proposed_tags = proposed
    return release
