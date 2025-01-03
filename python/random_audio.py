import random
import argparse

KEYS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def generate_prompt(key, scale, meter, bpm):
    return f"Suggest a name for an electronic song in the scale {key} {scale}, with a meter of {meter}, and a bpm of {bpm}."


def get_random_song_details():
    scales = [
        "major",
        "minor",
        "dorian",
        "ukrainian dorian",
        "phrygian",
        "lydian",
        "mixolydian",
        "locrian",
        "aeolian",
        "algerian",
        "flamenco mode",
        "gypsy scale",
        "harmonic major",
        "neapolitan major",
        "harmonic minor",
        "melodic minor",
        "neapolitan minor",
        "hirajoshi",
        "hungarian minor",
        "iwato",
        "persian",
        "prometheus",
        "whole tone",
        "half-whole dim.",
        "whole-half dim.",
        "minor blues",
        "minor pentatonic",
        "major pentatonic",
        "phrygian dominant",
        "lydian augmented",
        "lydian dominant",
        "super locrian",
        "a-tone spanish",
        "bhairav",
        "in-sen",
        "kumoi",
        "pelog selisir",
        "pelog tembung",
    ]
    meters = [
        "2/2",
        "2/4",
        "6/8",
        "3/4",
        "9/8",
        "3/2",
        "4/4",
        "12/8",
        "4/2",
        "5/8",
        "7/8",
        "5/4",
    ]
    meter_weights = [
        4,
        5,
        4,
        5,
        2,
        1,
        7,
        1,
        1,
        3,
        3,
        1,
    ]  # Adjust these values as needed

    key = random.choice(KEYS)
    scale = random.choice(scales)
    meter = random.choices(meters, weights=meter_weights, k=1)[0]
    bpm = random.randint(60, 160)

    return key, scale, meter, bpm


def generate_random_song():
    key, scale, meter, _ = get_random_song_details()

    return key, scale, meter


def get_random_note():
    notes = ["A", "B", "C", "D", "E", "F", "G"]
    octaves = ["1", "2", "3", "4", "5"]
    note = random.choice(notes)
    octave = random.choice(octaves)
    return f"{note}{octave}"

def get_random_license_plate():
    license_plate = [str(random.randint(0, 9)) for _ in range(8)]
    return "".join(license_plate)


def main():
    parser = argparse.ArgumentParser(description="Generate a random audio detail.")
    parser.add_argument(
        "--key", action="store_true", help="Flag to generate a random key for the song"
    )
    parser.add_argument(
        "--note", action="store_true", help="Flag to generate a random note to play"
    )
    parser.add_argument(
        "--piano-voice",
        action="store_true",
        help="Flag to generate a random voice for the piano",
    )
    parser.add_argument(
        "--song", action="store_true", help="Flag to generate a random song with details"
    )
    parser.add_argument(
        "--license-plate", action="store_true", help="Flag to generate a random license plate"
    )
    args = parser.parse_args()

    if not any(args.__dict__.values()):
        parser.print_help()
        return

    if args.song:
        key, scale, meter, bpm = get_random_song_details()
        prompt = generate_prompt(key, scale, meter, bpm)
        print(prompt)
        exit(0)
    if args.key:
        random_key = random.choice(KEYS)
        print(f"key: {random_key}")
    if args.note:
        note = get_random_note()
        print(f"note: {note}")
    if args.piano_voice:
        piano_voice_number = random.randint(1, 60)
        print(f"voice: {piano_voice_number}")
    if args.license_plate:
        random_license_plate = get_random_license_plate()
        print(f"license plate: {random_license_plate}")


if __name__ == "__main__":
    main()
