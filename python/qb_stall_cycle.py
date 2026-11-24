import argparse
import random
import time
import qbittorrentapi
from qbittorrentapi.definitions import TorrentState, APINames
from qbittorrentapi.torrents import TorrentDictionary, TorrentInfoList
from qbittorrentapi.client import Client


def parse_args():
    parser = argparse.ArgumentParser(description="Cycle through stalled torrents")
    parser.add_argument("--host", default="localhost", help="qBittorrent host")
    parser.add_argument("--port", type=int, default=8080, help="qBittorrent port")
    parser.add_argument("--username", default="admin", help="qBittorrent username")
    parser.add_argument("--password", default="adminadmin", help="qBittorrent password")
    return parser.parse_args()


def get_stalled_torrents(qbt_client: Client) -> TorrentInfoList:
    stalled_torrents = qbt_client.torrents_info(
        include_hashes=True, filter=TorrentState.STALLED_DOWNLOAD
    )
    final = []
    print(f"Found {len(stalled_torrents)} stalled torrents.")
    for torrent in stalled_torrents:
        if (torrent.completion_on == -1 or torrent.progress < 1) and torrent.priority in range(1, 10):
            final.append(torrent)
            print(f"Stalled torrent: {torrent.name} ({torrent.hash}) {torrent.priority}")

    return final


def randomize_priority(qbt_client: Client, stalled_torrents: list[TorrentDictionary]):
    hashes = [torrent.hash for torrent in stalled_torrents]
    random.shuffle(hashes)
    print(hashes)
    qbt_client.torrents_bottomPrio(torrent_hashes=hashes)


def main():
    parsed_args = parse_args()
    qbt_client = qbittorrentapi.Client(
        host=parsed_args.host,
        port=parsed_args.port,
        username=parsed_args.username,
        password=parsed_args.password,
    )

    try:
        qbt_client.auth_log_in()
    except qbittorrentapi.LoginFailed as e:
        print(f"Login failed: {e}")
        return
    stalled_torrents = get_stalled_torrents(qbt_client)
    randomize_priority(qbt_client, stalled_torrents)

    print(f"Processed {len(stalled_torrents)} stalled torrents.")


if __name__ == "__main__":
    main()


# {
#     "added_on": 1775937977,
#     "amount_left": 0,
#     "auto_tmm": False,
#     "availability": -1,
#     "category": "",
#     "comment": "https://orpheus.network/torrents.php?torrentid=2713891",
#     "completed": 556576541,
#     "completion_on": 1775941856,
#     "content_path": "/downloads/Aquasky/Aquasky - Raise The Devil (2011) [FLAC CD] [PASA010CD]",
#     "dl_limit": 0,
#     "dlspeed": 0,
#     "download_path": "/downloads/incomplete",
#     "downloaded": 556714251,
#     "downloaded_session": 0,
#     "eta": 8640000,
#     "f_l_piece_prio": False,
#     "force_start": False,
#     "has_metadata": True,
#     "hash": "62a550c9dc1de6a801e04c336631d57bb3567b43",
#     "inactive_seeding_time_limit": -2,
#     "infohash_v1": "62a550c9dc1de6a801e04c336631d57bb3567b43",
#     "infohash_v2": "",
#     "last_activity": 1775941856,
#     "magnet_uri": "magnet:?xt=urn:btih:62a550c9dc1de6a801e04c336631d57bb3567b43&dn=Aquasky%20-%20Raise%20The%20Devil%20%282011%29%20%5BFLAC%20CD%5D%20%5BPASA010CD%5D&xl=556576541&tr=https%3A%2F%2Fhome.opsfet.ch%2F678802b0454ff22429da59b13e3446f2%2Fannounce",
#     "max_inactive_seeding_time": -1,
#     "max_ratio": -1,
#     "max_seeding_time": -1,
#     "name": "Aquasky - Raise The Devil (2011) [FLAC CD] [PASA010CD]",
#     "num_complete": 5,
#     "num_incomplete": 0,
#     "num_leechs": 0,
#     "num_seeds": 0,
#     "popularity": 0,
#     "priority": 0,
#     "private": True,
#     "progress": 1,
#     "ratio": 0,
#     "ratio_limit": -2,
#     "root_path": "/downloads/Aquasky/Aquasky - Raise The Devil (2011) [FLAC CD] [PASA010CD]",
#     "save_path": "/downloads/Aquasky",
#     "seeding_time": 29395,
#     "seeding_time_limit": -2,
#     "seen_complete": 1775941856,
#     "seq_dl": False,
#     "size": 556576541,
#     "state": "queuedUP",
#     "super_seeding": False,
#     "tags": "",
#     "time_active": 33274,
#     "total_size": 556576541,
#     "tracker": "https://home.opsfet.ch/678802b0454ff22429da59b13e3446f2/announce",
#     "trackers_count": 1,
#     "up_limit": 0,
#     "uploaded": 0,
#     "uploaded_session": 0,
#     "upspeed": 0,
#     "reannounce_in": 0,
# }
