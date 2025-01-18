import random
import argparse
import time
import os
from datetime import datetime
from progressbar import ProgressBar, Bar, Percentage, ETA
from helpers import get_files_in_base_path, find_temp_file, play_audio
import tempfile
import json

KEYS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def generate_prompt(key, scale, meter, bpm):
    return f"Suggest a name for an electronic song in the scale {key} {scale}, with a meter of {meter}, and a bpm of {bpm}."


def get_random_note():
    notes = ["A", "B", "C", "D", "E", "F", "G"]
    octaves = ["1", "2", "3", "4", "5"]
    note = random.choice(notes)
    octave = random.choice(octaves)
    return f"{note}{octave}"


def get_random_license_plate():
    license_plate = [str(random.randint(0, 9)) for _ in range(8)]
    return "".join(license_plate)


def run_timer(minutes):
    seconds = minutes * 60
    bar = ProgressBar(maxval=seconds, widgets=[ETA(), " ", Bar("=", "[", "]"), " ", Percentage()])
    bar.start()
    paused = False
    for i in range(seconds):
        if paused:
            print("\nTimer paused. Press Enter to resume or Ctrl+C to exit.")
            input()
            paused = False
        try:
            time.sleep(1)
            bar.update(i + 1)
        except KeyboardInterrupt:
            paused = True

    bar.finish()

    current_month = datetime.now().strftime("%Y-%B")
    temp_file_suffix = f"files_{current_month}.json"
    temp_file_path = find_temp_file(temp_file_suffix)

    if temp_file_path:
        print(temp_file_path)
        with open(temp_file_path, "r") as file:
            music_files = json.load(file)
    else:
        print(f"cache miss on {temp_file_suffix}")
        user_path = os.path.expanduser("~")
        music_files = {
            "music_files": get_files_in_base_path(
                f"{user_path}/documents/Music", lambda file: file.endswith(".mp3") or file.endswith(".wav")
            )
        }

        with tempfile.NamedTemporaryFile(delete=False, suffix=temp_file_suffix, mode="w") as temp_file:
            temp_file_path = temp_file.name
            json.dump(music_files, temp_file.file)

    random_file = random.choice(music_files.get("music_files"))
    play_audio(random_file)


def build_parser():
    parser = argparse.ArgumentParser(description="Generate a random audio detail.")
    parser.add_argument("--warm-up", action="store_true", help="Flag to generate warm up random details")
    parser.add_argument("--timer", type=int, help="Number of minutes for the countdown timer")

    args = parser.parse_args()

    if not any(args.__dict__.values()):
        parser.print_help()
        exit(1)

    return args


def main():
    args = build_parser()

    if args.warm_up:
        random_key = random.choice(KEYS)
        print(f"key: {random_key}")

        note = get_random_note()
        print(f"note: {note}")

        piano_voice_number = random.randint(1, 60)
        print(f"voice: {piano_voice_number}")

        random_license_plate = get_random_license_plate()
        print(f"license plate: {random_license_plate}")

        tonal_code = list(range(1, 9))
        random.shuffle(tonal_code)
        print(f"tonal code: {tonal_code}")
    if args.timer:
        print(f"Countdown timer set for {args.timer} minutes.")
        run_timer(args.timer)


if __name__ == "__main__":
    main()
