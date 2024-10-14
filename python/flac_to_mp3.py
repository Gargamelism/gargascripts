import argparse
import os
from pydub import AudioSegment
from progressbar import ProgressBar

from helpers import change_extension


def get_relevant_files(base_path, filter_cb):
    relevant_files = []
    for root, dirs, files in os.walk(base_path):
        relevant_files.extend(
            [os.path.join(root, file) for file in files if filter_cb(file)]
        )

    return relevant_files


def flac_to_mp3(file_path):
    if file_path.endswith(".flac"):
        print(f"converting {file_path} to mp3")
        flac_audio = AudioSegment.from_file(file_path, "flac")

        mp3_name = change_extension(file_path, ".mp3")

        flac_audio.export(mp3_name, format="mp3", parameters=["-qscale:a", "0"])


def main():
    parser = argparse.ArgumentParser(
        description="calculate duration times in given file"
    )
    parser.add_argument("base_path")
    args = parser.parse_args()

    relevant_files = get_relevant_files(args.base_path, lambda x: x.endswith(".flac"))
    progress_bar = ProgressBar(max_value=len(relevant_files))
    for file in relevant_files:
        flac_to_mp3(file)
        progress_bar.increment()
    progress_bar.finish()

    print("done!")


if __name__ == "__main__":
    main()
