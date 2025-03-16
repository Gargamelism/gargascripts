import os
import hashlib
import sys
import select
import tempfile
import time
import simpleaudio
from pydub import AudioSegment


def change_extension(filename, new_extension):
    return os.path.splitext(filename)[0] + new_extension


def get_files_in_base_path(base_path, filter_cb=None):
    if filter_cb is None:
        filter_cb = lambda _: True

    relevant_files = []
    for root, _, files in os.walk(base_path):
        for file in files:
            file_path = os.path.join(root, file)
            if filter_cb(file_path):
                relevant_files.append(file_path)

    return relevant_files


def calc_file_md5(file_path):
    with open(file_path, "rb") as file:
        file_hash = hashlib.md5()
        while chunk := file.read(8192):
            file_hash.update(chunk)
        return file_hash.hexdigest()


def input_with_timeout(prompt, timeout):
    print(prompt)
    rlist, _, _ = select.select([sys.stdin], [], [], timeout)
    if rlist:
        return sys.stdin.readline().strip()
    return None


def find_temp_file(contains_pattern):
    temp_dir = tempfile.gettempdir()
    for file_name in os.listdir(temp_dir):
        if contains_pattern in file_name:
            return os.path.join(temp_dir, file_name)

    return None


def play_audio(file_path):
    if os.path.exists(file_path):
        audio = None
        wav_audio = None

        audio = AudioSegment.from_file(file_path, format=file_path.split(".")[-1])
        wav_audio = audio.export(format="wav")

        player = simpleaudio.play_buffer(wav_audio.read(), 1, 2, audio.frame_rate * 2)
        minutes, seconds = divmod(audio.duration_seconds, 60)
        print(f"Playing {file_path}, length: {int(minutes)}:{int(seconds):02d} minutes, frame rate: {audio.frame_rate}")

        stop_playing = False
        while not stop_playing and player.is_playing():
            time.sleep(0.1)
            stop_playing = input_with_timeout("Press 's' to stop playing", timeout=audio.duration_seconds) == "s"
        player.stop()
    else:
        print(f"File {file_path} does not exist.")
