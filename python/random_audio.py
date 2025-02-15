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
INTERVALS = ["m2", "M2", "m3", "M3", "P4", "T", "P5", "m6", "M6", "m7", "M7", "P8"]
CHORD_TYPES = ["major", "minor", "diminished", "augmented"]
CHORD_INVERSION_TYPES = ["root", "first inversion", "second inversion"]


def generate_prompt(key, scale, meter, bpm):
    return f"Suggest a name for an electronic song in the scale {key} {scale}, with a meter of {meter}, and a bpm of {bpm}."


def get_random_note(includes_sharps=False):
    notes = ["A", "B", "C", "D", "E", "F", "G"]
    octaves = ["1", "2", "3", "4", "5"]
    note = random.choice(notes)
    if includes_sharps:
        note += "#" if random.random() > 0.5 else ""
    octave = random.choice(octaves)
    return f"{note}{octave}"


def get_random_license_plate():
    license_plate = [str(random.randint(0, 9)) for _ in range(8)]
    return "".join(license_plate)


# some combination of this with onedrive causes the file to be locked
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


def get_random_interval():
    base_note = get_random_note(True)
    interval = random.choice(INTERVALS)
    print(f"base note: {base_note}, interval: {interval}")


def get_random_chord():
    base = get_random_note()
    chord_type = random.choice(CHORD_TYPES)
    inversion = random.choice(CHORD_INVERSION_TYPES)

    print(f"base: {base}, chord type: {chord_type}, inversion: {inversion}")


def get_random_solfege(notes_count):
    key = random.choice(KEYS)
    print(f"key: {key}")
    solfege = [str(random.randint(0, 9)) for _ in range(notes_count)]
    solfege = [f"{note} |" if (i + 1) % 4 == 0 else note for i, note in enumerate(solfege)]
    print(" ".join(solfege))


def get_continous_random_audio_details(count, cb):
    for i in range(count):
        cb()
        if i < count - 1:
            input("Press Enter to continue...")

    print("Done!")


def build_parser():
    parser = argparse.ArgumentParser(description="Generate a random audio detail.")
    parser.add_argument("--warm-up", action="store_true", help="Flag to generate warm up random details")
    parser.add_argument("--timer", type=int, help="Number of minutes for the countdown timer")
    parser.add_argument("--intervals", type=int, help="Number of random intervals to generate")
    parser.add_argument("--keys", type=int, help="Number of random keys to generate")
    parser.add_argument("--chords", type=int, help="Number of random chords to generate")
    parser.add_argument("--solfege", type=int, help="Number of random solfege to generate")

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
    if args.intervals:
        get_continous_random_audio_details(args.intervals, get_random_interval)
    if args.keys:
        get_continous_random_audio_details(args.keys, lambda: print(random.choice(KEYS)))
    if args.chords:
        get_continous_random_audio_details(args.chords, get_random_chord)
    if args.solfege:
        get_continous_random_audio_details(args.solfege, lambda: get_random_solfege(16))


if __name__ == "__main__":
    main()
