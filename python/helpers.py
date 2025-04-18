import os
import hashlib
import sys
import select
import tempfile
import time
import simpleaudio
from pydub import AudioSegment


# Added docstrings to all functions for better clarity and maintainability.
def change_extension(filename, new_extension):
    """Change the file extension of a given filename.

    Args:
        filename (str): The original filename.
        new_extension (str): The new extension to apply.

    Returns:
        str: The filename with the new extension.
    """
    return os.path.splitext(filename)[0] + new_extension


def get_files_in_base_path(base_path, filter_cb=None):
    """Retrieve all files in a base directory that match a filter callback.

    Args:
        base_path (str): The base directory to search.
        filter_cb (callable, optional): A callback function to filter files. Defaults to None.

    Returns:
        list: A list of file paths that match the filter.
    """
    if filter_cb is None:
        filter_cb = lambda _: True

    relevant_files = []
    try:
        if not os.path.exists(base_path):
            raise FileNotFoundError(f"Base path {base_path} does not exist.")
        for root, _, files in os.walk(base_path):
            for file in files:
                file_path = os.path.join(root, file)
                if filter_cb(file_path):
                    relevant_files.append(file_path)
    except Exception as e:
        print(f"Error while traversing directory: {e}")

    return relevant_files


def calc_file_md5(file_path):
    """Calculate the MD5 hash of a file.

    Args:
        file_path (str): The path to the file.

    Returns:
        str: The MD5 hash of the file.
    """
    with open(file_path, "rb") as file:
        file_hash = hashlib.md5()
        while chunk := file.read(8192):
            file_hash.update(chunk)
        return file_hash.hexdigest()


def input_with_timeout(prompt, timeout):
    """Prompt the user for input with a timeout.

    Args:
        prompt (str): The prompt message to display.
        timeout (int): The timeout duration in seconds.

    Returns:
        str or None: The user input if provided within the timeout, otherwise None.
    """
    print(prompt)
    rlist, _, _ = select.select([sys.stdin], [], [], timeout)
    if rlist:
        return sys.stdin.readline().strip()
    return None


def find_temp_file(contains_pattern):
    """Find a temporary file that contains a specific pattern in its name.

    Args:
        contains_pattern (str): The pattern to search for in temporary file names.

    Returns:
        str or None: The path to the matching temporary file, or None if not found.
    """
    temp_dir = tempfile.gettempdir()
    for file_name in os.listdir(temp_dir):
        if contains_pattern in file_name:
            return os.path.join(temp_dir, file_name)

    return None


def play_audio(file_path):
    """Play an audio file using simpleaudio and pydub.

    Args:
        file_path (str): The path to the audio file.

    Returns:
        None
    """
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
